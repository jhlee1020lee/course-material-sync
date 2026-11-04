"""Small, account-independent material synchronization engine.

The state file is the commit point. New revisions use new paths, so a failed
state replacement cannot point an existing record at partially replaced bytes.
Only callers' material identifiers and relative paths are persisted; download
URLs and exception messages are never included in state or reports.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from .models import Material

SCHEMA_VERSION = 1
STATE_LIMIT = 8 * 1024 * 1024
_COUNTS = ("added", "updated", "unchanged", "repaired", "failed", "planned")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])\Z", re.I)


class SyncError(Exception):
    """A workspace-level failure with a safe, stable public error code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _ItemError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _component(value: Any, *, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or value in {".", ".."}
        or value != value.strip()
        or value[-1:] == "."
        or any(unicodedata.category(c).startswith("C") or c in '<>:"/\\|?*' for c in value)
        or _RESERVED.fullmatch(value.split(".", 1)[0].rstrip(" ."))
    ):
        raise _ItemError("UNSAFE_NAME")
    return value


def _report_label(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or len(value) > 256
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        return None
    return value


def _validate_material(material: Material) -> None:
    if not isinstance(material, Material):
        raise _ItemError("INVALID_MATERIAL")
    _component(material.course, limit=64)
    _component(material.filename, limit=120)
    if (
        not isinstance(material.id, str)
        or not material.id
        or len(material.id) > 256
        or any(unicodedata.category(c).startswith("C") for c in material.id)
        or not isinstance(material.url, str)
        or not material.url
        or any(unicodedata.category(c).startswith("C") for c in material.url)
        or (material.updated_at is not None and not isinstance(material.updated_at, str))
    ):
        raise _ItemError("INVALID_MATERIAL")


def _key(course: str, material_id: str) -> str:
    return hashlib.sha256((course + "\0" + material_id).encode("utf-8")).hexdigest()


def _stem(course: str, material_id: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9_-]", "_", material_id).strip("_")[:20] or "item"
    return prefix + "-" + _key(course, material_id)[:32]


def _file_path(course: str, material_id: str, filename: str, digest: str) -> str:
    return f"files/{course}/{_stem(course, material_id)}-{digest}-{filename}"


def _history_path(course: str, material_id: str, filename: str, digest: str) -> str:
    return f"history/{course}/{_stem(course, material_id)}/{digest}-{filename}"


def _reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _check_existing(path: Path, *, directory: bool) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if _reparse(info) or (
        not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode)
    ):
        raise SyncError("UNSAFE_WORKSPACE")
    return True


def _check_directory_chain(path: Path) -> None:
    for part in reversed((path, *path.parents)):
        _check_existing(part, directory=True)


def _open_read(path: Path) -> Any:
    _check_existing(path, directory=False)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    info = os.fstat(fd)
    if _reparse(info) or not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise SyncError("UNSAFE_WORKSPACE")
    return os.fdopen(fd, "rb")


def _matches(path: Path, digest: str, size: int) -> bool:
    if not _check_existing(path, directory=False):
        return False
    with _open_read(path) as handle:
        if os.fstat(handle.fileno()).st_size != size:
            return False
        actual = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            actual.update(chunk)
        return actual.hexdigest() == digest


def _atomic_bytes(path: Path, payload: bytes) -> None:
    _check_directory_chain(path.parent)
    _check_existing(path, directory=False)
    fd, name = tempfile.mkstemp(prefix=".sync-", suffix=".tmp", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _check_existing(path, directory=False)
        os.replace(staged, path)
    finally:
        with contextlib.suppress(OSError):
            staged.unlink(missing_ok=True)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


class SyncEngine:
    def __init__(
        self, workspace: Path, fetch: Callable[[Material], bytes], max_bytes: int = 50 * 1024 * 1024
    ):
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if not callable(fetch):
            raise TypeError("fetch must be callable")
        self.workspace = Path(os.path.abspath(os.fspath(workspace)))
        self.fetch = fetch
        self.max_bytes = max_bytes

    def _path(self, relative: str) -> Path:
        if not isinstance(relative, str) or "\\" in relative or ":" in relative:
            raise SyncError("INVALID_STATE")
        pure = PurePosixPath(relative)
        if (
            pure.is_absolute()
            or pure.as_posix() != relative
            or any(p in {".", ".."} for p in pure.parts)
        ):
            raise SyncError("INVALID_STATE")
        path = self.workspace.joinpath(*pure.parts)
        _check_directory_chain(path.parent)
        _check_existing(path, directory=False)
        return path

    def _mkdir(self, path: Path) -> None:
        _check_directory_chain(path)
        path.mkdir(parents=True, exist_ok=True)
        _check_directory_chain(path)

    @contextlib.contextmanager
    def _lock(self) -> Iterator[None]:
        lock_path = self.workspace / ".sync.lock"
        try:
            fd = os.open(
                lock_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            raise SyncError("WORKSPACE_BUSY") from None
        except OSError:
            raise SyncError("WORKSPACE_IO_FAILED") from None
        info = os.fstat(fd)
        try:
            yield
        finally:
            os.close(fd)
            with contextlib.suppress(OSError):
                current = lock_path.lstat()
                if not _reparse(current) and (current.st_dev, current.st_ino) == (
                    info.st_dev,
                    info.st_ino,
                ):
                    lock_path.unlink()

    def _load_state(self) -> dict[str, Any]:
        state_path = self.workspace / "state.json"
        if not _check_existing(state_path, directory=False):
            return {"schema_version": SCHEMA_VERSION, "materials": {}}
        try:
            with _open_read(state_path) as handle:
                payload = handle.read(STATE_LIMIT + 1)
            if len(payload) > STATE_LIMIT:
                raise ValueError("state too large")
            state = json.loads(payload.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
            if not isinstance(state, dict) or set(state) != {"schema_version", "materials"}:
                raise ValueError("state structure")
            if (
                type(state["schema_version"]) is not int
                or state["schema_version"] != SCHEMA_VERSION
            ):
                raise ValueError("state version")
            if not isinstance(state["materials"], dict):
                raise ValueError("state records")
            for key, record in state["materials"].items():
                self._validate_record(key, record)
            return state
        except (ValueError, TypeError, KeyError, UnicodeError, _ItemError):
            raise SyncError("INVALID_STATE") from None
        except OSError:
            raise SyncError("WORKSPACE_IO_FAILED") from None

    def _validate_record(self, key: str, record: Any) -> None:
        if not isinstance(record, dict) or set(record) != {
            "course",
            "id",
            "filename",
            "path",
            "sha256",
            "size",
            "history",
        }:
            raise ValueError("record structure")
        material = Material(record["id"], record["course"], record["filename"], "metadata-only")
        _validate_material(material)
        if key != _key(material.course, material.id):
            raise ValueError("record identity")
        self._validate_version(record, material, history=False)
        if not isinstance(record["history"], list):
            raise ValueError("history structure")
        seen: set[str] = set()
        for version in record["history"]:
            if not isinstance(version, dict) or set(version) != {
                "filename",
                "path",
                "sha256",
                "size",
            }:
                raise ValueError("version structure")
            self._validate_version(version, material, history=True)
            if version["path"] in seen:
                raise ValueError("duplicate history")
            seen.add(version["path"])

    def _validate_version(
        self, version: dict[str, Any], material: Material, *, history: bool
    ) -> None:
        filename = _component(version["filename"], limit=120)
        digest, size = version["sha256"], version["size"]
        if (
            not isinstance(digest, str)
            or not _HASH.fullmatch(digest)
            or type(size) is not int
            or not 0 <= size < 2**63
        ):
            raise ValueError("version metadata")
        expected = (_history_path if history else _file_path)(
            material.course, material.id, filename, digest
        )
        if version["path"] != expected:
            raise ValueError("version path")
        self._path(expected)

    def _archive(self, old: dict[str, Any], old_path: Path) -> tuple[dict[str, Any], bool]:
        relative = _history_path(old["course"], old["id"], old["filename"], old["sha256"])
        target = self._path(relative)
        version = {key: old[key] for key in ("filename", "sha256", "size")}
        version["path"] = relative
        if target.exists():
            if not _matches(target, old["sha256"], old["size"]):
                raise _ItemError("HISTORY_CONFLICT")
            return version, False
        self._mkdir(target.parent)
        fd, name = tempfile.mkstemp(prefix=".sync-", suffix=".tmp", dir=target.parent)
        staged = Path(name)
        try:
            with os.fdopen(fd, "wb") as output, _open_read(old_path) as source:
                digest = hashlib.sha256()
                size = 0
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    size += len(chunk)
                    if size > old["size"]:
                        raise _ItemError("LOCAL_CHANGED_DURING_SYNC")
                    digest.update(chunk)
                    output.write(chunk)
                if size != old["size"] or digest.hexdigest() != old["sha256"]:
                    raise _ItemError("LOCAL_CHANGED_DURING_SYNC")
                output.flush()
                os.fsync(output.fileno())
            _check_existing(target, directory=False)
            os.replace(staged, target)
        finally:
            with contextlib.suppress(OSError):
                staged.unlink(missing_ok=True)
        return version, True

    def _sync_one(self, material: Material, state: dict[str, Any]) -> dict[str, Any]:
        key = _key(material.course, material.id)
        old = state["materials"].get(key)
        old_path = self._path(old["path"]) if old else None
        old_valid = bool(old and _matches(old_path, old["sha256"], old["size"]))
        try:
            payload = self.fetch(material)
        except Exception:
            raise _ItemError("FETCH_FAILED") from None
        if not isinstance(payload, bytes):
            raise _ItemError("INVALID_RESPONSE")
        if len(payload) > self.max_bytes:
            raise _ItemError("SIZE_LIMIT")
        digest = hashlib.sha256(payload).hexdigest()
        relative = _file_path(material.course, material.id, material.filename, digest)
        target = self._path(relative)
        changed = bool(old and (old["sha256"] != digest or old["filename"] != material.filename))
        status = (
            "added"
            if old is None
            else "updated"
            if changed
            else "unchanged"
            if old_valid
            else "repaired"
        )
        if status == "unchanged":
            return {"status": status, "path": relative}
        history = list(old["history"]) if old else []
        if old and old_valid and old_path != target:
            version, _ = self._archive(old, old_path)
            if not any(entry["path"] == version["path"] for entry in history):
                history.append(version)
        target_exists = _check_existing(target, directory=False)
        if target_exists and not _matches(target, digest, len(payload)) and target != old_path:
            raise _ItemError("TARGET_CONFLICT")
        self._mkdir(target.parent)
        if not target_exists or not _matches(target, digest, len(payload)):
            _atomic_bytes(target, payload)
        record = {
            "course": material.course,
            "id": material.id,
            "filename": material.filename,
            "path": relative,
            "sha256": digest,
            "size": len(payload),
            "history": history,
        }
        next_state = {
            "schema_version": SCHEMA_VERSION,
            "materials": {**state["materials"], key: record},
        }
        serialized = (
            json.dumps(next_state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        if len(serialized) > STATE_LIMIT:
            raise _ItemError("STATE_SIZE_LIMIT")
        try:
            _atomic_bytes(self.workspace / "state.json", serialized)
        except OSError:
            if not target_exists:
                with contextlib.suppress(OSError):
                    target.unlink()
            raise _ItemError("STATE_WRITE_FAILED") from None
        state["materials"][key] = record
        # A crash before cleanup leaves a harmless duplicate. The archived
        # revision and the new state have already been committed at this point.
        if old and old_valid and old_path != target:
            with contextlib.suppress(OSError):
                if _matches(old_path, old["sha256"], old["size"]):
                    old_path.unlink()
        result: dict[str, Any] = {"status": status, "path": relative}
        if old and not old_valid and changed:
            result["previous_local_copy"] = "unavailable_or_modified"
        return result

    def run(self, materials: Iterable[Material], *, dry_run: bool = False) -> dict[str, Any]:
        try:
            candidates = list(materials)
        except Exception:
            raise SyncError("INVALID_INPUT") from None
        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "counts": dict.fromkeys(_COUNTS, 0),
            "items": [],
        }
        try:
            _check_directory_chain(self.workspace)
            if dry_run:
                state = self._load_state()
                self._process(candidates, state, summary, dry_run=True)
            else:
                self._mkdir(self.workspace)
                with self._lock():
                    state = self._load_state()
                    self._process(candidates, state, summary, dry_run=False)
        except OSError:
            raise SyncError("WORKSPACE_IO_FAILED") from None
        return summary

    def _process(
        self,
        candidates: list[Material],
        state: dict[str, Any],
        summary: dict[str, Any],
        *,
        dry_run: bool,
    ) -> None:
        seen: set[str] = set()
        for material in candidates:
            item = {
                name: _report_label(getattr(material, name, None))
                if isinstance(material, Material)
                else None
                for name in ("course", "id", "filename")
            }
            try:
                _validate_material(material)
                key = _key(material.course, material.id)
                if key in seen:
                    raise _ItemError("DUPLICATE_ID")
                seen.add(key)
                if dry_run:
                    item["status"] = "planned"
                else:
                    item.update(self._sync_one(material, state))
            except _ItemError as exc:
                item.update(status="failed", error_code=exc.code)
            except OSError:
                item.update(status="failed", error_code="STORAGE_FAILED")
            summary["items"].append(item)
            summary["counts"][item["status"]] += 1

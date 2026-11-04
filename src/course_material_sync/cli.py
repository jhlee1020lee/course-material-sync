"""Small explicit commands with machine-readable results and sanitized errors."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-sync", description="Sync authorized Canvas files."
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "login", "run"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", type=Path, default=Path(".course-sync"))
        command.add_argument("--json", action="store_true", help="Print a JSON result.")
        if name != "demo":
            command.add_argument("--config", type=Path, required=True)
        if name != "login":
            command.add_argument(
                "--dry-run", action="store_true", help="Plan without saving files."
            )
        if name == "demo":
            command.add_argument("--revision", type=int, choices=(1, 2), default=1)
        elif name == "run":
            command.add_argument(
                "--headed", action="store_true", help="Show the dedicated browser."
            )
    return parser


def _workspace_path(path: Path, *, create: bool = False) -> Path:
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        try:
            mode = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode.st_mode) or (
            getattr(mode, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ConfigError("workspace_link_not_allowed")
    absolute = absolute.resolve(strict=False)
    if absolute == Path(absolute.anchor) or (absolute.exists() and not absolute.is_dir()):
        raise ConfigError("invalid_workspace")
    if create:
        absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
    return absolute


def _print_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    if "error_code" in result:
        print("Error: " + result["error_code"], file=sys.stderr)
        return
    if "counts" in result:
        print(" ".join(f"{key}={value}" for key, value in result["counts"].items()))
        for item in result.get("items", []):
            print(f"{item.get('status', '')}: {item.get('course', '')}/{item.get('filename', '')}")
    else:
        print(result.get("status", "done"))


def _canvas_command(args: argparse.Namespace) -> dict:
    from .canvas import AuthRequired, CanvasError, CanvasSource

    config = load_config(args.config)
    workspace = _workspace_path(args.workspace, create=args.command == "login")
    profile = _workspace_path(workspace / ".browser-profile")
    if args.command == "run" and not profile.is_dir():
        raise AuthRequired("login_required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ConfigError("install_canvas_extra_and_chromium") from exc
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            headless=args.command != "login" and not args.headed,
            accept_downloads=False,
        )
        try:
            if args.command == "login":
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(config.base_url, wait_until="domcontentloaded", timeout=30000)
                print(
                    "Sign in in the dedicated browser, then press Enter here. "
                    "Do not paste passwords or authentication codes into this terminal.",
                    file=sys.stderr,
                )
                input()
                source = CanvasSource(config.base_url, context.request)
                # Verify access without collecting participants, grades, or submissions.
                source.list_materials(config.courses[0].id, config.courses[0].slug)
                return {"schema_version": 1, "status": "login_verified"}
            source = CanvasSource(
                config.base_url,
                context.request,
                allowed_download_hosts=config.allowed_download_hosts,
                max_bytes=config.max_bytes,
            )
            materials = []
            for course in config.courses:
                materials.extend(source.list_materials(course.id, course.slug))
            return _sync_canvas_source(
                workspace, source, materials, max_bytes=config.max_bytes, dry_run=args.dry_run
            )
        except EOFError as exc:
            raise CanvasError("interactive_login_required") from exc
        finally:
            context.close()


def _sync_canvas_source(workspace, source, materials, *, max_bytes, dry_run):
    from .canvas import AuthRequired
    from .sync import SyncEngine

    authentication_failed = False

    def fetch(material):
        nonlocal authentication_failed
        if authentication_failed:
            raise AuthRequired()
        try:
            return source.fetch(material)
        except AuthRequired:
            authentication_failed = True
            raise

    result = SyncEngine(workspace, fetch, max_bytes=max_bytes).run(materials, dry_run=dry_run)
    if authentication_failed:
        result["error_code"] = "authentication_required"
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from .canvas import AuthRequired, CanvasError
    from .sync import SyncError

    try:
        if args.command == "demo":
            from .demo import run_demo

            result = run_demo(
                _workspace_path(args.workspace), revision=args.revision, dry_run=args.dry_run
            )
        else:
            result = _canvas_command(args)
        _print_result(result, args.json)
        if result.get("error_code") == "authentication_required":
            return 3
        return 1 if result.get("counts", {}).get("failed", 0) else 0
    except ConfigError as exc:
        _print_result({"schema_version": 1, "error_code": str(exc)}, args.json)
        return 2
    except AuthRequired as exc:
        _print_result({"schema_version": 1, "error_code": exc.code}, args.json)
        return 3
    except (SyncError, CanvasError) as exc:
        _print_result({"schema_version": 1, "error_code": exc.code}, args.json)
        return 1
    except KeyboardInterrupt:
        _print_result({"schema_version": 1, "error_code": "interrupted"}, args.json)
        return 130
    except Exception:
        # Browser exceptions can contain signed URLs or account details; never echo them.
        _print_result({"schema_version": 1, "error_code": "operation_failed"}, args.json)
        return 1

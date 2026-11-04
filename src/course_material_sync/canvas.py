"""Read-only Canvas file discovery using a caller-owned Playwright session.

Only course file and module APIs are queried. Authentication is performed by
the caller in a browser; this module never reads passwords or exports cookies.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from .models import Material


class CanvasError(Exception):
    """An error with a bounded code, never a remote URL or response body."""

    def __init__(self, code: str = "canvas_error") -> None:
        self.code = code if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) else "canvas_error"
        super().__init__(self.code)


class AuthRequired(CanvasError):
    """The session needs authentication or permission to access this course."""

    def __init__(self, code: str = "authentication_required") -> None:
        super().__init__(code)


SUPPORTED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".ppt",
        ".pptx",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".hwp",
        ".hwpx",
        ".odt",
        ".odp",
        ".ods",
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".zip",
        ".tar",
        ".gz",
        ".7z",
        ".ipynb",
        ".py",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".java",
        ".scala",
        ".rs",
        ".r",
        ".m",
        ".sql",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
    }
)
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_REDIRECTS = 5
_TIMEOUT_MS = 30_000


def _parsed_url(value: str) -> Any:
    if not isinstance(value, str) or not value or re.search(r"[\x00-\x20\\]", value):
        raise CanvasError("invalid_url")
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise CanvasError("invalid_url") from None
    return parsed


def _origin(parsed: Any) -> tuple[str, str, int]:
    return parsed.scheme, parsed.hostname.casefold(), parsed.port or 443


def _positive_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise CanvasError("invalid_identifier")
    if isinstance(value, str) and not re.fullmatch(r"[1-9][0-9]*", value):
        raise CanvasError("invalid_identifier")
    result = int(value)
    if result <= 0:
        raise CanvasError("invalid_identifier")
    return result


class CanvasSource:
    """Discover accessible files and fetch bytes without recording signed URLs.

    ``request`` is a synchronous Playwright ``BrowserContext.request``.
    ``max_bytes`` limits accepted content, not the transport's buffered memory.
    Additional download hosts permit HTTPS on port 443, without wildcards.
    """

    def __init__(
        self,
        base_url: str,
        request: Any,
        *,
        allowed_download_hosts: Sequence[str] = (),
        max_pages: int = 100,
        max_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        parsed = _parsed_url(base_url)
        if parsed.path not in {"", "/"} or parsed.query:
            raise CanvasError("invalid_base_url")
        if (
            type(max_pages) is not int
            or max_pages < 1
            or type(max_bytes) is not int
            or max_bytes < 1
        ):
            raise CanvasError("invalid_limit")
        if isinstance(allowed_download_hosts, (str, bytes)):
            raise CanvasError("invalid_download_host")
        allowed: set[str] = set()
        for host in allowed_download_hosts:
            if not isinstance(host, str) or not re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host
            ):
                raise CanvasError("invalid_download_host")
            if ".." in host or any(
                part.startswith("-") or part.endswith("-") for part in host.split(".")
            ):
                raise CanvasError("invalid_download_host")
            allowed.add(host.casefold())
        self.base_url = base_url.rstrip("/")
        self.request = request
        self.max_pages = max_pages
        self.max_bytes = max_bytes
        self._base_origin = _origin(parsed)
        self._download_hosts = frozenset(allowed)
        self._known_sizes: dict[tuple[str, str], int | None] = {}

    def _validate_api_url(self, url: str, *, path: str | None = None) -> None:
        parsed = _parsed_url(url)
        if _origin(parsed) != self._base_origin:
            raise CanvasError("untrusted_api_origin")
        if not parsed.path.startswith("/api/v1/") or (path is not None and parsed.path != path):
            raise CanvasError("unexpected_api_path")

    def _validate_download_url(self, url: str) -> None:
        parsed = _parsed_url(url)
        origin = _origin(parsed)
        if origin != self._base_origin and not (
            parsed.hostname.casefold() in self._download_hosts and origin[2] == 443
        ):
            raise CanvasError("untrusted_download_origin")
        if re.search(r"/(?:login|signin|sign_in|oauth2?)(?:/|$)", parsed.path, re.I):
            raise AuthRequired()

    def _request(self, url: str) -> Any:
        try:
            response = self.request.get(
                url,
                fail_on_status_code=False,
                timeout=_TIMEOUT_MS,
                max_redirects=0,
                headers={"Accept": "*/*", "Authorization": ""},
            )
        except Exception:
            raise CanvasError("request_failed") from None
        # The transport must not silently follow redirects despite max_redirects=0.
        if str(response.url) != url:
            self._dispose(response)
            raise CanvasError("unexpected_response_url")
        return response

    @staticmethod
    def _dispose(response: Any) -> None:
        try:
            response.dispose()
        except Exception:
            pass

    @staticmethod
    def _headers(response: Any) -> dict[str, str]:
        try:
            return {str(k).casefold(): str(v) for k, v in response.headers.items()}
        except Exception:
            raise CanvasError("invalid_response_headers") from None

    @staticmethod
    def _check_status(response: Any) -> None:
        if response.status in {401, 403}:
            raise AuthRequired()
        if response.status != 200:
            raise CanvasError("http_error")

    @staticmethod
    def _body(response: Any, headers: dict[str, str], limit: int) -> bytes:
        length = headers.get("content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                raise CanvasError("invalid_content_length") from None
            if declared < 0:
                raise CanvasError("invalid_content_length")
            if declared > limit:
                raise CanvasError("response_too_large")
        try:
            body = response.body()
        except Exception:
            raise CanvasError("response_read_failed") from None
        if not isinstance(body, bytes):
            raise CanvasError("invalid_response_body")
        if len(body) > limit:
            raise CanvasError("response_too_large")
        return body

    def _api_json(self, url: str) -> tuple[Any, dict[str, str]]:
        self._validate_api_url(url)
        response = self._request(url)
        try:
            if response.status in _REDIRECTS:
                raise AuthRequired("authentication_redirect")
            self._check_status(response)
            headers = self._headers(response)
            content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type in _HTML_TYPES:
                raise AuthRequired("authentication_html")
            if content_type != "application/json" and not content_type.endswith("+json"):
                raise CanvasError("unexpected_metadata_type")
            data = self._body(response, headers, _MAX_METADATA_BYTES)
            try:
                text = data.decode("utf-8-sig")
                if text.startswith("while(1);"):
                    text = text[len("while(1);") :]
                payload = json.loads(text)
            except (UnicodeError, ValueError):
                raise CanvasError("invalid_metadata_json") from None
            return payload, headers
        finally:
            self._dispose(response)

    @staticmethod
    def _next_link(header: str) -> str | None:
        if not header:
            return None
        matches = list(re.finditer(r"<([^<>]+)>\s*((?:;\s*[^,]*)?)", header))
        if not matches:
            raise CanvasError("invalid_pagination")
        next_links: list[str] = []
        previous_end = 0
        for match in matches:
            if header[previous_end : match.start()].strip(" ,\t\r\n"):
                raise CanvasError("invalid_pagination")
            previous_end = match.end()
            url, parameters = match.groups()
            relation = re.search(r'(?:^|;)\s*rel\s*=\s*(?:"([^"]+)"|([^;\s]+))', parameters, re.I)
            if relation and "next" in (relation.group(1) or relation.group(2)).split():
                next_links.append(url)
        if header[previous_end:].strip(" ,\t\r\n"):
            raise CanvasError("invalid_pagination")
        if len(next_links) > 1:
            raise CanvasError("invalid_pagination")
        return next_links[0] if next_links else None

    def _list(self, path: str, *, include_items: bool = False) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"per_page": 100}
        if include_items:
            query["include[]"] = "items"
        url = f"{self.base_url}{path}?{urlencode(query)}"
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for _ in range(self.max_pages):
            if url in seen:
                raise CanvasError("pagination_cycle")
            seen.add(url)
            self._validate_api_url(url, path=path)
            payload, headers = self._api_json(url)
            if not isinstance(payload, list) or any(not isinstance(x, dict) for x in payload):
                raise CanvasError("invalid_list_payload")
            result.extend(payload)
            following = self._next_link(headers.get("link", ""))
            if following is None:
                return result
            url = urljoin(url, following)
        raise CanvasError("pagination_limit")

    @staticmethod
    def _blocked(item: dict[str, Any]) -> bool:
        return (
            any(
                item.get(key) is True
                for key in ("hidden", "hidden_for_user", "locked", "locked_for_user")
            )
            or item.get("published") is False
            or item.get("upload_status", "success") != "success"
        )

    def _material(self, item: dict[str, Any], course: str) -> Material | None:
        file_id = _positive_id(item.get("id"))
        if self._blocked(item):
            return None
        name = item.get("display_name") or item.get("filename")
        if not isinstance(name, str) or not name or len(name) > 512:
            raise CanvasError("invalid_filename")
        if PurePosixPath(name).suffix.casefold() not in SUPPORTED_EXTENSIONS:
            return None
        if "/" in name or "\\" in name or re.search(r"[\x00-\x1f\x7f]", name):
            raise CanvasError("invalid_filename")
        metadata_type = (
            str(item.get("content-type") or item.get("content_type") or "").split(";", 1)[0].lower()
        )
        if metadata_type in _HTML_TYPES:
            return None
        size = item.get("size")
        if size is not None:
            if type(size) is not int or size < 0:
                raise CanvasError("invalid_file_size")
        url = item.get("url")
        if not isinstance(url, str):
            raise CanvasError("invalid_download_url")
        self._validate_download_url(url)
        updated = item.get("updated_at")
        if updated is not None:
            if not isinstance(updated, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", updated
            ):
                raise CanvasError("invalid_updated_at")
            try:
                datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                raise CanvasError("invalid_updated_at") from None
        return Material(id=str(file_id), course=course, filename=name, url=url, updated_at=updated)

    def list_materials(self, course_id: int, course_slug: str) -> list[Material]:
        course_id = _positive_id(course_id)
        if not isinstance(course_slug, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", course_slug
        ):
            raise CanvasError("invalid_course_slug")
        course_path = f"/api/v1/courses/{course_id}"
        files = self._list(f"{course_path}/files")
        known: dict[int, Material | None] = {}
        sizes: dict[int, int | None] = {}
        for item in files:
            file_id = _positive_id(item.get("id"))
            candidate = self._material(item, course_slug)
            size = item.get("size") if candidate is not None else None
            if file_id in known and (known[file_id] != candidate or sizes[file_id] != size):
                raise CanvasError("conflicting_file_metadata")
            known[file_id] = candidate
            sizes[file_id] = size
        modules = self._list(f"{course_path}/modules", include_items=True)
        for module in modules:
            if module.get("published") is False or module.get("state") == "locked":
                continue
            module_id = _positive_id(module.get("id"))
            embedded = module.get("items")
            count = module.get("items_count")
            if count is not None and (type(count) is not int or count < 0):
                raise CanvasError("invalid_module_count")
            if not isinstance(embedded, list) or count is None or len(embedded) < count:
                items = self._list(f"{course_path}/modules/{module_id}/items")
                if count is not None and len(items) < count:
                    raise CanvasError("incomplete_module_items")
            else:
                items = embedded
            for item in items:
                if not isinstance(item, dict):
                    raise CanvasError("invalid_module_item")
                if item.get("type") != "File" or self._blocked(item):
                    continue
                details = item.get("content_details")
                if isinstance(details, dict) and details.get("locked_for_user") is True:
                    continue
                file_id = _positive_id(item.get("content_id"))
                if file_id not in known:
                    payload, _ = self._api_json(f"{self.base_url}/api/v1/files/{file_id}")
                    if not isinstance(payload, dict) or _positive_id(payload.get("id")) != file_id:
                        raise CanvasError("invalid_file_metadata")
                    known[file_id] = self._material(payload, course_slug)
                    sizes[file_id] = payload.get("size") if known[file_id] is not None else None
        # Publish size hints only after the complete discovery succeeds. They are
        # private runtime metadata, not part of the persisted Material contract.
        self._known_sizes = {
            key: value for key, value in self._known_sizes.items() if key[0] != course_slug
        }
        self._known_sizes.update(
            ((course_slug, str(file_id)), sizes[file_id])
            for file_id, material in known.items()
            if material is not None
        )
        return [item for item in known.values() if item is not None]

    def fetch(self, material: Material) -> bytes:
        if PurePosixPath(material.filename).suffix.casefold() not in SUPPORTED_EXTENSIONS:
            raise CanvasError("unsupported_extension")
        size = self._known_sizes.get((material.course, material.id))
        if size is not None and size > self.max_bytes:
            raise CanvasError("file_too_large")
        url = material.url
        seen: set[str] = set()
        for _ in range(_MAX_REDIRECTS + 1):
            self._validate_download_url(url)
            if url in seen:
                raise CanvasError("redirect_cycle")
            seen.add(url)
            response = self._request(url)
            try:
                headers = self._headers(response)
                if response.status in _REDIRECTS:
                    location = headers.get("location")
                    if not location:
                        raise CanvasError("invalid_redirect")
                    url = urljoin(url, location)
                    continue
                self._check_status(response)
                mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if mime in _HTML_TYPES:
                    raise AuthRequired("authentication_html")
                body = self._body(response, headers, self.max_bytes)
                prefix = body[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
                if prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body", b"<form")):
                    raise AuthRequired("authentication_html")
                if not body:
                    raise CanvasError("empty_download")
                return body
            finally:
                self._dispose(response)
        raise CanvasError("redirect_limit")

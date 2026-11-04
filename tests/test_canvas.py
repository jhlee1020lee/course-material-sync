from __future__ import annotations

import json
import unittest

from course_material_sync.canvas import AuthRequired, CanvasError, CanvasSource
from course_material_sync.models import Material

BASE = "https://canvas.example.com"
FILES = f"{BASE}/api/v1/courses/7/files?per_page=100"
MODULES = f"{BASE}/api/v1/courses/7/modules?per_page=100&include%5B%5D=items"


class Response:
    def __init__(self, url, *, payload=None, data=None, status=200, headers=None):
        self.url = url
        self.status = status
        self.headers = headers or {"content-type": "application/json"}
        self.data = json.dumps(payload).encode() if data is None else data
        self.disposed = False

    def body(self):
        return self.data

    def dispose(self):
        self.disposed = True


class Requests:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        return route


def metadata(file_id=3, filename="lecture.pdf", **extra):
    return {
        "id": file_id,
        "display_name": filename,
        "url": f"{BASE}/files/{file_id}/download?verifier=synthetic",
        "size": 5,
        "updated_at": "2020-01-01T00:00:00Z",
        **extra,
    }


def source_with(files, modules=None, routes=None, **kwargs):
    request = Requests(
        {
            FILES: Response(FILES, payload=files),
            MODULES: Response(MODULES, payload=modules or []),
            **(routes or {}),
        }
    )
    return CanvasSource(BASE, request, **kwargs), request


class DiscoveryTests(unittest.TestCase):
    def test_lists_files_and_unlisted_module_files_without_duplicates(self):
        file_url = f"{BASE}/api/v1/files/4"
        modules = [
            {
                "id": 11,
                "items_count": 3,
                "items": [
                    {"type": "File", "content_id": 3},
                    {"type": "File", "content_id": 4},
                    {"type": "Assignment", "content_id": 99},
                ],
            }
        ]
        source, request = source_with(
            [metadata()], modules, {file_url: Response(file_url, payload=metadata(4, "lab.zip"))}
        )
        materials = source.list_materials(7, "sample")
        self.assertEqual([m.id for m in materials], ["3", "4"])
        self.assertEqual(materials[1].course, "sample")
        self.assertFalse(any("assignments" in url for url, _ in request.calls))
        self.assertTrue(all(r.disposed for r in request.routes.values()))

    def test_follows_opaque_link_even_when_page_is_short(self):
        next_url = f"{BASE}/api/v1/courses/7/files?opaque=next"
        source, request = source_with(
            [metadata()],
            routes={
                next_url: Response(next_url, payload=[metadata(4)]),
            },
        )
        request.routes[FILES].headers["Link"] = f'<{next_url}>; rel="next"'
        self.assertEqual(len(source.list_materials(7, "sample")), 2)

    def test_fetches_items_when_canvas_omits_embedded_items(self):
        item_url = f"{BASE}/api/v1/courses/7/modules/11/items?per_page=100"
        source, _ = source_with(
            [metadata()],
            [{"id": 11, "items_count": 1}],
            {item_url: Response(item_url, payload=[{"type": "File", "content_id": 3}])},
        )
        self.assertEqual(len(source.list_materials(7, "sample")), 1)

    def test_skips_hidden_locked_unpublished_unsupported_and_html(self):
        source, _ = source_with(
            [
                metadata(1, hidden_for_user=True),
                metadata(2, locked=True),
                metadata(3, published=False),
                metadata(4, "video.mp4"),
                metadata(5, **{"content-type": "text/html"}),
                metadata(6),
            ],
            [{"id": 8, "state": "locked"}],
        )
        self.assertEqual([m.id for m in source.list_materials(7, "sample")], ["6"])

    def test_failed_second_page_is_not_partial_success(self):
        next_url = f"{BASE}/api/v1/courses/7/files?page=2"
        source, request = source_with(
            [metadata()], routes={next_url: Response(next_url, status=500)}
        )
        request.routes[FILES].headers["link"] = f'<{next_url}>; rel="next"'
        with self.assertRaisesRegex(CanvasError, "http_error"):
            source.list_materials(7, "sample")

    def test_page_limit_fails_explicitly(self):
        source, request = source_with([metadata()], max_pages=1)
        request.routes[FILES].headers["link"] = f'<{FILES}&page=2>; rel="next"'
        with self.assertRaisesRegex(CanvasError, "pagination_limit"):
            source.list_materials(7, "sample")

    def test_foreign_pagination_is_rejected_before_request(self):
        source, request = source_with([])
        request.routes[FILES].headers["link"] = '<https://other.example/api/v1/files>; rel="next"'
        with self.assertRaisesRegex(CanvasError, "untrusted_api_origin"):
            source.list_materials(7, "sample")
        self.assertEqual(len(request.calls), 1)

    def test_pagination_cannot_switch_to_roster_api(self):
        source, request = source_with([])
        request.routes[FILES].headers["link"] = f'<{BASE}/api/v1/courses/7/users>; rel="next"'
        with self.assertRaisesRegex(CanvasError, "unexpected_api_path"):
            source.list_materials(7, "sample")
        self.assertEqual(len(request.calls), 1)

    def test_bad_schema_and_filename_are_not_silently_ignored(self):
        for value, expected in [
            ({"oops": []}, "invalid_list_payload"),
            ([metadata(filename="../lecture.pdf")], "invalid_filename"),
        ]:
            with self.subTest(value=value):
                source, _ = source_with(value)
                with self.assertRaisesRegex(CanvasError, expected):
                    source.list_materials(7, "sample")

    def test_api_html_and_auth_status_are_auth_required(self):
        for status, content_type in [
            (200, "text/html"),
            (401, "application/json"),
            (403, "application/json"),
        ]:
            with self.subTest(status=status):
                source, request = source_with([])
                request.routes[FILES] = Response(
                    FILES, status=status, headers={"content-type": content_type}
                )
                with self.assertRaises(AuthRequired):
                    source.list_materials(7, "sample")

    def test_module_metadata_error_is_not_suppressed(self):
        meta = f"{BASE}/api/v1/files/4"
        source, _ = source_with(
            [],
            [{"id": 1, "items_count": 1, "items": [{"type": "File", "content_id": 4}]}],
            {meta: Response(meta, status=404)},
        )
        with self.assertRaisesRegex(CanvasError, "http_error"):
            source.list_materials(7, "sample")

    def test_incomplete_module_response_is_rejected(self):
        items = f"{BASE}/api/v1/courses/7/modules/1/items?per_page=100"
        source, _ = source_with(
            [], [{"id": 1, "items_count": 2}], {items: Response(items, payload=[])}
        )
        with self.assertRaisesRegex(CanvasError, "incomplete_module_items"):
            source.list_materials(7, "sample")

    def test_invalid_configuration_is_rejected(self):
        for url in [
            "http://canvas.example.com",
            "https://user:pass@canvas.example.com",
            "https://canvas.example.com/?token=hidden",
            "https://canvas.example.com/path",
        ]:
            with self.subTest(url=url), self.assertRaises(CanvasError):
                CanvasSource(url, Requests({}))
        with self.assertRaises(CanvasError):
            CanvasSource(BASE, Requests({}), allowed_download_hosts=["*.example.com"])

    def test_pagination_cycle_and_malformed_link_are_explicit(self):
        for link, expected in [
            (f'<{FILES}>; rel="next"', "pagination_cycle"),
            ('broken; rel="next"', "invalid_pagination"),
            (f'<{FILES}>; rel="current", broken; rel="next"', "invalid_pagination"),
        ]:
            with self.subTest(link=link):
                source, request = source_with([])
                request.routes[FILES].headers["link"] = link
                with self.assertRaisesRegex(CanvasError, expected):
                    source.list_materials(7, "sample")

    def test_updated_at_cannot_smuggle_arbitrary_text_into_state(self):
        for value in ["not-a-date", "2020-99-01T00:00:00Z", "2020-01-01"]:
            with self.subTest(value=value):
                source, _ = source_with([metadata(updated_at=value)])
                with self.assertRaisesRegex(CanvasError, "invalid_updated_at"):
                    source.list_materials(7, "sample")

    def test_conflicting_duplicates_are_not_silently_overwritten(self):
        source, _ = source_with([metadata(), metadata(filename="changed.pdf")])
        with self.assertRaisesRegex(CanvasError, "conflicting_file_metadata"):
            source.list_materials(7, "sample")

    def test_oversized_file_fails_individually_before_download(self):
        small = metadata(4, size=5)
        source, request = source_with(
            [metadata(3, "large.zip", size=11), small],
            routes={
                small["url"]: Response(
                    small["url"], data=b"small", headers={"content-type": "application/pdf"}
                )
            },
            max_bytes=10,
        )
        materials = source.list_materials(7, "sample")
        self.assertEqual([material.id for material in materials], ["3", "4"])
        discovery_requests = len(request.calls)
        with self.assertRaisesRegex(CanvasError, "file_too_large"):
            source.fetch(materials[0])
        self.assertEqual(len(request.calls), discovery_requests)
        self.assertEqual(source.fetch(materials[1]), b"small")
        self.assertEqual(len(request.calls), discovery_requests + 1)

    def test_conflicting_duplicate_sizes_are_not_silently_overwritten(self):
        source, _ = source_with([metadata(size=5), metadata(size=50)], max_bytes=10)
        with self.assertRaisesRegex(CanvasError, "conflicting_file_metadata"):
            source.list_materials(7, "sample")

    def test_size_hints_are_course_scoped_and_refreshed(self):
        small = metadata(size=5)
        source, request = source_with(
            [metadata(size=11)],
            routes={
                small["url"]: Response(
                    small["url"], data=b"small", headers={"content-type": "application/pdf"}
                )
            },
            max_bytes=10,
        )
        large = source.list_materials(7, "first-course")[0]
        request.routes[FILES] = Response(FILES, payload=[small])
        other_course_material = source.list_materials(7, "second-course")[0]
        self.assertEqual(source.fetch(other_course_material), b"small")
        with self.assertRaisesRegex(CanvasError, "file_too_large"):
            source.fetch(large)
        refreshed = source.list_materials(7, "first-course")[0]
        self.assertEqual(source.fetch(refreshed), b"small")


class DownloadTests(unittest.TestCase):
    def make_source(self, response, **kwargs):
        material = Material("3", "sample", "lecture.pdf", response.url)
        request = Requests({response.url: response})
        return CanvasSource(BASE, request, **kwargs), request, material

    def test_fetch_returns_bytes_and_disposes_response(self):
        response = Response(
            f"{BASE}/files/3/download",
            data=b"%PDF-test",
            headers={"content-type": "application/pdf"},
        )
        source, request, material = self.make_source(response)
        self.assertEqual(source.fetch(material), b"%PDF-test")
        self.assertTrue(response.disposed)
        self.assertEqual(request.calls[0][1]["max_redirects"], 0)
        self.assertEqual(request.calls[0][1]["headers"]["Authorization"], "")

    def test_redirect_host_is_checked_before_following(self):
        response = Response(
            f"{BASE}/files/3/download",
            status=302,
            headers={"location": "https://outside.example/file?secret=synthetic"},
        )
        source, request, material = self.make_source(response)
        with self.assertRaisesRegex(CanvasError, "untrusted_download_origin") as error:
            source.fetch(material)
        self.assertEqual(len(request.calls), 1)
        self.assertNotIn("secret", str(error.exception))

    def test_explicit_cdn_redirect_is_allowed(self):
        target = "https://cdn.example.com/file"
        first = Response(f"{BASE}/files/3/download", status=302, headers={"location": target})
        source, request, material = self.make_source(
            first, allowed_download_hosts=["cdn.example.com"]
        )
        request.routes[target] = Response(
            target, data=b"%PDF-good", headers={"content-type": "application/pdf"}
        )
        self.assertEqual(source.fetch(material), b"%PDF-good")
        self.assertEqual(len(request.calls), 2)

    def test_content_and_declared_size_limits(self):
        for headers in [{"content-type": "application/pdf"}, {"content-length": "11"}]:
            source, _, material = self.make_source(
                Response(f"{BASE}/files/3/download", data=b"x" * 11, headers=headers), max_bytes=10
            )
            with self.assertRaisesRegex(CanvasError, "response_too_large"):
                source.fetch(material)

    def test_html_login_response_is_never_saved(self):
        for body, content_type in [
            (b"login", "text/html"),
            (b" \n<!DOCTYPE html><html>Login</html>", "application/octet-stream"),
        ]:
            source, _, material = self.make_source(
                Response(
                    f"{BASE}/files/3/download", data=body, headers={"content-type": content_type}
                )
            )
            with self.assertRaises(AuthRequired):
                source.fetch(material)

    def test_login_redirect_requires_manual_authentication(self):
        source, request, material = self.make_source(
            Response(f"{BASE}/files/3/download", status=302, headers={"location": "/login/saml"})
        )
        with self.assertRaises(AuthRequired):
            source.fetch(material)
        self.assertEqual(len(request.calls), 1)

    def test_exception_text_does_not_expose_transport_details(self):
        url = f"{BASE}/files/3/download?verifier=synthetic-private-value"
        request = Requests({url: RuntimeError("Cookie: synthetic-secret " + url)})
        source = CanvasSource(BASE, request)
        with self.assertRaisesRegex(CanvasError, "request_failed") as error:
            source.fetch(Material("3", "sample", "lecture.pdf", url))
        self.assertNotIn("private", str(error.exception))
        self.assertIsNone(error.exception.__cause__)

    def test_unexpected_transport_redirect_and_empty_body_are_rejected(self):
        source, request, material = self.make_source(Response(f"{BASE}/files/3/download", data=b""))
        with self.assertRaisesRegex(CanvasError, "empty_download"):
            source.fetch(material)
        request.routes[material.url].url = "https://outside.example/file"
        with self.assertRaisesRegex(CanvasError, "unexpected_response_url"):
            source.fetch(material)

    def test_redirect_cycles_and_insecure_targets_are_rejected(self):
        for target, expected in [
            (f"{BASE}/files/3/download", "redirect_cycle"),
            ("http://canvas.example.com/files/3/download", "invalid_url"),
        ]:
            with self.subTest(target=target):
                source, _, material = self.make_source(
                    Response(f"{BASE}/files/3/download", status=302, headers={"location": target})
                )
                with self.assertRaisesRegex(CanvasError, expected):
                    source.fetch(material)


if __name__ == "__main__":
    unittest.main()

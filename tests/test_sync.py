from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock, patch

from course_material_sync import sync
from course_material_sync.models import Material
from course_material_sync.sync import SyncEngine, SyncError


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="course-sync-test-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.workspace = self.parent / "workspace"
        self.material = Material(
            "101",
            "sample-course",
            "lecture.txt",
            "https://example.invalid/file?secret=DO_NOT_STORE",
        )
        self.fetch = Mock(return_value=b"first revision\n")
        self.engine = SyncEngine(self.workspace, self.fetch, max_bytes=128)

    def run_one(self, material=None, **kwargs):
        return self.engine.run([material or self.material], **kwargs)

    def state(self):
        return json.loads((self.workspace / "state.json").read_text(encoding="utf-8"))

    def record(self):
        return next(iter(self.state()["materials"].values()))

    def current(self):
        return self.workspace / self.record()["path"]

    def assert_workspace_error(self, code, call):
        with self.assertRaises(SyncError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def symlink(self, link, destination, directory=False):
        try:
            link.symlink_to(destination, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("This account cannot create symbolic links")

    def test_material_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.material.id = "changed"

    def test_first_sync_persists_bytes_and_json_summary(self):
        result = self.run_one()
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(
            result["counts"],
            {"added": 1, "updated": 0, "unchanged": 0, "repaired": 0, "failed": 0, "planned": 0},
        )
        self.assertEqual(self.current().read_bytes(), b"first revision\n")
        self.assertEqual(result["items"][0]["path"], self.record()["path"])
        self.assertEqual(self.record()["history"], [])
        json.dumps(result)

    def test_unchanged_content_does_not_rewrite_state_or_material(self):
        self.run_one()
        previous = (self.workspace / "state.json").read_bytes()
        with patch.object(sync, "_atomic_bytes", side_effect=AssertionError("unexpected write")):
            result = self.run_one()
        self.assertEqual(result["counts"]["unchanged"], 1)
        self.assertEqual((self.workspace / "state.json").read_bytes(), previous)
        self.assertEqual(self.fetch.call_count, 2)

    def test_revision_preserves_previous_bytes_in_history(self):
        self.run_one()
        old_path = self.current()
        self.fetch.return_value = b"second revision\n"
        result = self.run_one()
        self.assertEqual(result["counts"]["updated"], 1)
        self.assertEqual(self.current().read_bytes(), b"second revision\n")
        history = self.record()["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual((self.workspace / history[0]["path"]).read_bytes(), b"first revision\n")
        self.assertFalse(old_path.exists())

    def test_revision_can_return_to_previous_content(self):
        self.run_one()
        self.fetch.return_value = b"second revision\n"
        self.run_one()
        self.fetch.return_value = b"first revision\n"
        result = self.run_one()
        self.assertEqual(result["counts"]["updated"], 1)
        self.assertEqual(self.current().read_bytes(), b"first revision\n")
        self.assertEqual(len(self.record()["history"]), 2)
        self.run_one()
        self.assertEqual(len(self.record()["history"]), 2)

    def test_missing_file_is_repaired(self):
        self.run_one()
        self.current().unlink()
        result = self.run_one()
        self.assertEqual(result["counts"]["repaired"], 1)
        self.assertEqual(self.current().read_bytes(), b"first revision\n")

    def test_corruption_of_equal_size_is_detected_and_repaired(self):
        self.run_one()
        self.current().write_bytes(b"x" * len(b"first revision\n"))
        result = self.run_one()
        self.assertEqual(result["counts"]["repaired"], 1)
        self.assertEqual(self.current().read_bytes(), b"first revision\n")

    def test_changed_source_with_missing_old_copy_does_not_invent_history(self):
        self.run_one()
        self.current().unlink()
        self.fetch.return_value = b"second revision"
        result = self.run_one()
        self.assertEqual(result["counts"]["updated"], 1)
        self.assertEqual(result["items"][0]["previous_local_copy"], "unavailable_or_modified")
        self.assertEqual(self.record()["history"], [])

    def test_same_filename_different_ids_have_distinct_paths(self):
        second = Material("102", self.material.course, self.material.filename, self.material.url)
        result = self.engine.run([self.material, second])
        self.assertEqual(result["counts"]["added"], 2)
        paths = [item["path"] for item in result["items"]]
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all((self.workspace / path).is_file() for path in paths))

    def test_renamed_source_preserves_previous_name_in_history(self):
        self.run_one()
        renamed = Material(self.material.id, self.material.course, "renamed.txt", self.material.url)
        result = self.run_one(renamed)
        self.assertEqual(result["counts"]["updated"], 1)
        self.assertEqual(self.record()["filename"], "renamed.txt")
        self.assertEqual(self.record()["history"][0]["filename"], "lecture.txt")

    def test_duplicate_identity_fails_without_second_fetch(self):
        result = self.engine.run([self.material, self.material])
        self.assertEqual(result["counts"]["added"], 1)
        self.assertEqual(result["items"][1]["error_code"], "DUPLICATE_ID")
        self.fetch.assert_called_once_with(self.material)

    def test_fetch_failure_is_isolated_and_error_details_are_redacted(self):
        second = Material("102", self.material.course, "second.txt", self.material.url)
        self.fetch.side_effect = [
            RuntimeError("secret=DO_NOT_STORE https://private.invalid"),
            b"ok",
        ]
        result = self.engine.run([self.material, second])
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertEqual(result["counts"]["added"], 1)
        self.assertEqual(result["items"][0]["error_code"], "FETCH_FAILED")
        self.assertNotIn("DO_NOT_STORE", json.dumps(result))
        self.assertNotIn("private.invalid", json.dumps(result))

    def test_url_and_updated_at_are_not_persisted(self):
        material = Material(
            "101", "sample", "file.txt", self.material.url, "PRIVATE_TIMESTAMP_TEXT"
        )
        result = self.run_one(material)
        persisted = (self.workspace / "state.json").read_text(encoding="utf-8")
        for text in (persisted, json.dumps(result)):
            self.assertNotIn("secret", text)
            self.assertNotIn("https://", text)
            self.assertNotIn("PRIVATE_TIMESTAMP_TEXT", text)

    def test_oversize_response_does_not_change_existing_state(self):
        self.run_one()
        old = (self.workspace / "state.json").read_bytes()
        self.fetch.return_value = b"x" * 129
        result = self.run_one()
        self.assertEqual(result["items"][0]["error_code"], "SIZE_LIMIT")
        self.assertEqual((self.workspace / "state.json").read_bytes(), old)
        self.assertEqual(self.current().read_bytes(), b"first revision\n")

    def test_exact_size_limit_and_empty_files_are_supported(self):
        self.fetch.return_value = b"x" * 128
        self.assertEqual(self.run_one()["counts"]["added"], 1)
        self.fetch.return_value = b""
        self.assertEqual(self.run_one()["counts"]["updated"], 1)
        self.assertEqual(self.current().read_bytes(), b"")

    def test_non_bytes_fetch_result_fails(self):
        self.fetch.return_value = "not bytes"
        result = self.run_one()
        self.assertEqual(result["items"][0]["error_code"], "INVALID_RESPONSE")
        self.assertFalse((self.workspace / "state.json").exists())

    def test_dry_run_on_new_workspace_neither_fetches_nor_writes(self):
        result = self.run_one(dry_run=True)
        self.assertEqual(result["counts"]["planned"], 1)
        self.fetch.assert_not_called()
        self.assertFalse(self.workspace.exists())

    def test_dry_run_does_not_repair_missing_files_or_rewrite_state(self):
        self.run_one()
        self.current().unlink()
        old = (self.workspace / "state.json").read_bytes()
        self.fetch.reset_mock()
        self.assertEqual(self.run_one(dry_run=True)["counts"]["planned"], 1)
        self.fetch.assert_not_called()
        self.assertEqual((self.workspace / "state.json").read_bytes(), old)
        self.assertFalse(self.current().exists())
        self.assertFalse((self.workspace / ".sync.lock").exists())

    def test_state_commit_failure_leaves_previous_revision_current(self):
        self.run_one()
        old_state = (self.workspace / "state.json").read_bytes()
        old_path = self.current()
        self.fetch.return_value = b"second revision"
        original = sync.os.replace

        def fail_state(source, destination):
            if Path(destination).name == "state.json":
                raise OSError("test failure with PRIVATE_DETAIL")
            return original(source, destination)

        with patch.object(sync.os, "replace", side_effect=fail_state):
            result = self.run_one()
        self.assertEqual(result["items"][0]["error_code"], "STATE_WRITE_FAILED")
        self.assertEqual((self.workspace / "state.json").read_bytes(), old_state)
        self.assertEqual(old_path.read_bytes(), b"first revision\n")
        self.assertNotIn("PRIVATE_DETAIL", json.dumps(result))
        self.assertEqual(self.run_one()["counts"]["updated"], 1)

    def test_material_write_failure_leaves_old_state_and_data(self):
        self.run_one()
        old_state = (self.workspace / "state.json").read_bytes()
        old_path = self.current()
        self.fetch.return_value = b"second revision"
        original = sync.os.replace

        def fail_file(source, destination):
            if "files" in Path(destination).parts:
                raise OSError("test failure")
            return original(source, destination)

        with patch.object(sync.os, "replace", side_effect=fail_file):
            result = self.run_one()
        self.assertEqual(result["items"][0]["error_code"], "STORAGE_FAILED")
        self.assertEqual((self.workspace / "state.json").read_bytes(), old_state)
        self.assertEqual(old_path.read_bytes(), b"first revision\n")
        self.assertFalse(list(self.workspace.rglob("*.tmp")))

    def test_existing_lock_is_not_removed(self):
        self.workspace.mkdir()
        lock = self.workspace / ".sync.lock"
        lock.write_bytes(b"owned by another operation")
        self.assert_workspace_error("WORKSPACE_BUSY", self.run_one)
        self.assertEqual(lock.read_bytes(), b"owned by another operation")
        self.fetch.assert_not_called()

    def test_nested_run_observes_lock_and_lock_is_released(self):
        def fetch(material):
            self.assert_workspace_error(
                "WORKSPACE_BUSY", lambda: SyncEngine(self.workspace, Mock()).run([material])
            )
            return b"ok"

        self.engine.fetch = fetch
        self.assertEqual(self.run_one()["counts"]["added"], 1)
        self.assertFalse((self.workspace / ".sync.lock").exists())

    def test_invalid_json_state_fails_closed_without_fetch(self):
        self.workspace.mkdir()
        path = self.workspace / "state.json"
        path.write_text("{broken", encoding="utf-8")
        self.assert_workspace_error("INVALID_STATE", self.run_one)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
        self.fetch.assert_not_called()

    def test_unknown_state_version_and_duplicate_keys_fail_closed(self):
        self.workspace.mkdir()
        for payload in (
            '{"schema_version":2,"materials":{}}',
            '{"schema_version":1,"schema_version":1,"materials":{}}',
        ):
            with self.subTest(payload=payload):
                (self.workspace / "state.json").write_text(payload, encoding="utf-8")
                self.assert_workspace_error("INVALID_STATE", self.run_one)
        self.fetch.assert_not_called()

    def test_path_traversal_in_state_is_rejected(self):
        self.run_one()
        state = self.state()
        next(iter(state["materials"].values()))["path"] = "../outside.txt"
        (self.workspace / "state.json").write_text(json.dumps(state), encoding="utf-8")
        self.fetch.reset_mock()
        self.assert_workspace_error("INVALID_STATE", self.run_one)
        self.fetch.assert_not_called()

    def test_unexpected_state_fields_are_rejected(self):
        self.run_one()
        state = self.state()
        next(iter(state["materials"].values()))["url"] = "https://example.invalid/private"
        (self.workspace / "state.json").write_text(json.dumps(state), encoding="utf-8")
        self.assert_workspace_error("INVALID_STATE", self.run_one)

    def test_unsafe_material_names_do_not_fetch_or_escape(self):
        for unsafe in (
            "..",
            "../outside",
            "a/b",
            "a\\b",
            "C:outside",
            "NUL",
            "con.txt",
            "CONIN$",
            "CONOUT$.txt",
            "CON .txt",
            "LPT1.pdf",
            "COM¹.txt",
            "ends.",
            "ends ",
            " starts",
            "bad\x00name",
            "name\ud800",
        ):
            for field in ("course", "filename"):
                with self.subTest(value=repr(unsafe), field=field):
                    values = dict(id="101", course="sample", filename="lecture.txt", url="fixture")
                    values[field] = unsafe
                    result = self.run_one(Material(**values), dry_run=True)
                    self.assertEqual(result["items"][0]["error_code"], "UNSAFE_NAME")
        self.fetch.assert_not_called()
        self.assertFalse(self.workspace.exists())

    def test_invalid_material_type_and_identifier_are_reported(self):
        result = self.engine.run(
            [
                None,
                Material("", "sample", "a.txt", "fixture"),
                Material("\ud800", "sample", "a.txt", "fixture"),
            ],
            dry_run=True,
        )
        self.assertEqual(result["counts"]["failed"], 3)
        self.assertTrue(all(item["error_code"] == "INVALID_MATERIAL" for item in result["items"]))
        self.assertIsNone(result["items"][2]["id"])
        json.dumps(result, ensure_ascii=False).encode("utf-8")

    def test_workspace_symlink_is_rejected(self):
        outside = self.parent / "outside"
        outside.mkdir()
        self.symlink(self.workspace, outside, directory=True)
        self.assert_workspace_error("UNSAFE_WORKSPACE", self.run_one)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_in_ancestor_chain_is_rejected(self):
        outside = self.parent / "outside"
        outside.mkdir()
        alias = self.parent / "alias"
        self.symlink(alias, outside, directory=True)
        engine = SyncEngine(alias / "nested", self.fetch)
        self.assert_workspace_error("UNSAFE_WORKSPACE", lambda: engine.run([self.material]))
        self.assertFalse((outside / "nested").exists())

    def test_symlinked_files_directory_is_rejected_without_touching_target(self):
        self.workspace.mkdir()
        outside = self.parent / "outside"
        outside.mkdir()
        self.symlink(self.workspace / "files", outside, directory=True)
        self.assert_workspace_error("UNSAFE_WORKSPACE", self.run_one)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_state_is_rejected(self):
        self.workspace.mkdir()
        outside = self.parent / "outside.json"
        payload = b'{"schema_version":1,"materials":{}}'
        outside.write_bytes(payload)
        self.symlink(self.workspace / "state.json", outside)
        self.assert_workspace_error("UNSAFE_WORKSPACE", self.run_one)
        self.assertEqual(outside.read_bytes(), payload)
        self.fetch.assert_not_called()

    def test_symlinked_material_is_rejected(self):
        self.run_one()
        path = self.current()
        path.unlink()
        outside = self.parent / "outside.txt"
        outside.write_bytes(b"external")
        self.symlink(path, outside)
        self.assert_workspace_error("UNSAFE_WORKSPACE", self.run_one)
        self.assertEqual(outside.read_bytes(), b"external")

    def test_history_corruption_blocks_update_without_losing_current(self):
        self.run_one()
        self.fetch.return_value = b"second revision"
        self.run_one()
        first_history = self.workspace / self.record()["history"][0]["path"]
        first_history.write_bytes(b"corrupt")
        self.fetch.return_value = b"first revision\n"
        self.run_one()
        old_state = (self.workspace / "state.json").read_bytes()
        self.fetch.return_value = b"third revision"
        result = self.run_one()
        self.assertEqual(result["items"][0]["error_code"], "HISTORY_CONFLICT")
        self.assertEqual((self.workspace / "state.json").read_bytes(), old_state)
        self.assertEqual(self.current().read_bytes(), b"first revision\n")

    def test_invalid_input_iterator_does_not_touch_workspace(self):
        def broken():
            yield self.material
            raise RuntimeError("private detail")

        self.assert_workspace_error("INVALID_INPUT", lambda: self.engine.run(broken()))
        self.assertFalse(self.workspace.exists())
        self.fetch.assert_not_called()

    def test_invalid_size_limit_is_rejected(self):
        for value in (0, -1, True, "50"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SyncEngine(self.workspace, self.fetch, max_bytes=value)


if __name__ == "__main__":
    unittest.main()

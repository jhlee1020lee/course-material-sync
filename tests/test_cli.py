import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from course_material_sync.canvas import AuthRequired
from course_material_sync.cli import _sync_canvas_source, _workspace_path, main
from course_material_sync.config import ConfigError
from course_material_sync.models import Material


class CliTests(unittest.TestCase):
    def test_workspace_root_alias_is_rejected(self):
        alias = Path(Path.cwd().anchor) / "synthetic-unused-directory" / ".."
        with self.assertRaises(ConfigError):
            _workspace_path(alias)

    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(arguments + ["--json"])
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_demo_revision_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            args = ["demo", "--workspace", str(Path(directory) / "workspace")]
            code, result, _ = self.invoke(args)
            self.assertEqual(code, 0)
            self.assertEqual(result["counts"]["added"], 2)
            code, result, _ = self.invoke(args)
            self.assertEqual(result["counts"]["unchanged"], 2)
            code, result, _ = self.invoke(args + ["--revision", "2"])
            self.assertEqual(result["counts"]["updated"], 1)
            self.assertEqual(result["counts"]["unchanged"], 1)

    def test_demo_dry_run_does_not_create_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "absent"
            code, result, _ = self.invoke(["demo", "--workspace", str(workspace), "--dry-run"])
            self.assertEqual(code, 0)
            self.assertEqual(result["counts"]["planned"], 2)
            self.assertFalse(workspace.exists())

    def test_private_exception_text_is_not_emitted(self):
        with patch(
            "course_material_sync.cli._canvas_command",
            side_effect=RuntimeError("https://private.example.com/?credential=do-not-print"),
        ):
            code, result, stderr = self.invoke(["run", "--config", "unused.json"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error_code"], "operation_failed")
        self.assertNotIn("do-not-print", json.dumps(result) + stderr)

    def test_auth_has_distinct_exit_code(self):
        with patch("course_material_sync.cli._canvas_command", side_effect=AuthRequired()):
            code, result, _ = self.invoke(["run", "--config", "unused.json"])
        self.assertEqual(code, 3)
        self.assertEqual(result["error_code"], "authentication_required")

    def test_expired_login_during_fetch_stops_further_requests(self):
        source = Mock()
        source.fetch.side_effect = AuthRequired()
        materials = [
            Material(str(i), "demo", f"note-{i}.txt", "https://canvas.example.com/file")
            for i in (1, 2)
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = _sync_canvas_source(
                Path(directory), source, materials, max_bytes=1000, dry_run=False
            )
        self.assertEqual(result["error_code"], "authentication_required")
        self.assertEqual(result["counts"]["failed"], 2)
        self.assertEqual(source.fetch.call_count, 1)
        with patch("course_material_sync.cli._canvas_command", return_value=result):
            code, emitted, _ = self.invoke(["run", "--config", "unused.json"])
        self.assertEqual(code, 3)
        self.assertEqual(emitted["counts"]["failed"], 2)

    def test_invalid_config_does_not_dump_original_error(self):
        code, result, _ = self.invoke(["run", "--config", "missing-config.local.json"])
        self.assertEqual(code, 2)
        self.assertEqual(result["error_code"], "config_unreadable")


if __name__ == "__main__":
    unittest.main()

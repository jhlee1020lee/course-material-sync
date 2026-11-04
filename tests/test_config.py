import json
import tempfile
import unittest
from pathlib import Path

from course_material_sync.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def load(self, **overrides):
        value = {"base_url": "https://canvas.example.com", "courses": [{"id": 101, "slug": "test"}]}
        value.update(overrides)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return load_config(path)

    def test_defaults(self):
        self.assertEqual(self.load().max_bytes, 50 * 1024 * 1024)

    def test_reject_unknown_fields_and_secrets(self):
        with self.assertRaises(ConfigError):
            self.load(password="synthetic-placeholder")

    def test_reject_non_origin_urls(self):
        for url in (
            "http://canvas.example.com",
            "https://user:pass@canvas.example.com",
            "https://canvas.example.com/?token=placeholder",
            "https://canvas.example.com/api",
            "https://canvas.example.com:8443",
        ):
            with self.subTest(url=url), self.assertRaises(ConfigError):
                self.load(base_url=url)

    def test_course_ids_slugs_and_duplicates(self):
        for courses in (
            [{"id": True, "slug": "test"}],
            [{"id": 1, "slug": "../escape"}],
            [{"id": 1, "slug": "nul"}],
            [{"id": 1, "slug": "one"}, {"id": 1, "slug": "two"}],
        ):
            with self.subTest(courses=courses), self.assertRaises(ConfigError):
                self.load(courses=courses)

    def test_no_wildcard_download_hosts(self):
        with self.assertRaises(ConfigError):
            self.load(allowed_download_hosts=["*.example.com"])

    def test_limits_are_bounded_integers(self):
        for limit in (0, 1025, "10", True):
            with self.subTest(limit=limit), self.assertRaises(ConfigError):
                self.load(max_download_mb=limit)


if __name__ == "__main__":
    unittest.main()

"""Strict, data-only configuration; no passwords or arbitrary code hooks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Course:
    id: int
    slug: str


@dataclass(frozen=True)
class Config:
    base_url: str
    courses: tuple[Course, ...]
    allowed_download_hosts: tuple[str, ...] = ()
    max_bytes: int = 50 * 1024 * 1024


def load_config(path: Path) -> Config:
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ConfigError("config_too_large")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError("config_unreadable") from exc
    if not isinstance(data, dict) or set(data) - {
        "base_url",
        "courses",
        "allowed_download_hosts",
        "max_download_mb",
    }:
        raise ConfigError("config_unknown_fields")
    base = data.get("base_url")
    if not isinstance(base, str):
        raise ConfigError("base_url_required")
    try:
        url = urlsplit(base)
        port = url.port
    except ValueError as exc:
        raise ConfigError("invalid_base_url") from exc
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
        or port not in (None, 443)
    ):
        raise ConfigError("base_url_must_be_https_origin")
    courses = data.get("courses")
    if not isinstance(courses, list) or not courses:
        raise ConfigError("courses_required")
    parsed = []
    ids, slugs = set(), set()
    reserved = {"con", "prn", "aux", "nul"} | {
        f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(1, 10)
    }
    for item in courses:
        if not isinstance(item, dict) or set(item) != {"id", "slug"}:
            raise ConfigError("invalid_course_fields")
        course_id, slug = item["id"], item["slug"]
        if type(course_id) is not int or course_id <= 0:
            raise ConfigError("invalid_course_id")
        if (
            not isinstance(slug, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", slug)
            or slug in reserved
        ):
            raise ConfigError("invalid_course_slug")
        if course_id in ids or slug in slugs:
            raise ConfigError("duplicate_course")
        ids.add(course_id)
        slugs.add(slug)
        parsed.append(Course(course_id, slug))
    hosts = data.get("allowed_download_hosts", [])
    if not isinstance(hosts, list) or any(
        not isinstance(host, str)
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
        or ".." in host
        for host in hosts
    ):
        raise ConfigError("invalid_download_hosts")
    mb = data.get("max_download_mb", 50)
    if type(mb) is not int or not 1 <= mb <= 1024:
        raise ConfigError("invalid_download_limit")
    return Config(base.rstrip("/"), tuple(parsed), tuple(hosts), mb * 1024 * 1024)

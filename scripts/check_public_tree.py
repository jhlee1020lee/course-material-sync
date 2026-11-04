"""Check the explicitly tracked public tree, without scanning ignored runtime data."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {
    ".gitignore",
    ".gitattributes",
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "MANIFEST.in",
}
DIRECTORIES = {"src", "tests", "examples", "scripts", "docs", ".github"}
EXTENSIONS = {".py", ".md", ".json", ".yml", ".yaml", ".toml"}
RULES = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    "personal_windows_path": re.compile(r"[A-Za-z]:[/\\]Users[/\\][^\s\"']+", re.I),
    "personal_unix_path": re.compile(r"/(?:Users|home)/[a-zA-Z0-9_.-]+/"),
    "real_school_email": re.compile(r"[a-zA-Z0-9_.+-]+@(?:[a-zA-Z0-9.-]+\.)?(?:ac\.kr|edu)\b"),
}


def main() -> int:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = [Path(value.decode("utf-8")) for value in result.stdout.split(b"\0") if value]
    if not paths:
        print("No tracked files to inspect. Stage the reviewed public files first.")
        return 1
    errors = []
    for relative in paths:
        path = ROOT / relative
        if relative.parts[0] not in DIRECTORIES and relative.as_posix() not in TOP_FILES:
            errors.append((relative, "unapproved_path"))
        if len(relative.parts) > 1 and relative.suffix not in EXTENSIONS:
            errors.append((relative, "unapproved_file_type"))
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            errors.append((relative, "linked_path"))
            continue
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            errors.append((relative, "missing_or_large_file"))
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append((relative, "non_text_file"))
            continue
        for rule, pattern in RULES.items():
            if pattern.search(content):
                errors.append((relative, rule))
    for path, rule in errors:
        print(f"{path.as_posix()}: {rule}")  # Never print the matched secret.
    if errors:
        return 1
    print(f"Public-tree checks passed for {len(paths)} tracked text files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

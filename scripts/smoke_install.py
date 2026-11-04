"""Install the built wheel in a clean environment and exercise the public entry point."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    wheels = list((ROOT / "dist").glob("course_material_sync-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Build exactly one wheel before running the installation check.")
    with zipfile.ZipFile(wheels[0]) as wheel:
        for name in wheel.namelist():
            if not (name.startswith("course_material_sync/") or ".dist-info/" in name):
                raise SystemExit("Unexpected wheel member")
            if name.endswith((".json", ".log", ".sqlite", ".db")):
                raise SystemExit("Runtime data must not be packaged")
    with tempfile.TemporaryDirectory(prefix="course-sync-install-") as temp:
        folder = Path(temp)
        environment = folder / "venv"
        venv.create(environment, with_pip=True)
        binary = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        command = binary / ("course-sync.exe" if os.name == "nt" else "course-sync")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])],
            cwd=folder,
            check=True,
        )
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("PYTHONHOME", None)
        clean_env["PYTHONUTF8"] = "1"
        args = [str(command), "demo", "--workspace", str(folder / "workspace"), "--json"]
        results = []
        for extra in ([], [], ["--revision", "2"]):
            process = subprocess.run(
                args + extra,
                cwd=folder,
                env=clean_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            results.append(json.loads(process.stdout))
        assert results[0]["counts"]["added"] == 2
        assert results[1]["counts"]["unchanged"] == 2
        assert results[2]["counts"]["updated"] == 1
        assert results[2]["counts"]["unchanged"] == 1
    print("Clean wheel install and demo passed without optional dependencies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

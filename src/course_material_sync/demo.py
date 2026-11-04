"""Generated public examples. No LMS account, source files, or network required."""

from __future__ import annotations

from pathlib import Path

from .models import Material
from .sync import SyncEngine


def run_demo(workspace: Path, *, revision: int = 1, dry_run: bool = False) -> dict:
    contents = {
        "lesson-01": b"Sample lesson: functions map inputs to outputs.\n",
        "lesson-02": (
            b"Sample lesson: sets contain distinct elements.\n"
            if revision == 1
            else b"Sample lesson: sets contain distinct elements.\nRevision 2: the empty set.\n"
        ),
    }
    materials = [
        Material(key, "demo-course", key + ".txt", "https://canvas.example.com/files/" + key)
        for key in contents
    ]
    return SyncEngine(workspace, lambda material: contents[material.id]).run(
        materials, dry_run=dry_run
    )

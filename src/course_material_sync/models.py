"""Public metadata passed to the synchronizer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    id: str
    course: str
    filename: str
    url: str
    updated_at: str | None = None

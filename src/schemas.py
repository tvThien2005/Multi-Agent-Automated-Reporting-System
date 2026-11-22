"""Shared serializable data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryResult:
    rows: list[dict[str, Any]]
    truncated: bool

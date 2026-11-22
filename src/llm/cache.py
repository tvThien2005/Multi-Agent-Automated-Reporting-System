"""Small deterministic on-disk cache for LLM completions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class FileCache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, key: dict[str, Any]) -> Path:
        digest = hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, key: dict[str, Any]) -> str | None:
        path = self._path(key)
        return json.loads(path.read_text(encoding="utf-8"))["content"] if path.exists() else None

    def put(self, key: dict[str, Any], content: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps({"content": content}), encoding="utf-8")

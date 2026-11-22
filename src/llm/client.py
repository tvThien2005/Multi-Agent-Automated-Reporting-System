"""OpenAI-compatible LLM client with retry, caching and structured parsing."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from src.llm.cache import FileCache


T = TypeVar("T", bound=BaseModel)
Message = dict[str, str]
Transport = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class CompletionMetadata:
    cached: bool
    latency_seconds: float


class LLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
        cache_directory: Path = Path("eval/cache"),
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.cache = FileCache(cache_directory)
        self.transport = transport or self._http_transport

    def _http_transport(self, payload: dict[str, Any]) -> str:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1200,
        retries: int = 2,
        use_cache: bool = True,
        json_mode: bool = False,
    ) -> tuple[str, CompletionMetadata]:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        key = {"url": self.base_url, **payload}
        if use_cache and (cached := self.cache.get(key)) is not None:
            return cached, CompletionMetadata(cached=True, latency_seconds=0.0)
        started = time.perf_counter()
        for attempt in range(retries + 1):
            try:
                content = self.transport(payload)
                if use_cache:
                    self.cache.put(key, content)
                return content, CompletionMetadata(cached=False, latency_seconds=time.perf_counter() - started)
            except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
                retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code in {429, 500, 502, 503, 504}
                if attempt >= retries or not retryable:
                    raise RuntimeError(f"LLM request failed: {exc}") from exc
                time.sleep((2**attempt) + random.uniform(0, 0.2))
        raise AssertionError("unreachable")

    def complete_structured(self, model_type: type[T], messages: list[Message], **kwargs: Any) -> T:
        content, _ = self.complete(messages, json_mode=True, **kwargs)
        return model_type.model_validate_json(content)

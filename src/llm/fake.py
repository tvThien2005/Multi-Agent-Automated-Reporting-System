"""Deterministic LLM fake for agent tests."""

from __future__ import annotations

from collections import deque

from src.llm.client import CompletionMetadata, Message


class FakeLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = deque(responses)
        self.calls: list[list[Message]] = []

    def complete(self, messages: list[Message], **_: object) -> tuple[str, CompletionMetadata]:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("FakeLLMClient has no remaining response.")
        return self.responses.popleft(), CompletionMetadata(cached=False, latency_seconds=0.0)

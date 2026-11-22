import urllib.error

from pydantic import BaseModel

from src.llm.client import LLMClient


class Answer(BaseModel):
    answer: str


def test_cache_and_structured_output(tmp_path) -> None:
    calls = []

    def transport(_: dict) -> str:
        calls.append(1)
        return '{"answer":"ok"}'

    client = LLMClient(base_url="https://example.test", api_key="key", model="model", cache_directory=tmp_path, transport=transport)
    assert client.complete_structured(Answer, [{"role": "user", "content": "x"}]).answer == "ok"
    assert client.complete_structured(Answer, [{"role": "user", "content": "x"}]).answer == "ok"
    assert len(calls) == 1


def test_retries_transient_failure(tmp_path) -> None:
    attempts = []

    def transport(_: dict) -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.URLError("offline")
        return "done"

    client = LLMClient(base_url="https://example.test", api_key="key", model="model", cache_directory=tmp_path, transport=transport)
    content, _ = client.complete([{"role": "user", "content": "x"}], retries=1, use_cache=False)
    assert content == "done"
    assert len(attempts) == 2

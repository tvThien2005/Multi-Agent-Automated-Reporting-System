"""One-shot Text-to-SQL baseline.

This module deliberately makes exactly one model request for each question.  It
does not retry, repair SQL, or call a second model to classify answerability.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.llm.client import LLMClient


SYSTEM_PROMPT = """You are a PostgreSQL Text-to-SQL assistant for an e-commerce
database. Answer using only the supplied schema. Return exactly one JSON object,
with no Markdown or commentary, in this shape:
{"answerable": true, "sql": "SELECT ...", "reason": null}
or
{"answerable": false, "sql": null, "reason": "Lý do bằng tiếng Việt"}

Rules:
- Use PostgreSQL syntax. The DDL was authored with unquoted camelCase names;
  PostgreSQL stores those physical identifiers in lowercase. Therefore use the
  lowercase names (for example ngaydat, trangthai, donhangid) without quotes.
- Produce exactly one read-only SELECT query when answerable. A WITH ... SELECT
  query is allowed.
- Never invent a table, column, business metric, or value not present in schema.
- If the question is ambiguous or cannot be answered from the schema, set
  answerable to false and do not write SQL.
"""


@dataclass(frozen=True)
class BaselineAnswer:
    answerable: bool
    sql: str | None
    reason: str | None
    raw_content: str


class BaselineResponseError(ValueError):
    """The model response was not the required JSON contract."""


class OpenAICompatibleClient:
    """Minimal Chat Completions client for Groq/OpenAI-compatible providers."""

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout_seconds: int = 60) -> None:
        if not api_key:
            raise ValueError("BASELINE_API_KEY is required.")
        if not base_url:
            raise ValueError("BASELINE_BASE_URL is required.")
        if not model:
            raise ValueError("BASELINE_MODEL is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = LLMClient(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
        )

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleClient":
        from src.config import get_model_config

        model = get_model_config("baseline_sql")
        return cls(
            api_key=model.api_key,
            base_url=model.base_url,
            model=model.model,
            timeout_seconds=model.timeout_seconds,
        )

    def complete_once(self, *, schema_context: str, question_vi: str) -> str:
        """Make the baseline's sole LLM request for one question."""
        content, _ = self.client.complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Schema PostgreSQL:\n{schema_context}\n\nCâu hỏi: {question_vi}"},
            ],
            temperature=0,
            max_tokens=1200,
            retries=0,
            json_mode=True,
        )
        return content


def read_schema_context(schema_file: Path) -> str:
    """Use the checked-in DDL as a reproducible baseline schema context."""
    return schema_file.read_text(encoding="utf-8")


def parse_baseline_answer(raw_content: str) -> BaselineAnswer:
    """Validate the single structured response returned by the provider."""
    candidate = raw_content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)
    try:
        data: dict[str, Any] = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise BaselineResponseError("Model did not return valid JSON.") from exc

    answerable = data.get("answerable")
    sql = data.get("sql")
    reason = data.get("reason")
    if not isinstance(answerable, bool):
        raise BaselineResponseError("Field 'answerable' must be boolean.")
    if sql is not None and not isinstance(sql, str):
        raise BaselineResponseError("Field 'sql' must be a string or null.")
    if reason is not None and not isinstance(reason, str):
        raise BaselineResponseError("Field 'reason' must be a string or null.")
    if answerable and not sql:
        raise BaselineResponseError("An answerable result requires SQL.")
    if not answerable and sql is not None:
        raise BaselineResponseError("A refusal must not contain SQL.")
    if not answerable and not reason:
        raise BaselineResponseError("A refusal requires a reason.")
    return BaselineAnswer(answerable=answerable, sql=sql, reason=reason, raw_content=raw_content)

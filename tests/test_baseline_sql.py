import pytest

from src.agents.baseline_sql import BaselineResponseError, parse_baseline_answer


def test_parses_answerable_structured_response() -> None:
    result = parse_baseline_answer('{"answerable": true, "sql": "SELECT 1", "reason": null}')
    assert result.answerable is True
    assert result.sql == "SELECT 1"


def test_parses_refusal_structured_response() -> None:
    result = parse_baseline_answer('{"answerable": false, "sql": null, "reason": "Thiếu dữ liệu"}')
    assert result.answerable is False
    assert result.reason == "Thiếu dữ liệu"


def test_rejects_sql_on_refusal() -> None:
    with pytest.raises(BaselineResponseError, match="must not contain SQL"):
        parse_baseline_answer('{"answerable": false, "sql": "SELECT 1", "reason": "x"}')

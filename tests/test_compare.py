from datetime import date
from decimal import Decimal

from src.eval.compare import results_match


def test_compares_rows_as_multiset_by_default() -> None:
    assert results_match([{"a": 1}, {"a": 1}, {"a": 2}], [{"a": 2}, {"a": 1}, {"a": 1}])


def test_compares_row_order_when_requested() -> None:
    assert not results_match([{"a": 1}, {"a": 2}], [{"a": 2}, {"a": 1}], order_matters=True)


def test_normalizes_decimal_date_and_null() -> None:
    assert results_match(
        [{"amount": Decimal("1.23456"), "day": date(2026, 10, 1), "value": None}],
        [{"amount": 1.23455, "day": "2026-10-01", "value": None}],
    )

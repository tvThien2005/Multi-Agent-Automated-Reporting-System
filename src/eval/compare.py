"""Deterministic comparison for Text-to-SQL result sets."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence


def normalize_value(value: Any, *, decimal_places: int = 4) -> Any:
    """Convert DB values to stable, JSON-like values before comparison."""
    if isinstance(value, Decimal):
        # Convert after rounding so Decimal and psycopg's occasional float
        # representation compare by the same four-decimal evaluation policy.
        return float(round(value, decimal_places))
    if isinstance(value, float):
        return round(value, decimal_places)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def normalize_rows(
    rows: Iterable[Mapping[str, Any] | Sequence[Any]],
    *,
    ignore_column_order: bool = False,
    decimal_places: int = 4,
) -> list[tuple[Any, ...]]:
    """Normalize rows, retaining duplicate rows for multiset comparison."""
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        values = row.values() if isinstance(row, Mapping) else row
        item = tuple(normalize_value(value, decimal_places=decimal_places) for value in values)
        normalized.append(tuple(sorted(item, key=repr)) if ignore_column_order else item)
    return normalized


def results_match(
    expected_rows: Iterable[Mapping[str, Any] | Sequence[Any]],
    actual_rows: Iterable[Mapping[str, Any] | Sequence[Any]],
    *,
    order_matters: bool = False,
    ignore_column_order: bool = False,
    decimal_places: int = 4,
) -> bool:
    """Compare result rows as a sequence or a multiset, as configured."""
    expected = normalize_rows(
        expected_rows,
        ignore_column_order=ignore_column_order,
        decimal_places=decimal_places,
    )
    actual = normalize_rows(
        actual_rows,
        ignore_column_order=ignore_column_order,
        decimal_places=decimal_places,
    )
    return expected == actual if order_matters else Counter(expected) == Counter(actual)

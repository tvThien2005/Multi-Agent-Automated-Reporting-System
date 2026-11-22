import pytest

from src.safety.executor import QueryErrorCode, QueryExecutionError, ReadOnlyExecutor
from src.safety.sql_guard import UnsafeSQLError


pytestmark = pytest.mark.db


def _executor(*, max_rows: int = 1_000, timeout_ms: int = 10_000) -> ReadOnlyExecutor:
    return ReadOnlyExecutor(allowed_tables={"don_hang"}, max_rows=max_rows, timeout_ms=timeout_ms)


def test_executor_serializes_and_truncates_rows() -> None:
    result = _executor(max_rows=2).execute("SELECT id, tongtien, ngaydat FROM don_hang ORDER BY id")
    assert len(result.rows) == 2
    assert result.truncated is True
    assert isinstance(result.rows[0]["tongtien"], float)
    assert result.rows[0]["ngaydat"].startswith("2025-")


def test_executor_classifies_bad_column() -> None:
    with pytest.raises(QueryExecutionError) as error:
        _executor().execute("SELECT missing_column FROM don_hang")
    assert error.value.code == QueryErrorCode.SQL_ERROR


def test_executor_enforces_statement_timeout() -> None:
    with pytest.raises(QueryExecutionError) as error:
        _executor(timeout_ms=1).execute("SELECT COUNT(*) FROM don_hang a CROSS JOIN don_hang b")
    assert error.value.code == QueryErrorCode.TIMEOUT


def test_executor_never_sends_writes_to_database() -> None:
    with pytest.raises(UnsafeSQLError):
        _executor().execute("DELETE FROM don_hang")

"""Single read-only database execution path used by baseline evaluation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.safety.sql_guard import validate_readonly_sql
from src.schemas import QueryResult
from src.config import get_database_config, get_safety_config


class QueryErrorCode(StrEnum):
    SQL_ERROR = "SQL_ERROR"
    TIMEOUT = "TIMEOUT"
    DATABASE_ERROR = "DATABASE_ERROR"


class QueryExecutionError(RuntimeError):
    def __init__(self, code: QueryErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class ReadOnlyExecutor:
    def __init__(
        self,
        *,
        allowed_tables: set[str],
        max_rows: int = 1_000,
        timeout_ms: int = 10_000,
        connection_kwargs: dict[str, object] | None = None,
    ) -> None:
        self.allowed_tables = allowed_tables
        self.max_rows = max_rows
        self.timeout_ms = timeout_ms
        if connection_kwargs is None:
            database = get_database_config()
            connection_kwargs = {
                "host": database.host,
                "port": database.port,
                "dbname": database.database,
                "user": database.reader_user,
                "password": database.reader_password,
            }
        self.connection_kwargs = connection_kwargs

    @classmethod
    def from_environment(cls, *, allowed_tables: set[str]) -> "ReadOnlyExecutor":
        safety = get_safety_config()
        return cls(
            allowed_tables=allowed_tables,
            max_rows=safety.max_rows,
            timeout_ms=safety.statement_timeout_ms,
        )

    def execute(self, sql: str) -> QueryResult:
        validated = validate_readonly_sql(sql, allowed_tables=self.allowed_tables)
        connection = psycopg2.connect(**self.connection_kwargs)
        try:
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                try:
                    cursor.execute("SET LOCAL statement_timeout = %s", (self.timeout_ms,))
                    cursor.execute(validated.sql)
                    fetched = cursor.fetchmany(self.max_rows + 1)
                except psycopg2.errors.QueryCanceled as exc:
                    raise QueryExecutionError(QueryErrorCode.TIMEOUT, "Query exceeded statement timeout.") from exc
                except psycopg2.ProgrammingError as exc:
                    raise QueryExecutionError(QueryErrorCode.SQL_ERROR, str(exc).strip()) from exc
                except psycopg2.Error as exc:
                    raise QueryExecutionError(QueryErrorCode.DATABASE_ERROR, str(exc).strip()) from exc
                rows = [{key: _serialize(value) for key, value in dict(row).items()} for row in fetched[: self.max_rows]]
                return QueryResult(rows=rows, truncated=len(fetched) > self.max_rows)
        finally:
            connection.close()

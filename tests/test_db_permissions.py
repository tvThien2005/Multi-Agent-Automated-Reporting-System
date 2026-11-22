"""Integration tests for the least-privilege SQL-agent database role."""

from __future__ import annotations

import psycopg2
import pytest


pytestmark = pytest.mark.db


def test_reader_can_select_and_has_readonly_defaults(reader_connection) -> None:
    with reader_connection.cursor() as cursor:
        cursor.execute("SHOW default_transaction_read_only")
        assert cursor.fetchone()[0] == "on"

        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == "10s"

        cursor.execute("SELECT COUNT(*) FROM don_hang")
        assert cursor.fetchone()[0] == 20_000


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO khu_vuc (tenkhuvuc) VALUES ('pytest-permission-probe')",
        "UPDATE khu_vuc SET tenkhuvuc = tenkhuvuc WHERE FALSE",
        "DELETE FROM khu_vuc WHERE FALSE",
        "CREATE TABLE pytest_permission_probe (id integer)",
        "DROP TABLE IF EXISTS pytest_permission_probe",
    ],
)
def test_reader_cannot_write_or_change_schema(reader_connection, statement: str) -> None:
    with reader_connection.cursor() as cursor:
        with pytest.raises(psycopg2.Error) as error:
            cursor.execute(statement)
    assert "read-only" in str(error.value).lower() or "permission denied" in str(error.value).lower()

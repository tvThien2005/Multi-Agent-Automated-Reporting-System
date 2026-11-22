import pytest

from src.safety.sql_guard import UnsafeSQLError, validate_readonly_sql


def test_allows_cte_select_over_allowed_table() -> None:
    validated = validate_readonly_sql(
        "WITH monthly AS (SELECT * FROM don_hang) SELECT * FROM monthly",
        allowed_tables={"don_hang"},
    )
    assert validated.sql.startswith("WITH monthly")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM don_hang",
        "INSERT INTO don_hang VALUES (1)",
        "UPDATE don_hang SET tongtien = 0",
        "CREATE TABLE x (id int)",
        "DROP TABLE don_hang",
        "ALTER TABLE don_hang ADD x int",
        "SELECT pg_sleep(1)",
        "SELECT pg_read_file('x')",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM unknown_table",
        "SELECT * FROM don_hang FOR UPDATE",
        "SELECT 1; SELECT 2",
        "WITH x AS (DELETE FROM don_hang RETURNING id) SELECT * FROM x",
        "SELECT * INTO copied FROM don_hang",
    ],
)
def test_blocks_write_and_dangerous_function(sql: str) -> None:
    with pytest.raises(UnsafeSQLError):
        validate_readonly_sql(sql, allowed_tables={"don_hang"})


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM don_hang",
        "SELECT * FROM don_hang WHERE trangthai ILIKE '%giao%'",
        "SELECT COUNT(*) FROM don_hang",
        "SELECT ROW_NUMBER() OVER (ORDER BY id) FROM don_hang",
        "WITH x AS (SELECT id FROM don_hang) SELECT * FROM x",
        "SELECT id::text FROM don_hang",
        "SELECT * FROM don_hang UNION SELECT * FROM don_hang",
        "SELECT * FROM don_hang WHERE id IN (SELECT id FROM don_hang)",
        "SELECT CASE WHEN id > 0 THEN id END FROM don_hang",
        "SELECT DISTINCT trangthai FROM don_hang",
    ],
)
def test_allows_readonly_postgres_queries(sql: str) -> None:
    assert validate_readonly_sql(sql, allowed_tables={"don_hang"}).sql == sql

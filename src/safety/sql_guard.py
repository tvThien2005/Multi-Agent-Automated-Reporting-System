"""AST-based read-only SQL validation for PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class UnsafeSQLError(ValueError):
    """SQL violates VietReport's read-only evaluation policy."""


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str


_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Set,
    exp.Into,
)
_BLOCKED_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "lo_import",
    "lo_export",
    "dblink",
    "set_config",
    "pg_terminate_backend",
    "pg_cancel_backend",
}


def validate_readonly_sql(sql: str, *, allowed_tables: set[str]) -> ValidatedSQL:
    """Permit one SELECT/UNION query over the explicitly allowed tables only."""
    try:
        statements = parse(sql, read="postgres")
    except ParseError as exc:
        raise UnsafeSQLError("SQL_PARSE_ERROR") from exc
    if len(statements) != 1:
        raise UnsafeSQLError("MULTIPLE_STATEMENTS")
    expression = statements[0]
    if not isinstance(expression, (exp.Select, exp.Union)):
        raise UnsafeSQLError("NOT_A_SELECT")

    cte_names = {cte.alias_or_name for cte in expression.find_all(exp.CTE)}
    for node in expression.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise UnsafeSQLError(f"FORBIDDEN_NODE:{node.key}")
        if isinstance(node, exp.Table):
            if node.db or node.catalog:
                raise UnsafeSQLError("EXTERNAL_SCHEMA")
            if node.name not in allowed_tables and node.name not in cte_names:
                raise UnsafeSQLError(f"TABLE_NOT_ALLOWED:{node.name}")
        if isinstance(node, exp.Func):
            name = (node.name or node.sql_name()).lower()
            if name in _BLOCKED_FUNCTIONS:
                raise UnsafeSQLError(f"FORBIDDEN_FUNCTION:{name}")
    if expression.args.get("locks"):
        raise UnsafeSQLError("LOCKING_SELECT")
    return ValidatedSQL(sql=sql)

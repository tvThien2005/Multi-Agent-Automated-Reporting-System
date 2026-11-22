from pathlib import Path

import pytest

from src.agents.schema_context import SchemaContextBuilder
from src.config import get_database_config


pytestmark = pytest.mark.db


def test_context_is_derived_from_database() -> None:
    database = get_database_config()
    builder = SchemaContextBuilder(
        {
            "host": database.host,
            "port": database.port,
            "dbname": database.database,
            "user": database.reader_user,
            "password": database.reader_password,
        },
        Path("configs/business_notes.md"),
    )
    context = builder.build({"don_hang", "thanh_toan"})
    assert "Table don_hang:" in context
    assert "ngaydat" in context
    assert "Table thanh_toan:" in context
    assert "sanphamid" in context
    assert "Đã hủy" in context


def test_full_context_contains_all_tables() -> None:
    database = get_database_config()
    context = SchemaContextBuilder(
        {
            "host": database.host,
            "port": database.port,
            "dbname": database.database,
            "user": database.reader_user,
            "password": database.reader_password,
        },
        Path("configs/business_notes.md"),
    ).build()
    assert context.count("Table ") == 13

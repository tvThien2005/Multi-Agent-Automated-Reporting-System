"""Shared fixtures for database-backed tests."""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg2
import pytest


def _connect(*, reader: bool) -> psycopg2.extensions.connection:
    settings = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB", "E-commerce"),
        "user": os.getenv(
            "POSTGRES_USER" if reader else "POSTGRES_ADMIN_USER",
            "vietreport_reader" if reader else "vietreport_admin",
        ),
        "password": os.getenv(
            "POSTGRES_PASSWORD" if reader else "POSTGRES_ADMIN_PASSWORD",
            "vietreport_reader_password" if reader else "vietreport_admin_password",
        ),
    }
    try:
        return psycopg2.connect(**settings)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL is unavailable for a db test: {exc}")


@pytest.fixture
def reader_connection() -> Iterator[psycopg2.extensions.connection]:
    connection = _connect(reader=True)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def admin_connection() -> Iterator[psycopg2.extensions.connection]:
    connection = _connect(reader=False)
    try:
        yield connection
    finally:
        connection.close()

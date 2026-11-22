"""Build a compact, database-derived Text-to-SQL schema context."""

from __future__ import annotations

from pathlib import Path

import psycopg2


class SchemaContextBuilder:
    def __init__(self, connection_kwargs: dict[str, object], business_notes: Path) -> None:
        self.connection_kwargs = connection_kwargs
        self.business_notes = business_notes

    def build(self, tables: set[str] | None = None) -> str:
        connection = psycopg2.connect(**self.connection_kwargs)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.table_name, c.column_name, c.data_type,
                           pgd.description
                    FROM information_schema.columns c
                    LEFT JOIN pg_catalog.pg_statio_all_tables st
                      ON st.schemaname = c.table_schema AND st.relname = c.table_name
                    LEFT JOIN pg_catalog.pg_description pgd
                      ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
                    WHERE c.table_schema = 'public'
                    ORDER BY c.table_name, c.ordinal_position
                    """
                )
                rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND data_type IN ('character varying', 'text')
                    ORDER BY table_name, column_name
                    """
                )
                categorical = cursor.fetchall()
                examples: dict[tuple[str, str], list[str]] = {}
                for table, column in categorical:
                    if tables is not None and table not in tables:
                        continue
                    cursor.execute(
                        f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 8"
                    )
                    values = [str(value[0]) for value in cursor.fetchall()]
                    if 1 < len(values) <= 8:
                        examples[(table, column)] = values
        finally:
            connection.close()

        grouped: dict[str, list[tuple[str, str, str | None]]] = {}
        for table, column, data_type, comment in rows:
            if tables is None or table in tables:
                grouped.setdefault(table, []).append((column, data_type, comment))
        rendered = ["Database uses lowercase physical identifiers; write names exactly as shown."]
        for table, columns in grouped.items():
            rendered.append(f"\nTable {table}:")
            for column, data_type, comment in columns:
                line = f"- {column}: {data_type}"
                if comment:
                    line += f" — {comment}"
                if (values := examples.get((table, column))):
                    line += f"; examples: {', '.join(values)}"
                rendered.append(line)
        rendered.append("\nBusiness notes:\n" + self.business_notes.read_text(encoding="utf-8").strip())
        return "\n".join(rendered)

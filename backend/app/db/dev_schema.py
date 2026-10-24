"""
Development-only schema sync.

`Base.metadata.create_all` creates missing tables but never alters existing ones, so a dev database
created before a model gained a column would break. This adds any missing columns in place.
It never drops or changes columns; production schema changes belong in Alembic migrations.
"""

import logging
from typing import List

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateColumn

from app.db.base import Base

logger = logging.getLogger(__name__)


def add_missing_columns(conn: Connection) -> List[str]:
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    added: List[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all handles new tables
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable and column.server_default is None:
                logger.warning(
                    f"Cannot auto-add NOT NULL column {table.name}.{column.name} without a server default; "
                    "recreate the dev database."
                )
                continue
            ddl = CreateColumn(column).compile(dialect=conn.dialect)
            conn.exec_driver_sql(f'ALTER TABLE {table.name} ADD COLUMN {ddl}')
            added.append(f"{table.name}.{column.name}")
    if added:
        logger.info(f"Dev schema sync added columns: {', '.join(added)}")
    return added

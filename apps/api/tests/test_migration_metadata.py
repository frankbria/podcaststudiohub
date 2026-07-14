"""
Alembic target metadata must match the migrated schema (issue #318).

env.py builds target_metadata from Base.metadata, which is only complete if
every model module has been imported. This test compares the table-name set
registered on Base.metadata (after importing the whole src.models package,
exactly as env.py now does) against the tables that actually exist in the
migrated test database. It fails in BOTH drift directions:

- a migration creates a table with no corresponding model import
  (the pre-#318 bug: the next `--autogenerate` would emit DROP TABLE), or
- a model exists whose table was never migrated.

A column-level autogenerate-clean assertion is deliberately NOT made here:
models are known to omit some real DB constraints (see #308), so only the
table set is compared.
"""

import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from src.database import Base
import src.models  # noqa: F401  — registers every model on Base.metadata

from tests.conftest import TEST_DATABASE_URL


def test_metadata_tables_match_migrated_schema():
	# Mirror env.py's driver normalization so any TEST_DATABASE_URL scheme works.
	sync_url = TEST_DATABASE_URL
	if sync_url.startswith("postgresql+asyncpg://"):
		sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
	elif sync_url.startswith("postgresql://"):
		sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://", 1)
	engine = sa.create_engine(sync_url, poolclass=NullPool)
	try:
		db_tables = set(sa.inspect(engine).get_table_names(schema="public"))
	finally:
		engine.dispose()
	db_tables.discard("alembic_version")

	model_tables = set(Base.metadata.tables)

	missing_models = db_tables - model_tables
	missing_migrations = model_tables - db_tables
	assert model_tables == db_tables, (
		f"model/migration drift — tables in DB with no model in metadata "
		f"(autogenerate would DROP them): {sorted(missing_models)}; "
		f"models with no migrated table: {sorted(missing_migrations)}"
	)

"""Add missing indexes for discriminator and status columns

Adds four B-tree indexes that are declared in the SQLAlchemy models with
``index=True`` but were omitted from the initial migration:

- ``idx_content_sources_source_type``      — extraction-router discriminator
- ``idx_content_sources_extraction_status`` — background-job status filter
- ``idx_distribution_targets_target_type`` — platform-routing discriminator
- ``idx_tts_configurations_provider``      — provider-selection lookup

Without these indexes, every query that filters on any of these columns
performs a full sequential scan, which becomes expensive as the tables grow.

Revision ID: 004
Revises: 003
Create Date: 2026-03-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES = [
	# ContentSource: extraction-router discriminator
	('idx_content_sources_source_type', 'content_sources', 'source_type'),
	# ContentSource: background-job status filter
	('idx_content_sources_extraction_status', 'content_sources', 'extraction_status'),
	# DistributionTarget: platform-routing discriminator
	('idx_distribution_targets_target_type', 'distribution_targets', 'target_type'),
	# TTSConfiguration: provider-selection lookup
	('idx_tts_configurations_provider', 'tts_configurations', 'provider'),
]


def upgrade() -> None:
	# These tables pre-exist and may hold data: build CONCURRENTLY so the
	# index build never blocks writes (issue #318). CONCURRENTLY cannot run
	# inside a transaction, hence the autocommit block. The DROP guards make
	# reruns safe — a failed CONCURRENTLY build leaves an INVALID index.
	with op.get_context().autocommit_block():
		for name, table, column in INDEXES:
			op.execute(f"DROP INDEX IF EXISTS {name}")
			op.create_index(
				name,
				table,
				[column],
				postgresql_using='btree',
				postgresql_concurrently=True,
			)


def downgrade() -> None:
	for name, table, _column in INDEXES:
		op.drop_index(name, table_name=table)

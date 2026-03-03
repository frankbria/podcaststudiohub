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


def upgrade() -> None:
	# ContentSource: extraction-router discriminator
	op.create_index(
		'idx_content_sources_source_type',
		'content_sources',
		['source_type'],
		postgresql_using='btree',
	)

	# ContentSource: background-job status filter
	op.create_index(
		'idx_content_sources_extraction_status',
		'content_sources',
		['extraction_status'],
		postgresql_using='btree',
	)

	# DistributionTarget: platform-routing discriminator
	op.create_index(
		'idx_distribution_targets_target_type',
		'distribution_targets',
		['target_type'],
		postgresql_using='btree',
	)

	# TTSConfiguration: provider-selection lookup
	op.create_index(
		'idx_tts_configurations_provider',
		'tts_configurations',
		['provider'],
		postgresql_using='btree',
	)


def downgrade() -> None:
	op.drop_index('idx_content_sources_source_type', table_name='content_sources')
	op.drop_index('idx_content_sources_extraction_status', table_name='content_sources')
	op.drop_index('idx_distribution_targets_target_type', table_name='distribution_targets')
	op.drop_index('idx_tts_configurations_provider', table_name='tts_configurations')

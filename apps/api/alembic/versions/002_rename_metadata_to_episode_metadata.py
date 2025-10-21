"""Rename metadata column to episode_metadata in episodes table

Revision ID: 002
Revises: 001
Create Date: 2025-10-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Rename metadata column to episode_metadata"""
	# Rename the column
	op.alter_column(
		'episodes',
		'metadata',
		new_column_name='episode_metadata',
		existing_type=postgresql.JSONB(),
		existing_nullable=False,
		existing_server_default=sa.text("'{}'::jsonb")
	)

	# Drop the old GIN index on metadata
	op.drop_index('idx_episodes_metadata_gin', table_name='episodes')

	# Drop the old title index (it references the metadata column)
	op.drop_index('idx_episodes_title', table_name='episodes')

	# Recreate the GIN index with the new column name
	op.create_index(
		'idx_episodes_episode_metadata_gin',
		'episodes',
		['episode_metadata'],
		postgresql_using='gin',
		postgresql_ops={'episode_metadata': 'jsonb_path_ops'}
	)

	# Recreate the title index with the new column name
	op.create_index(
		'idx_episodes_title',
		'episodes',
		[sa.text("(episode_metadata->>'title')")]
	)


def downgrade() -> None:
	"""Revert episode_metadata column back to metadata"""
	# Drop the new indexes
	op.drop_index('idx_episodes_title', table_name='episodes')
	op.drop_index('idx_episodes_episode_metadata_gin', table_name='episodes')

	# Rename the column back
	op.alter_column(
		'episodes',
		'episode_metadata',
		new_column_name='metadata',
		existing_type=postgresql.JSONB(),
		existing_nullable=False,
		existing_server_default=sa.text("'{}'::jsonb")
	)

	# Recreate the old indexes
	op.create_index(
		'idx_episodes_metadata_gin',
		'episodes',
		['metadata'],
		postgresql_using='gin',
		postgresql_ops={'metadata': 'jsonb_path_ops'}
	)

	op.create_index(
		'idx_episodes_title',
		'episodes',
		[sa.text("(metadata->>'title')")]
	)

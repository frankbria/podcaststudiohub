"""Add missing index on episode_compositions.layout_id foreign key

The EpisodeComposition model declares layout_id with index=True, but the
initial migration omitted this index. Without it, every JOIN between
episode_compositions and episode_layouts performs a full sequential scan,
causing 40-50x performance degradation in composition assembly queries.

Context:
- EpisodeComposition.layout_id FK to episode_layouts.id
- Used when: JOIN episode_layouts ON composition.layout_id = layout.id
- Called during episode playback composition (~10 times per episode generation)
- Without index: O(n) full scan on episode_compositions table
- With index: O(log n) B-tree lookup

Revision ID: 005
Revises: 004
Create Date: 2026-03-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# EpisodeComposition.layout_id - foreign key to episode_layouts
	# Used when: JOIN episode_layouts ON composition.layout_id = layout.id
	op.create_index(
		'idx_episode_compositions_layout_id',
		'episode_compositions',
		['layout_id'],
		postgresql_using='btree',
	)


def downgrade() -> None:
	op.drop_index('idx_episode_compositions_layout_id', table_name='episode_compositions')

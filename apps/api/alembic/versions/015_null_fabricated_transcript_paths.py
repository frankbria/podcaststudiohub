"""NULL out fabricated episode transcript_path values

Revision ID: 015
Revises: 014
Create Date: 2026-07-10 00:00:00.000000

The generation task used to derive transcript_path by string-substituting the
audio path (audio.mp3 -> audio_transcript.txt), a file podcastfy never wrote —
so every generated episode's transcript_path pointed at a non-existent file
(#309). New code persists NULL; this backfills existing rows. Real transcripts
written by the script-generation service are named "<episode_id>.xml" and are
untouched by the LIKE pattern.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.execute(
		r"""
		UPDATE episodes
		SET transcript_path = NULL
		WHERE transcript_path LIKE '%\_transcript.txt'
		"""
	)


def downgrade() -> None:
	# Data-only cleanup of values that were always dangling; nothing to restore.
	pass

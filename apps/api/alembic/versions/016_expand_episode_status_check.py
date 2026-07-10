"""Expand episodes_status_check to the full generation_status vocabulary

Revision ID: 016
Revises: 015
Create Date: 2026-07-10 00:00:00.000000

Migration 001 allowed only draft/queued/extracting/generating/synthesizing/
complete/failed, but the workflow also writes 'composing', 'uploading',
'distributing' (distribution callbacks and the in-task success recording from
issue #312), and 'distribution_failed' (on_workflow_complete, issue #300).
Those UPDATEs raised CheckViolation, which the callbacks swallow — so
per-platform distribution results were silently never recorded. This expands
the constraint to every status the code writes.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STATUSES = (
	"'draft', 'queued', 'extracting', 'generating', 'synthesizing', "
	"'complete', 'failed'"
)
NEW_STATUSES = (
	"'draft', 'queued', 'extracting', 'generating', 'synthesizing', "
	"'composing', 'uploading', 'distributing', 'distribution_failed', "
	"'complete', 'failed'"
)


def upgrade() -> None:
	op.drop_constraint("episodes_status_check", "episodes", type_="check")
	op.create_check_constraint(
		"episodes_status_check",
		"episodes",
		f"generation_status IN ({NEW_STATUSES})",
	)


def downgrade() -> None:
	op.drop_constraint("episodes_status_check", "episodes", type_="check")
	op.create_check_constraint(
		"episodes_status_check",
		"episodes",
		f"generation_status IN ({OLD_STATUSES})",
	)

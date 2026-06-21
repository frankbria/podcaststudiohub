"""Canonicalize user emails to lowercase (case-insensitive identity)

Revision ID: 012
Revises: 011
Create Date: 2026-06-20 00:00:00.000000

Makes email case never identity-significant (#255):
- Aborts if case-variant duplicate accounts already exist (manual dedupe
  required — auto-merging would destroy account data).
- Lowercases all existing emails.
- Adds a functional unique index on lower(email) to enforce canonical uniqueness.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	bind = op.get_bind()

	# Abort loudly on case-variant collisions — merging accounts is not safe to
	# automate (it would orphan owned resources / drop credentials). Operator
	# must dedupe manually before this migration can proceed.
	collisions = bind.execute(
		sa.text(
			"SELECT lower(email) AS canonical, count(*) AS n "
			"FROM users GROUP BY lower(email) HAVING count(*) > 1"
		)
	).fetchall()
	if collisions:
		offenders = ", ".join(f"{row.canonical} (x{row.n})" for row in collisions)
		raise RuntimeError(
			"Cannot canonicalize user emails: case-variant duplicate accounts "
			f"exist and must be merged/removed manually first: {offenders}"
		)

	op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
	op.create_index(
		"uq_users_email_lower",
		"users",
		[sa.text("lower(email)")],
		unique=True,
	)


def downgrade() -> None:
	op.drop_index("uq_users_email_lower", table_name="users")

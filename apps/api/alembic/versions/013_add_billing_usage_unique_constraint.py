"""Add unique constraint on billing_usage(user_id, period_start)

Revision ID: 013
Revises: 012
Create Date: 2026-06-26 00:00:00.000000

Backstops per-period usage uniqueness at the DB level (#296):
- Deduplicates any existing rows by aggregating metric columns into the
  earliest-created survivor per (user_id, period_start) group, then deleting
  the duplicates — so the constraint applies cleanly on dirty databases.
- Adds UNIQUE(user_id, period_start) so concurrent first-touch metering can
  never create duplicate rows (which made scalar_one_or_none() raise
  MultipleResultsFound → 500).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Aggregate metric columns from duplicate rows into the earliest-created
	# survivor (min created_at, ties broken by id) per (user_id, period_start).
	op.execute(
		"""
		WITH survivors AS (
			SELECT id AS keep_id, user_id, period_start
			FROM (
				SELECT id, user_id, period_start,
				       ROW_NUMBER() OVER (
				           PARTITION BY user_id, period_start
				           ORDER BY created_at, id
				       ) AS rn
				FROM billing_usage
			) ranked
			WHERE rn = 1
		),
		agg AS (
			SELECT user_id, period_start,
			       SUM(episodes_created)   AS episodes_created,
			       SUM(api_calls)          AS api_calls,
			       SUM(storage_bytes)      AS storage_bytes,
			       SUM(compute_hours)      AS compute_hours,
			       SUM(overage_episodes)   AS overage_episodes,
			       SUM(overage_storage_gb) AS overage_storage_gb,
			       SUM(overage_cost)       AS overage_cost
			FROM billing_usage
			GROUP BY user_id, period_start
			HAVING COUNT(*) > 1
		)
		UPDATE billing_usage t
		SET episodes_created   = agg.episodes_created,
		    api_calls          = agg.api_calls,
		    storage_bytes      = agg.storage_bytes,
		    compute_hours      = agg.compute_hours,
		    overage_episodes   = agg.overage_episodes,
		    overage_storage_gb = agg.overage_storage_gb,
		    overage_cost       = agg.overage_cost
		FROM agg
		JOIN survivors s
		  ON s.user_id = agg.user_id AND s.period_start = agg.period_start
		WHERE t.id = s.keep_id;
		"""
	)

	# Delete the now-redundant duplicate rows, keeping only the survivors.
	op.execute(
		"""
		DELETE FROM billing_usage b
		USING (
			SELECT id,
			       ROW_NUMBER() OVER (
			           PARTITION BY user_id, period_start
			           ORDER BY created_at, id
			       ) AS rn
			FROM billing_usage
		) d
		WHERE b.id = d.id AND d.rn > 1;
		"""
	)

	op.create_unique_constraint(
		"uq_billing_usage_user_period",
		"billing_usage",
		["user_id", "period_start"],
	)


def downgrade() -> None:
	op.drop_constraint("uq_billing_usage_user_period", "billing_usage", type_="unique")

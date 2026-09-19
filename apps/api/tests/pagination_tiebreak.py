"""Shared check for deterministic paging under tied sort keys (#530).

With LIMIT/OFFSET, Postgres returns rows with equal sort keys in arbitrary
order unless the query breaks the tie, so a paging client can see a row twice
or never. Every paginated list therefore ends its ORDER BY with the primary
key. This helper forces a full tie and pages through two rows at a time.
"""

from datetime import datetime

from sqlalchemy import text

TIED_AT = datetime(2026, 1, 1, 12, 0, 0)


async def force_created_at_tie(test_db, table: str, ids: list[str]) -> None:
	"""Give the ``ids`` rows of ``table`` the same created_at.

	The shared test session keeps the last request's RLS tenant context armed,
	so the rows are visible to the UPDATE.
	"""
	result = await test_db.execute(
		text(f"UPDATE {table} SET created_at = :ts WHERE id = ANY(CAST(:ids AS uuid[]))"),
		{"ts": TIED_AT, "ids": ids},
	)
	assert result.rowcount == len(ids)


async def assert_tied_pages_stable(
	client,
	test_db,
	headers: dict,
	*,
	table: str,
	url: str,
	key: str,
	ids: list[str],
	descending: bool = True,
) -> None:
	"""Tie ``created_at`` across ``ids`` and assert paging returns each exactly once, in id order."""
	await force_created_at_tie(test_db, table, ids)

	sep = "&" if "?" in url else "?"
	seen: list[str] = []
	for page in range(1, (len(ids) + 1) // 2 + 1):
		response = await client.get(f"{url}{sep}page={page}&page_size=2", headers=headers)
		assert response.status_code == 200, response.text
		seen += [row["id"] for row in response.json()[key]]

	assert seen == sorted(ids, reverse=descending), f"unstable paging under tied created_at: {seen}"

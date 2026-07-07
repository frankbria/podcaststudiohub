"""
Minimal conftest for unit tests — sets required env vars without loading the full app.
"""
import os
from uuid import UUID, uuid4

# Set required environment variables before any src imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("ENVIRONMENT", "test")


async def _register_user(
	client,
	email: str | None = None,
	*,
	email_prefix: str = "unit_test_",
	full_name: str = "Unit Test User",
) -> UUID:
	"""Register a real user via the auth flow and return their user id.

	Shared by service-layer unit tests (billing_service, team_service, ...)
	that need a real, persisted user for FK-backed rows rather than a bare
	uuid4(). Uses the same `client` (bound to the shared `test_db` session)
	so the row is visible to direct service-layer calls in the same test.
	"""
	if email is None:
		email = f"{email_prefix}{uuid4()}@example.com"
	response = await client.post("/auth/register", json={
		"email": email,
		"password": "SecurePass123!",
		"full_name": full_name,
	})
	assert response.status_code == 201, response.text
	return UUID(response.json()["user"]["id"])

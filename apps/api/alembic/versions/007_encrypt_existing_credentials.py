"""Encrypt existing plaintext credentials in distribution_targets and users

Iterates over existing rows and encrypts any plaintext credentials found in:
- distribution_targets.config: Spotify OAuth tokens, Apple API keys, webhook
  Authorization/Secret/Token/Api-Key headers
- users.encrypted_api_keys: Any values stored in plaintext (non-encrypted)

The encryption uses the same PostgreSQL pgcrypto encrypt_credential() function
that new records use, so all credentials are stored identically after migration.

NOTE: This migration is NOT safely reversible. Downgrade() is a no-op because
decrypting in-place would expose credentials. Back up the database before
running this migration.

Revision ID: 007
Revises: 006
Create Date: 2026-03-11 00:00:00.000000

"""
from typing import Sequence, Union
import os
import logging

from alembic import op
from sqlalchemy import text

logger = logging.getLogger("alembic.runtime.migration")

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Header name fragments that indicate a sensitive credential value
_SENSITIVE_HEADER_FRAGMENTS = ("authorization", "secret", "token", "api-key")


def _is_sensitive_header(name: str) -> bool:
	"""Return True if a header name suggests it contains a credential."""
	lower = name.lower()
	return any(frag in lower for frag in _SENSITIVE_HEADER_FRAGMENTS)


def _looks_encrypted(value: str) -> bool:
	"""
	Heuristic: pgcrypto encrypt_credential() returns a hex string prefixed
	with '\\x' when cast to text. Plaintext values will not start with that.
	"""
	return isinstance(value, str) and value.startswith("\\x")


def upgrade() -> None:
	"""Encrypt existing plaintext credentials."""
	encryption_key = os.environ.get("ENCRYPTION_KEY", "")
	if not encryption_key:
		raise RuntimeError(
			"ENCRYPTION_KEY environment variable must be set to run migration 007."
		)

	connection = op.get_bind()

	# ------------------------------------------------------------------
	# 1. Encrypt Spotify OAuth tokens in distribution_targets
	# ------------------------------------------------------------------
	spotify_rows = connection.execute(
		text(
			"SELECT id, config FROM distribution_targets "
			"WHERE target_type = 'spotify' AND config IS NOT NULL"
		)
	).fetchall()

	for row in spotify_rows:
		target_id = row[0]
		config = dict(row[1]) if row[1] else {}
		oauth_tokens = config.get("oauth_tokens", {})
		changed = False

		for field in ("access_token", "refresh_token"):
			value = oauth_tokens.get(field)
			if value and not _looks_encrypted(value):
				result = connection.execute(
					text("SELECT encrypt_credential(:val, :key)"),
					{"val": value, "key": encryption_key},
				).scalar()
				oauth_tokens[field] = result
				changed = True

		if changed:
			config["oauth_tokens"] = oauth_tokens
			connection.execute(
				text(
					"UPDATE distribution_targets SET config = :cfg::jsonb "
					"WHERE id = :tid"
				),
				{"cfg": __import__("json").dumps(config), "tid": str(target_id)},
			)
			logger.info("Encrypted Spotify tokens for distribution_target %s", target_id)

	# ------------------------------------------------------------------
	# 2. Encrypt Apple Podcasts API keys
	# ------------------------------------------------------------------
	apple_rows = connection.execute(
		text(
			"SELECT id, config FROM distribution_targets "
			"WHERE target_type = 'apple_podcasts' AND config IS NOT NULL"
		)
	).fetchall()

	for row in apple_rows:
		target_id = row[0]
		config = dict(row[1]) if row[1] else {}
		credentials = config.get("credentials", {})
		api_key = credentials.get("api_key")

		if api_key and not _looks_encrypted(api_key):
			result = connection.execute(
				text("SELECT encrypt_credential(:val, :key)"),
				{"val": api_key, "key": encryption_key},
			).scalar()
			credentials["api_key"] = result
			config["credentials"] = credentials
			connection.execute(
				text(
					"UPDATE distribution_targets SET config = :cfg::jsonb "
					"WHERE id = :tid"
				),
				{"cfg": __import__("json").dumps(config), "tid": str(target_id)},
			)
			logger.info("Encrypted Apple API key for distribution_target %s", target_id)

	# ------------------------------------------------------------------
	# 3. Encrypt webhook sensitive headers
	# ------------------------------------------------------------------
	webhook_rows = connection.execute(
		text(
			"SELECT id, config FROM distribution_targets "
			"WHERE target_type = 'webhook' AND config IS NOT NULL"
		)
	).fetchall()

	for row in webhook_rows:
		target_id = row[0]
		config = dict(row[1]) if row[1] else {}
		headers = config.get("headers", {})
		if not headers:
			continue

		changed = False
		updated_headers = dict(headers)
		for header_name, header_value in headers.items():
			if _is_sensitive_header(header_name) and header_value and not _looks_encrypted(header_value):
				result = connection.execute(
					text("SELECT encrypt_credential(:val, :key)"),
					{"val": header_value, "key": encryption_key},
				).scalar()
				updated_headers[header_name] = result
				changed = True

		if changed:
			config["headers"] = updated_headers
			connection.execute(
				text(
					"UPDATE distribution_targets SET config = :cfg::jsonb "
					"WHERE id = :tid"
				),
				{"cfg": __import__("json").dumps(config), "tid": str(target_id)},
			)
			logger.info("Encrypted webhook headers for distribution_target %s", target_id)

	# ------------------------------------------------------------------
	# 4. Encrypt any plaintext values in users.encrypted_api_keys
	# ------------------------------------------------------------------
	user_rows = connection.execute(
		text(
			"SELECT id, encrypted_api_keys FROM users "
			"WHERE encrypted_api_keys IS NOT NULL "
			"AND encrypted_api_keys != '{}'::jsonb"
		)
	).fetchall()

	for row in user_rows:
		user_id = row[0]
		api_keys = dict(row[1]) if row[1] else {}
		changed = False
		updated_keys = dict(api_keys)

		for provider, key_value in api_keys.items():
			if key_value and not _looks_encrypted(key_value):
				result = connection.execute(
					text("SELECT encrypt_credential(:val, :key)"),
					{"val": key_value, "key": encryption_key},
				).scalar()
				updated_keys[provider] = result
				changed = True

		if changed:
			connection.execute(
				text(
					"UPDATE users SET encrypted_api_keys = :keys::jsonb "
					"WHERE id = :uid"
				),
				{"keys": __import__("json").dumps(updated_keys), "uid": str(user_id)},
			)
			logger.info("Encrypted API keys for user %s", user_id)


def downgrade() -> None:
	"""
	Downgrade is intentionally a no-op.

	Decrypting credentials in-place during a rollback would require exposing
	the raw values in SQL, creating a security risk. If a rollback is needed,
	restore from a database backup taken before running this migration.
	"""
	pass

"""
Unit tests for email service.

Tests cover:
- _render_verification_email: fallback template (no file), with template file
- send_email: EMAIL_ENABLED=False short-circuits, ENABLED+success, ENABLED+failure
- send_verification_email: calls render + send_email correctly
"""

import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path


# ===========================================================================
# _render_verification_email
# ===========================================================================


class TestRenderVerificationEmail:
	def test_fallback_html_contains_verification_url(self):
		"""When template file doesn't exist, inline fallback includes URL."""
		from src.services.email_service import _render_verification_email

		with patch.object(Path, "exists", return_value=False):
			html, text = _render_verification_email("https://example.com/verify", "Alice")

		assert "https://example.com/verify" in html
		assert "Alice" in html

	def test_fallback_text_contains_verification_url(self):
		"""Plain-text fallback includes URL."""
		from src.services.email_service import _render_verification_email

		with patch.object(Path, "exists", return_value=False):
			_, text = _render_verification_email("https://example.com/verify", "Bob")

		assert "https://example.com/verify" in text
		assert "Bob" in text

	def test_fallback_escapes_html_in_name(self):
		"""HTML special chars in user_name are escaped in HTML body."""
		from src.services.email_service import _render_verification_email

		with patch.object(Path, "exists", return_value=False):
			html, _ = _render_verification_email("https://example.com", "<script>")

		assert "<script>" not in html
		assert "&lt;script&gt;" in html

	def test_with_template_file_substitutes_values(self):
		"""When template file exists, values are substituted in its content."""
		from src.services.email_service import _render_verification_email

		template = "Hello {{ user_name }}, click {{ verification_url }}"

		with patch.object(Path, "exists", return_value=True), \
		     patch.object(Path, "read_text", return_value=template):
			html, _ = _render_verification_email("https://verify.example.com", "Carol")

		assert "Carol" in html
		assert "https://verify.example.com" in html
		assert "{{ user_name }}" not in html

	def test_returns_tuple_of_two_strings(self):
		"""Always returns (html_str, text_str)."""
		from src.services.email_service import _render_verification_email

		with patch.object(Path, "exists", return_value=False):
			result = _render_verification_email("http://x", "X")

		assert isinstance(result, tuple)
		assert len(result) == 2
		assert all(isinstance(s, str) for s in result)


# ===========================================================================
# send_email
# ===========================================================================


class TestSendEmail:

	@pytest.mark.asyncio
	async def test_email_disabled_returns_false(self):
		"""When EMAIL_ENABLED=False, send_email returns False without sending."""
		from src.services.email_service import send_email

		with patch("src.services.email_service.settings") as mock_settings:
			mock_settings.EMAIL_ENABLED = False
			result = await send_email(
				to_email="user@example.com",
				subject="Test",
				html_content="<p>Hello</p>",
				text_content="Hello",
			)

		assert result is False

	@pytest.mark.asyncio
	async def test_email_enabled_success_returns_true(self):
		"""When EMAIL_ENABLED=True and SMTP succeeds, returns True."""
		from src.services.email_service import send_email

		with patch("src.services.email_service.settings") as mock_settings, \
		     patch("src.services.email_service.asyncio.get_event_loop") as mock_loop_fn:
			mock_settings.EMAIL_ENABLED = True
			mock_settings.EMAIL_FROM = "from@example.com"
			mock_settings.EMAIL_FROM_NAME = "Test"
			mock_settings.SMTP_HOST = "localhost"
			mock_settings.SMTP_PORT = 587
			mock_settings.SMTP_USE_TLS = False
			mock_settings.SMTP_USERNAME = None
			mock_settings.SMTP_PASSWORD = None

			mock_loop = AsyncMock()
			mock_loop.run_in_executor = AsyncMock(return_value=None)
			mock_loop_fn.return_value = mock_loop

			result = await send_email(
				to_email="user@example.com",
				subject="Test",
				html_content="<p>Hello</p>",
				text_content="Hello",
			)

		assert result is True

	@pytest.mark.asyncio
	async def test_email_enabled_exception_returns_false(self):
		"""When EMAIL_ENABLED=True and SMTP raises, returns False (logged, not raised)."""
		from src.services.email_service import send_email

		with patch("src.services.email_service.settings") as mock_settings, \
		     patch("src.services.email_service.asyncio.get_event_loop") as mock_loop_fn:
			mock_settings.EMAIL_ENABLED = True

			mock_loop = AsyncMock()
			mock_loop.run_in_executor = AsyncMock(side_effect=Exception("SMTP connection refused"))
			mock_loop_fn.return_value = mock_loop

			result = await send_email(
				to_email="user@example.com",
				subject="Test",
				html_content="<p>Hello</p>",
				text_content="Hello",
			)

		assert result is False


# ===========================================================================
# send_verification_email
# ===========================================================================


class TestSendVerificationEmail:

	@pytest.mark.asyncio
	async def test_send_verification_email_disabled_returns_false(self):
		"""Delegates to send_email, which returns False when email disabled."""
		from src.services.email_service import send_verification_email

		with patch("src.services.email_service.settings") as mock_settings:
			mock_settings.EMAIL_ENABLED = False
			mock_settings.FRONTEND_URL = "http://localhost:3000"
			mock_settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24

			with patch.object(Path, "exists", return_value=False):
				result = await send_verification_email(
					user_email="user@example.com",
					user_name="Alice",
					verification_token="token123",
				)

		assert result is False

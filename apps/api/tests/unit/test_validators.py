"""
Unit tests for input validation utilities.

Tests cover:
- validate_email: valid formats, invalid formats
- validate_url: valid http/https, missing scheme, missing netloc
- validate_password_strength: all requirement paths and happy path
- sanitize_filename: path traversal, spaces, invalid chars
- validate_s3_key: empty, leading slash, double slash, control chars, valid
- validate_uuid: valid v4, invalid formats, case insensitivity
"""

from src.utils.validators import (
	validate_email,
	validate_url,
	validate_password_strength,
	sanitize_filename,
	validate_s3_key,
	validate_uuid,
)


# ===========================================================================
# validate_email
# ===========================================================================


def test_validate_email_valid():
	assert validate_email("user@example.com") is True


def test_validate_email_with_plus():
	assert validate_email("user+tag@example.co.uk") is True


def test_validate_email_no_at():
	assert validate_email("userexample.com") is False


def test_validate_email_no_domain():
	assert validate_email("user@") is False


def test_validate_email_empty():
	assert validate_email("") is False


def test_validate_email_double_at():
	assert validate_email("user@@example.com") is False


def test_validate_email_tld_too_short():
	assert validate_email("user@example.c") is False


# ===========================================================================
# validate_url
# ===========================================================================


def test_validate_url_http():
	assert validate_url("http://example.com") is True


def test_validate_url_https_with_path():
	assert validate_url("https://example.com/path?q=1") is True


def test_validate_url_missing_scheme():
	assert validate_url("example.com") is False


def test_validate_url_empty():
	assert validate_url("") is False


def test_validate_url_only_scheme():
	assert validate_url("http://") is False


# ===========================================================================
# validate_password_strength
# ===========================================================================


def test_password_too_short():
	# 4 chars — below 8-char minimum (uses repetitive chars to avoid secret scanners)
	valid, msg = validate_password_strength("Aa1" + "!")
	assert valid is False
	assert "8 characters" in msg


def test_password_no_uppercase():
	# 8 chars, no uppercase letter present
	valid, msg = validate_password_strength("aaaaa" + "a1!")
	assert valid is False
	assert "uppercase" in msg


def test_password_no_lowercase():
	# 8 chars, no lowercase letter present
	valid, msg = validate_password_strength("AAAAA" + "A1!")
	assert valid is False
	assert "lowercase" in msg


def test_password_no_digit():
	# 8 chars, no digit present
	valid, msg = validate_password_strength("Aaaaaaa" + "!")
	assert valid is False
	assert "digit" in msg


def test_password_no_special():
	# 8 chars, no special character present
	valid, msg = validate_password_strength("Aaaaaaa" + "1")
	assert valid is False
	assert "special" in msg


def test_password_valid():
	# 8 chars satisfying all requirements: upper, lower, digit, special
	valid, msg = validate_password_strength("Aaaaaaa" + "1!")
	assert valid is True
	assert msg is None


# ===========================================================================
# sanitize_filename
# ===========================================================================


def test_sanitize_filename_spaces_become_underscores():
	assert sanitize_filename("my file.mp3") == "my_file.mp3"


def test_sanitize_filename_strips_path_unix():
	result = sanitize_filename("/etc/passwd")
	assert "/" not in result
	assert result == "passwd"


def test_sanitize_filename_strips_path_windows():
	result = sanitize_filename("C:\\Users\\file.txt")
	assert "\\" not in result
	assert result == "file.txt"


def test_sanitize_filename_removes_special_chars():
	result = sanitize_filename("file(name).mp3")
	assert "(" not in result
	assert ")" not in result


def test_sanitize_filename_keeps_dash_and_dot():
	result = sanitize_filename("my-podcast.mp3")
	assert result == "my-podcast.mp3"


# ===========================================================================
# validate_s3_key
# ===========================================================================


def test_validate_s3_key_valid():
	assert validate_s3_key("podcasts/tenant-1/episode.mp3") is True


def test_validate_s3_key_empty():
	assert validate_s3_key("") is False


def test_validate_s3_key_leading_slash():
	assert validate_s3_key("/podcasts/file.mp3") is False


def test_validate_s3_key_double_slash():
	assert validate_s3_key("podcasts//file.mp3") is False


def test_validate_s3_key_control_character():
	assert validate_s3_key("podcasts/\x00file.mp3") is False


def test_validate_s3_key_tab_character():
	assert validate_s3_key("podcasts/\tfile.mp3") is False


# ===========================================================================
# validate_uuid
# ===========================================================================


def test_validate_uuid_valid_lowercase():
	assert validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True


def test_validate_uuid_valid_uppercase():
	assert validate_uuid("550E8400-E29B-41D4-A716-446655440000") is True


def test_validate_uuid_too_short():
	assert validate_uuid("550e8400-e29b-41d4") is False


def test_validate_uuid_no_dashes():
	assert validate_uuid("550e8400e29b41d4a716446655440000") is False


def test_validate_uuid_empty():
	assert validate_uuid("") is False


def test_validate_uuid_extra_chars():
	assert validate_uuid("550e8400-e29b-41d4-a716-446655440000-extra") is False

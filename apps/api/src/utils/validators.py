"""
Input validation utilities
"""
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


# PDF upload constraints (mirrors the 50 MB ceiling used for audio snippets).
MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# Content types accepted for a PDF upload. ``application/octet-stream`` is
# allowed because some browsers/clients send it for binary uploads even when the
# file is a valid PDF; the ``.pdf`` extension check below is the primary guard.
ALLOWED_PDF_CONTENT_TYPES = frozenset(
    {"application/pdf", "application/x-pdf", "application/octet-stream"}
)


def validate_pdf_format(filename: str, content_type: Optional[str] = None) -> str:
    """
    Validate that an uploaded file is a PDF.

    Checks the filename extension is ``.pdf`` (case-insensitive) and, when a
    content type is supplied, that it is an accepted PDF MIME type. Lenient on a
    generic ``application/octet-stream`` content type as long as the extension is
    ``.pdf`` (mirrors the audio-snippet validator's tolerance for generic types).

    Args:
        filename: Original filename of the uploaded file.
        content_type: MIME type reported by the upload (optional).

    Returns:
        The normalized extension ``"pdf"``.

    Raises:
        ValueError: If the extension is not ``.pdf`` or the content type is a
            recognized non-PDF type.
    """
    ext = Path(filename or "").suffix.lstrip(".").lower()
    if ext != "pdf":
        raise ValueError(
            f"Unsupported file format '.{ext}'. Only PDF files (.pdf) are allowed."
        )

    if content_type and content_type.lower() not in ALLOWED_PDF_CONTENT_TYPES:
        raise ValueError(
            f"Invalid content type '{content_type}'. Expected 'application/pdf'."
        )

    return ext


def validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email: Email address to validate

    Returns:
        True if valid email format, False otherwise
    """
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return bool(re.match(pattern, email))


def validate_url(url: str) -> bool:
    """
    Validate URL format.

    Args:
        url: URL to validate

    Returns:
        True if valid URL format, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength.

    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"

    return True, None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe storage.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for file system
    """
    # Remove path components
    filename = filename.split('/')[-1].split('\\')[-1]

    # Replace spaces with underscores
    filename = filename.replace(' ', '_')

    # Remove any characters that aren't alphanumeric, dash, underscore, or dot
    filename = re.sub(r'[^\w\-.]', '', filename)

    return filename


def validate_s3_key(s3_key: str) -> bool:
    """
    Validate S3 object key format.

    Args:
        s3_key: S3 object key to validate

    Returns:
        True if valid S3 key, False otherwise
    """
    # S3 keys cannot be empty, start with /, or contain //
    if not s3_key or s3_key.startswith('/') or '//' in s3_key:
        return False

    # Check for invalid characters (S3 allows most characters)
    # Disallow control characters
    if any(ord(c) < 32 for c in s3_key):
        return False

    return True


def validate_uuid(uuid_str: str) -> bool:
    """
    Validate UUID format.

    Args:
        uuid_str: UUID string to validate

    Returns:
        True if valid UUID format, False otherwise
    """
    uuid_pattern = re.compile(
        r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
        re.IGNORECASE
    )
    return bool(uuid_pattern.match(uuid_str))

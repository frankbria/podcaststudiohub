"""Email service for sending transactional emails via SMTP"""

import html
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _render_verification_email(verification_url: str, user_name: str) -> tuple[str, str]:
    """
    Render the verification email HTML and plain-text bodies.

    Args:
        verification_url: Full verification link (including token)
        user_name: Recipient's display name

    Returns:
        Tuple of (html_content, text_content)
    """
    template_path = _TEMPLATES_DIR / "verification_email.html"
    if template_path.exists():
        html_content = template_path.read_text(encoding="utf-8")
        html_content = html_content.replace("{{ verification_url }}", verification_url)
        html_content = html_content.replace("{{ user_name }}", user_name)
    else:
        # Fallback inline template — escape user-controlled values before HTML interpolation
        safe_name = html.escape(user_name)
        safe_url = html.escape(verification_url)
        html_content = f"""
<html>
<body>
<p>Hi {safe_name},</p>
<p>Please verify your email address by clicking the link below:</p>
<p><a href="{safe_url}">{safe_url}</a></p>
<p>This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.</p>
<p>If you did not create an account, you can safely ignore this email.</p>
</body>
</html>
"""

    text_content = (
        f"Hi {user_name},\n\n"
        f"Please verify your email address by visiting the following link:\n"
        f"{verification_url}\n\n"
        f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.\n\n"
        f"If you did not create an account, you can safely ignore this email."
    )

    return html_content, text_content


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
) -> bool:
    """
    Send an email via SMTP (synchronous).

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML body
        text_content: Plain-text body fallback

    Returns:
        True on success, False on failure (errors are logged, not raised)
    """
    if not settings.EMAIL_ENABLED:
        logger.debug("EMAIL_ENABLED=False; skipping email to %s", to_email)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
        msg["To"] = to_email

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        context = ssl.create_default_context()

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls(context=context)
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.sendmail(settings.EMAIL_FROM, [to_email], msg.as_string())

        logger.info("Email sent successfully to %s", to_email)
        return True

    except Exception as exc:
        logger.warning("Failed to send email to %s: %s", to_email, exc)
        return False


def send_verification_email(
    user_email: str,
    user_name: str,
    verification_token: str,
) -> bool:
    """
    Send the email-verification message to a newly registered user.

    Args:
        user_email: Recipient email address
        user_name: Recipient's display name
        verification_token: Signed JWT verification token

    Returns:
        True on success, False on failure
    """
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
    html_content, text_content = _render_verification_email(verification_url, user_name)

    return send_email(
        to_email=user_email,
        subject="Verify your Podcastfy account",
        html_content=html_content,
        text_content=text_content,
    )

"""Email service for sending transactional emails via SMTP"""

import asyncio
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
    # Escape user-controlled values before HTML interpolation
    safe_name = html.escape(user_name)
    safe_url = html.escape(verification_url)

    template_path = _TEMPLATES_DIR / "verification_email.html"
    if template_path.exists():
        html_content = template_path.read_text(encoding="utf-8")
        html_content = html_content.replace("{{ verification_url }}", safe_url)
        html_content = html_content.replace("{{ user_name }}", safe_name)
    else:
        # Fallback inline template
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


def _do_smtp_send(
    to_email: str,
    from_addr: str,
    from_name: str,
    subject: str,
    html_content: str,
    text_content: str,
    smtp_host: str,
    smtp_port: int,
    smtp_use_tls: bool,
    smtp_username: str,
    smtp_password: str,
) -> None:
    """Synchronous SMTP send — runs in a thread pool via run_in_executor."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        if smtp_use_tls:
            smtp.starttls(context=context)
        if smtp_username and smtp_password:
            smtp.login(smtp_username, smtp_password)
        smtp.sendmail(from_addr, [to_email], msg.as_string())


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
) -> bool:
    """
    Send an email via SMTP without blocking the event loop.

    The synchronous SMTP call is offloaded to a thread pool executor so that
    the async event loop remains unblocked during the SMTP handshake.

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
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _do_smtp_send,
            to_email,
            settings.EMAIL_FROM,
            settings.EMAIL_FROM_NAME,
            subject,
            html_content,
            text_content,
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            settings.SMTP_USE_TLS,
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD,
        )
        logger.info("Email sent successfully to %s", to_email)
        return True

    except Exception as exc:
        logger.warning("Failed to send email to %s: %s", to_email, exc)
        return False


async def send_verification_email(
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

    return await send_email(
        to_email=user_email,
        subject="Verify your Podcastfy account",
        html_content=html_content,
        text_content=text_content,
    )

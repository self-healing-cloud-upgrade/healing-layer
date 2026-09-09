"""
Email Notification Service — Async Escalation Emails

Sends escalation emails to the developer when healing fails
after MAX_RETRY_ATTEMPTS (3) consecutive attempts.

Uses aiosmtplib for non-blocking SMTP delivery so the
verification worker loop is never blocked.

Configuration:
    SMTP_ENABLED must be True in settings (default: False).
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD must be set.
    For Gmail: use an App Password (not your account password).

Graceful degradation:
    If SMTP is not configured or delivery fails, the error is
    logged and the pipeline continues — email is best-effort.
"""
import os
import asyncio
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List
import jinja2
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Jinja2 environment for email templates
_template_dir = os.path.join(
    os.path.dirname(__file__), "templates"
)
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_template_dir),
    autoescape=True,
)


def _render_escalation_email(
    escalation_data: Dict[str, Any],
) -> str:
    """
    Render the escalation email HTML body from template.
    Returns the rendered HTML string.
    """
    try:
        template = _jinja_env.get_template(
            "escalation_email.html.j2"
        )
        return template.render(**escalation_data)
    except Exception as e:
        logger.error(
            "Failed to render escalation email template",
            error=str(e),
        )
        # Fallback: plain text summary
        return (
            f"ESCALATION ALERT\n\n"
            f"Healing failed after "
            f"{escalation_data.get('attempts', '?')} attempts "
            f"for {escalation_data.get('service', '?')}:"
            f"{escalation_data.get('endpoint', '?')}.\n\n"
            f"Actions tried: "
            f"{', '.join(escalation_data.get('healing_actions_tried', []))}\n"
            f"Manual intervention required."
        )


async def send_escalation_email(
    escalation_data: Dict[str, Any],
    recipient_override: str = None,
) -> bool:
    """
    Send an escalation email to the developer.

    Args:
        escalation_data: Dict with keys:
            service, endpoint, failure_tag, attempts,
            healing_actions_tried, outcomes, escalated_at
        recipient_override: If provided, send to this
            address instead of settings.ESCALATION_EMAIL_TO.
            Used when the recipient is set from the frontend.

    Returns:
        True if email was sent successfully, False otherwise.
    """
    if not settings.SMTP_ENABLED:
        logger.info(
            "Email escalation skipped — SMTP_ENABLED is False"
        )
        return False

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            "Email escalation skipped — SMTP credentials "
            "not configured (SMTP_USER / SMTP_PASSWORD)"
        )
        return False

    # Prepare template data
    template_data = {
        "service": escalation_data.get("service", "unknown"),
        "endpoint": escalation_data.get("endpoint", "unknown"),
        "failure_tag": escalation_data.get(
            "failure_tag", "unknown"
        ),
        "attempts": escalation_data.get("attempts", 0),
        "max_attempts": 3,
        "healing_actions_tried": escalation_data.get(
            "healing_actions_tried", []
        ),
        "outcomes": escalation_data.get("outcomes", []),
        "escalated_at": escalation_data.get(
            "escalated_at",
            datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
        ),
    }

    # Render HTML body
    html_body = _render_escalation_email(template_data)

    # Determine recipient
    recipient = recipient_override or settings.ESCALATION_EMAIL_TO

    # Build email message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"🚨 [Niramay] Healing Failed — "
        f"{template_data['service']}:"
        f"{template_data['endpoint']} "
        f"({template_data['attempts']} attempts exhausted)"
    )
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = recipient

    # Attach HTML part
    msg.attach(MIMEText(html_body, "html"))

    # Send via aiosmtplib
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info(
            "Escalation email sent successfully",
            to=recipient,
            service=template_data["service"],
            endpoint=template_data["endpoint"],
        )
        return True

    except aiosmtplib.SMTPAuthenticationError as e:
        logger.error(
            "SMTP authentication failed — check "
            "SMTP_USER / SMTP_PASSWORD credentials",
            error=str(e),
        )
        return False
    except aiosmtplib.SMTPConnectError as e:
        logger.error(
            "SMTP connection failed — check "
            "SMTP_HOST / SMTP_PORT settings",
            error=str(e),
        )
        return False
    except Exception as e:
        logger.error(
            "Failed to send escalation email",
            error=str(e),
        )
        return False

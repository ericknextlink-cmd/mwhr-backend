import base64
import logging
from typing import Any, Dict, List, Tuple

import resend
from pydantic import EmailStr

from app.core.config import settings
from app.services.email_templates import wrap_email_body

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY


async def send_email(
    email_to: EmailStr,
    subject_template: str = "",
    html_template: str = "",
    environment: Dict[str, Any] = {},
    attachments: List[Tuple[str, bytes]] = None,
) -> None:
    """
    Send email using Resend.
    attachments: optional list of (filename, raw_bytes) e.g. [("invoice.pdf", pdf_bytes)]
    """
    payload = {
        "from": f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>",
        "to": [email_to],
        "subject": subject_template,
        "html": html_template,
    }
    if attachments:
        payload["attachments"] = [
            {"filename": name, "content": base64.b64encode(data).decode("utf-8")}
            for name, data in attachments
        ]

    if not settings.RESEND_API_KEY:
        logger.info("--- MOCK EMAIL SENDING (RESEND_API_KEY missing) ---")
        logger.info(f"To: {email_to}")
        logger.info(f"Subject: {subject_template}")
        logger.info(f"Attachments: {[a[0] for a in (attachments or [])]}")
        logger.info("---------------------------------------------------")
        return

    try:
        r = resend.Emails.send(payload)
        logger.info(f"Email sent successfully to {email_to}. ID: {r.get('id')}")
    except Exception as e:
        logger.error(f"Failed to send email via Resend: {e}")
        logger.info(f"To: {email_to}, Subject: {subject_template}")


async def send_reset_password_email(email_to: EmailStr, email: str, token: str) -> None:
    subject = "Password Recovery for Ministry Application"
    link = f"{settings.FRONTEND_URL}/auth/reset-password?token={token}"

    body = f"""
    <p>Hello,</p>
    <p>We received a request to reset your password for your Ministry Application account.</p>
    <p>Click the button below to reset your password. This link will expire in 15 minutes.</p>
    <p class="muted">If you did not request this, please ignore this email.</p>
    """
    html_content = wrap_email_body(
        title="Password Recovery",
        body_html=body,
        button_text="Reset password",
        button_link=link,
    )
    await send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
    )


async def send_verification_email(email_to: EmailStr, token: str) -> None:
    subject = "Verify your Ministry Application Account"
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"

    body = f"""
    <p>Welcome to the Ministry Application Portal!</p>
    <p>Please verify your email address to activate your account and start your application.</p>
    <p class="muted">If you didn't create an account, you can safely ignore this email.</p>
    """
    html_content = wrap_email_body(
        title="Verify your email",
        body_html=body,
        button_text="Verify email",
        button_link=link,
    )
    await send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
    )


async def send_invoice_email(
    email_to: EmailStr,
    applicant_name: str,
    application_id: int,
    pdf_bytes: bytes,
) -> None:
    """Send the 2-page invoice PDF to the applicant after payment."""
    subject = f"Invoice for your Certificate Application #{application_id}"
    # Link to certificates page (invoice and certs listed there). Unauthenticated users are redirected to login by the app.
    certificates_link = f"{settings.FRONTEND_URL}/dashboard/certificates"

    body = f"""
    <p>Dear {applicant_name},</p>
    <p>Thank you for completing payment for your certificate application.</p>
    <p>Please find your official invoice attached to this email (letter + invoice).</p>
    <p>You can also view and download it anytime from your certificates page.</p>
    """
    html_content = wrap_email_body(
        title="Your invoice is attached",
        body_html=body,
        button_text="View certificates & invoice",
        button_link=certificates_link,
    )
    await send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
        attachments=[("invoice.pdf", pdf_bytes)],
    )

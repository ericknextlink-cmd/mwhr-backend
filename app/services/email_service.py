from typing import Any, Dict
from pydantic import EmailStr
import logging
import resend
from app.core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY

async def send_email(
    email_to: EmailStr,
    subject_template: str = "",
    html_template: str = "",
    environment: Dict[str, Any] = {},
) -> None:
    """
    Send email using Resend.
    """
    if not settings.RESEND_API_KEY:
        logger.info(f"--- MOCK EMAIL SENDING (RESEND_API_KEY missing) ---")
        logger.info(f"To: {email_to}")
        logger.info(f"Subject: {subject_template}")
        logger.info(f"Body: \n{html_template}")
        logger.info(f"---------------------------------------------------")
        return

    try:
        r = resend.Emails.send({
            "from": f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>",
            "to": [email_to],
            "subject": subject_template,
            "html": html_template
        })
        logger.info(f"Email sent successfully to {email_to}. ID: {r.get('id')}")
    except Exception as e:
        logger.error(f"Failed to send email via Resend: {e}")
        # Fallback logging
        logger.info(f"--- FAILED EMAIL DUMP ---")
        logger.info(f"To: {email_to}")
        logger.info(f"Subject: {subject_template}")
        logger.info(f"Body: \n{html_template}")
        logger.info(f"-------------------------")

async def send_reset_password_email(email_to: EmailStr, email: str, token: str) -> None:
    subject = "Password Recovery for Ministry Application"
    # Link uses the configured FRONTEND_URL
    link = f"{settings.FRONTEND_URL}/auth/reset-password?token={token}"
    
    html_content = f"""
    <html>
        <body>
            <h1>Password Recovery</h1>
            <p>Hello,</p>
            <p>We received a request to reset your password for your Ministry Application account.</p>
            <p>Click the link below to reset your password:</p>
            <a href="{link}">{link}</a>
            <p>If you did not request this, please ignore this email.</p>
            <p>This link will expire in 15 minutes.</p>
        </body>
    </html>
    """
    
    await send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
    )

async def send_verification_email(email_to: EmailStr, token: str) -> None:
    subject = "Verify your Ministry Application Account"
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    
    html_content = f"""
    <html>
        <body>
            <h1>Verify Your Email</h1>
            <p>Welcome to the Ministry Application Portal!</p>
            <p>Please verify your email address to activate your account and start your application.</p>
            <p>Click the link below to verify:</p>
            <a href="{link}" style="background-color: #033783; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 10px;">Verify Email</a>
            <p style="margin-top: 20px; font-size: 12px; color: gray;">If you didn't create an account, you can safely ignore this email.</p>
        </body>
    </html>
    """
    
    await send_email(
        email_to=email_to,
        subject_template=subject,
        html_template=html_content,
    )


from typing import Any, Dict
from pydantic import EmailStr
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_email(
    email_to: EmailStr,
    subject_template: str = "",
    html_template: str = "",
    environment: Dict[str, Any] = {},
) -> None:
    """
    Mock email sending. In a real app, this would use SMTP or an API like SES/SendGrid.
    """
    logger.info(f"--- MOCK EMAIL SENDING ---")
    logger.info(f"To: {email_to}")
    logger.info(f"Subject: {subject_template}")
    logger.info(f"Body: \n{html_template}")
    logger.info(f"--------------------------")

async def send_reset_password_email(email_to: EmailStr, email: str, token: str) -> None:
    subject = "Password Recovery for Ministry Application"
    # Assuming frontend runs on localhost:3000 by default. 
    # In prod, this should come from settings.FRONTEND_URL
    link = f"http://localhost:3000/auth/reset-password?token={token}"
    
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


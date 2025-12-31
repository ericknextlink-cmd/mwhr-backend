from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.models.notification import Notification
from app.models.user import User
from app.core.config import settings

# Email Configuration
conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USER or "",
    MAIL_PASSWORD=settings.SMTP_PASSWORD or "",
    MAIL_FROM=settings.EMAILS_FROM_EMAIL or "noreply@example.com",
    MAIL_PORT=settings.SMTP_PORT or 587,
    MAIL_SERVER=settings.SMTP_HOST or "localhost",
    MAIL_FROM_NAME=settings.EMAILS_FROM_NAME or "Ministry App",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

async def send_email_notification(email_to: str, title: str, body: str):
    """
    Helper to send email asynchronously.
    """
    if not settings.EMAILS_ENABLED:
        return

    message = MessageSchema(
        subject=title,
        recipients=[email_to],
        body=body,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
    except Exception as e:
        print(f"Failed to send email to {email_to}: {e}")

async def notify_admins(session: AsyncSession, title: str, message: str, link: str = None):
    """
    Creates a notification for all superusers and sends an email.
    """
    # 1. Get all superusers
    statement = select(User).where(User.is_superuser == True)
    admins = await session.exec(statement)
    admins = admins.all()

    # 2. Create notification for each and send email
    for admin in admins:
        notification = Notification(
            user_id=admin.id,
            title=title,
            message=message,
            link=link,
            is_read=False
        )
        session.add(notification)
        
        # Send Email
        email_body = f"""
        <html>
            <body>
                <h2>{title}</h2>
                <p>{message}</p>
                {f'<p><a href="{settings.API_V1_STR}{link}">View Details</a></p>' if link else ''}
            </body>
        </html>
        """
        await send_email_notification(admin.email, title, email_body)
    
    # Caller must commit

async def notify_user(session: AsyncSession, user_id: int, title: str, message: str, link: str = None):
    """
    Creates a notification for a specific user and sends an email.
    """
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        link=link,
        is_read=False
    )
    session.add(notification)
    
    # Get user email to send notification
    user = await session.get(User, user_id)
    if user and user.email:
        email_body = f"""
        <html>
            <body>
                <h2>{title}</h2>
                <p>Hello,</p>
                <p>{message}</p>
                {f'<p><a href="{link}">View Details</a></p>' if link else ''}
            </body>
        </html>
        """
        await send_email_notification(user.email, title, email_body)
    
    # Caller must commit


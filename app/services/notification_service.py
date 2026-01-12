from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.notification import Notification
from app.models.user import User
from app.core.config import settings
from app.services.email_service import send_email

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
        
        # Send Email via common email service
        email_body = f"""
        <html>
            <body>
                <h2>{title}</h2>
                <p>{message}</p>
                {f'<p><a href="{settings.FRONTEND_URL}{link}">View Details</a></p>' if link else ''}
            </body>
        </html>
        """
        await send_email(admin.email, title, email_body)
    
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
                {f'<p><a href="{settings.FRONTEND_URL}{link}">View Details</a></p>' if link else ''}
            </body>
        </html>
        """
        await send_email(user.email, title, email_body)
    
    # Caller must commit
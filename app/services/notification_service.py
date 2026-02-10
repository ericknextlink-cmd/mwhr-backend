from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.notification import Notification
from app.models.user import User
from app.services.email_service import send_email
from app.services.email_templates import wrap_email_body


async def notify_admins(session: AsyncSession, title: str, message: str, link: str = None):
    """
    Creates a notification for all superusers and sends an email.
    """
    statement = select(User).where(User.is_superuser == True)
    admins = await session.exec(statement)
    admins = admins.all()

    for admin in admins:
        notification = Notification(
            user_id=admin.id,
            title=title,
            message=message,
            link=link,
            is_read=False,
        )
        session.add(notification)

        body = f"<p>{message}</p>"
        full_link = f"{settings.FRONTEND_URL}{link}" if link else None
        html_content = wrap_email_body(
            title=title,
            body_html=body,
            button_text="View details" if link else None,
            button_link=full_link,
        )
        await send_email(admin.email, title, html_content)

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
        is_read=False,
    )
    session.add(notification)

    user = await session.get(User, user_id)
    if user and user.email:
        body = f"<p>Hello,</p><p>{message}</p>"
        full_link = f"{settings.FRONTEND_URL}{link}" if link else None
        html_content = wrap_email_body(
            title=title,
            body_html=body,
            button_text="View details" if link else None,
            button_link=full_link,
        )
        await send_email(user.email, title, html_content)

    # Caller must commit
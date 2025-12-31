import asyncio
import sys
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.db.session import engine
from app.models.user import User, UserRole
from app.core.security import get_password_hash
from app.core.config import settings

async def create_admin_user(email: str, password: str):
    # Manually create session factory for standalone script
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_factory() as session:
        # Check if user already exists
        statement = select(User).where(User.email == email)
        result = await session.exec(statement)
        user = result.first()

        if user:
            print(f"User with email {email} already exists.")
            if not user.is_superuser:
                user.is_superuser = True
                user.role = UserRole.SUPER_ADMIN
                session.add(user)
                await session.commit()
                print(f"User {email} updated to Super Admin.")
            else:
                print(f"User {email} is already a superuser.")
            return

        # Create new superuser
        hashed_password = get_password_hash(password)
        new_superuser = User(
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True,
            role=UserRole.SUPER_ADMIN
        )
        session.add(new_superuser)
        await session.commit()
        await session.refresh(new_superuser)
        print(f"Super Admin '{email}' created successfully.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    admin_email = input("Enter Super Admin email: ")
    admin_password = input("Enter Super Admin password: ")

    asyncio.run(create_admin_user(admin_email, admin_password))
    print("Script finished.")
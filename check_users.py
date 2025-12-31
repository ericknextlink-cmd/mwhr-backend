import asyncio
from sqlmodel import select
from app.db.session import engine
from app.models.user import User
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

async def check_users():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        statement = select(User)
        result = await session.exec(statement)
        users = result.all()

        print(f"Found {len(users)} users in the database:")
        print("-" * 60)
        print(f"{'ID':<5} | {'Email':<30} | {'Is Active':<10} | {'Is Superuser':<12}")
        print("-" * 60)
        
        for user in users:
            print(f"{user.id:<5} | {user.email:<30} | {str(user.is_active):<10} | {str(user.is_superuser):<12}")
        print("-" * 60)

if __name__ == "__main__":
    asyncio.run(check_users())

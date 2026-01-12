import asyncio
from sqlmodel import select
from app.db.session import engine, AsyncSession
from app.models.user import User

async def verify_all_users():
    async_session = AsyncSession(engine)
    async with async_session as session:
        statement = select(User)
        results = await session.exec(statement)
        users = results.all()
        
        count = 0
        for user in users:
            if not user.is_verified:
                user.is_verified = True
                session.add(user)
                count += 1
        
        await session.commit()
        print(f"Successfully verified {count} existing users.")

if __name__ == "__main__":
    asyncio.run(verify_all_users())

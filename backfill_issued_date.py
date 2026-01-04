import asyncio
from sqlmodel import select
from app.db.session import engine
from app.models.application import Application, ApplicationStatus
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

async def backfill():
    print("Backfilling issued_date for existing approved certificates...")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        query = select(Application).where(
            Application.status == ApplicationStatus.APPROVED,
            Application.issued_date == None
        )
        result = await session.exec(query)
        apps = result.all()
        print(f"Found {len(apps)} apps to backfill.")
        for app in apps:
            app.issued_date = app.updated_at
            session.add(app)
            print(f" -> Backfilled App #{app.id} with date {app.issued_date}")
        await session.commit()
    print("Backfill complete.")

if __name__ == "__main__":
    asyncio.run(backfill())

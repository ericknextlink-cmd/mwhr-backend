import asyncio
from sqlmodel import SQLModel
from app.db.session import engine
# Import all models to ensure they are registered with SQLModel
from app.models import user, application, company_info, director, document, notification, audit_log

async def create_audit_table():
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    print("Tables created.")

if __name__ == "__main__":
    asyncio.run(create_audit_table())

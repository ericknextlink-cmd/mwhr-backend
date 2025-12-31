from sqlmodel import SQLModel
from app.db.session import engine
from . import user, application, company_info, director, document, notification, audit_log # Import all models

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


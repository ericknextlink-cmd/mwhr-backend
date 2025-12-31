import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_audit_label():
    print("Adding 'target_label' column to 'auditlog' table...")
    async with engine.connect() as conn:
        try:
            await conn.execute(text("ALTER TABLE auditlog ADD COLUMN IF NOT EXISTS target_label VARCHAR;"))
            await conn.commit()
            print("Successfully added 'target_label' column.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_audit_label())

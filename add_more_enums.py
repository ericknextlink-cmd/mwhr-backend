import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_missing_enums():
    print("Attempting to add missing enum values...")
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        for val in ['PENDING_PAYMENT', 'IN_REVIEW']:
            try:
                await conn.execute(text(f"ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS '{val}';"))
                print(f"Successfully added '{val}' to enum.")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"'{val}' already exists.")
                else:
                    print(f"Error adding '{val}': {e}")

if __name__ == "__main__":
    asyncio.run(add_missing_enums())

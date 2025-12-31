import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_lowercase_enums():
    print("Attempting to add lowercase enum values...")
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        for val in ['pending_payment', 'in_review']:
            try:
                await conn.execute(text(f"ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS '{val}';"))
                print(f"Successfully added '{val}' to enum.")
            except Exception as e:
                print(f"Error adding '{val}': {e}")

if __name__ == "__main__":
    asyncio.run(add_lowercase_enums())

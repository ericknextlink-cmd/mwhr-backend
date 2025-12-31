import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_remaining_lowercase_enums():
    print("Attempting to add remaining lowercase enum values...")
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        for val in ['submitted', 'approved', 'rejected', 'draft', 'cancelled', 'suspended']:
            try:
                await conn.execute(text(f"ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS '{val}';"))
                print(f"Successfully added '{val}' to enum.")
            except Exception as e:
                # Ignore if exists
                if "already exists" in str(e):
                    print(f"'{val}' already exists.")
                else:
                    print(f"Error adding '{val}': {e}")

if __name__ == "__main__":
    asyncio.run(add_remaining_lowercase_enums())

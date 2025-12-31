import asyncio
from sqlalchemy import text
from app.db.session import engine

async def force_add_column():
    print("Forcing add of 'expiry_date' column...")
    async with engine.connect() as conn:
        try:
            await conn.execute(text("ALTER TABLE application ADD COLUMN IF NOT EXISTS expiry_date TIMESTAMP WITHOUT TIME ZONE;"))
            await conn.commit() # Explicit commit
            print("Command executed and committed.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(force_add_column())

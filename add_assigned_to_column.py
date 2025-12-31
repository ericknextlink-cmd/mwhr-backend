import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_assigned_to():
    print("Adding 'assigned_to' column...")
    async with engine.connect() as conn:
        try:
            await conn.execute(text("ALTER TABLE application ADD COLUMN IF NOT EXISTS assigned_to INTEGER REFERENCES \"user\"(id);"))
            await conn.commit()
            print("Successfully added 'assigned_to' column.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_assigned_to())


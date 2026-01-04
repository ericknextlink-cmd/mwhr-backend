import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_issued_date_column():
    print("Adding 'issued_date' column to 'application' table...")
    async with engine.connect() as conn:
        try:
            await conn.execute(text("ALTER TABLE application ADD COLUMN IF NOT EXISTS issued_date TIMESTAMP WITHOUT TIME ZONE;"))
            await conn.commit()
            print("Column added successfully.")
        except Exception as e:
            print(f"Error: {e}")
            await conn.rollback()

if __name__ == "__main__":
    asyncio.run(add_issued_date_column())

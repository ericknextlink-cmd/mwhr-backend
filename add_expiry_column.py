import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_column():
    print("Attempting to add 'expiry_date' column to 'application' table...")
    async with engine.begin() as conn:
        try:
            # Check if column exists first to be safe (though raw SQL usually throws if it exists)
            # We'll just try to add it.
            await conn.execute(text("ALTER TABLE application ADD COLUMN expiry_date TIMESTAMP WITHOUT TIME ZONE;"))
            print("Successfully added 'expiry_date' column.")
        except Exception as e:
            if "already exists" in str(e):
                print("Column 'expiry_date' already exists.")
            else:
                print(f"Error adding column: {e}")

if __name__ == "__main__":
    asyncio.run(add_column())

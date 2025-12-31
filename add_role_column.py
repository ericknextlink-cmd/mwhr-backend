import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_role_column():
    print("Attempting to add 'role' column to 'user' table...")
    async with engine.begin() as conn:
        try:
            # 1. Add Column
            await conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR DEFAULT 'user';"))
            print("Successfully added 'role' column.")
            
            # 2. Migrate Data (Superusers -> SUPER_ADMIN)
            await conn.execute(text("UPDATE \"user\" SET role = 'super_admin' WHERE is_superuser = true;"))
            print("Successfully migrated existing superusers to 'super_admin' role.")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_role_column())

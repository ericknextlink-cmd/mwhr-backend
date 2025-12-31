import asyncio
from sqlalchemy import text
from app.db.session import engine

async def inspect_db():
    print("Inspecting 'application' table columns...")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'application';"))
        columns = [row[0] for row in result.fetchall()]
        print("Columns found:", columns)
        
        if 'expiry_date' in columns:
            print("SUCCESS: 'expiry_date' column exists.")
        else:
            print("FAILURE: 'expiry_date' column is MISSING.")

if __name__ == "__main__":
    asyncio.run(inspect_db())

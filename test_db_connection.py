import asyncio
import asyncpg
import sys

# provided connection details
# DATABASE_URL = "postgresql://postgres:3cbmFkWvQjbXL8fV@db.qjxjsberiwajxzmphaui.supabase.co:5432/postgres"

DSN = "postgresql://postgres:3cbmFkWvQjbXL8fV@db.qjxjsberiwajxzmphaui.supabase.co:5432/postgres?ssl=require"

async def test_connection():
    print(f"Attempting to connect to: {DSN.split('@')[1]}") # Hide password in print
    try:
        conn = await asyncpg.connect(DSN)
        version = await conn.fetchval("SELECT version()")
        print(f"Success! Connected to: {version}")
        await conn.close()
    except Exception as e:
        print(f"Connection Failed: {e}")
        # Print detailed error type
        print(f"Error Type: {type(e).__name__}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_connection())

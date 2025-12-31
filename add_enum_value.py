import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_enum_value():
    print("Attempting to add 'SUSPENDED' to 'applicationstatus' enum...")
    # 'ALTER TYPE ... ADD VALUE' cannot run inside a transaction block.
    # We use connect() and set isolation level to autocommit.
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            await conn.execute(text("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'SUSPENDED';"))
            print("Successfully added 'SUSPENDED' to enum.")
        except Exception as e:
            if "already exists" in str(e):
                print("'SUSPENDED' already exists.")
            else:
                # Sometimes "IF NOT EXISTS" is not supported in older PG versions for enums, 
                # so if it fails, it might be because it exists or syntax error.
                print(f"Error (might be okay if already exists): {e}")

    # Also add CANCELLED just in case we missed it earlier
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            await conn.execute(text("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'CANCELLED';"))
            print("Successfully added 'CANCELLED' to enum.")
        except Exception as e:
             if "already exists" in str(e):
                print("'CANCELLED' already exists.")
             else:
                print(f"Error (might be okay if already exists): {e}")

if __name__ == "__main__":
    asyncio.run(add_enum_value())

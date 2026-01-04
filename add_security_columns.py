import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_security_columns():
    print("Adding security columns to 'application' table...")
    async with engine.connect() as conn:
        try:
            # Add certificate_number
            await conn.execute(text("ALTER TABLE application ADD COLUMN IF NOT EXISTS certificate_number VARCHAR;"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_application_certificate_number ON application (certificate_number);"))
            
            # Add internal_uid
            # Note: We add it as nullable first. Populate it if needed, then set not null.
            await conn.execute(text("ALTER TABLE application ADD COLUMN IF NOT EXISTS internal_uid UUID;"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_application_internal_uid ON application (internal_uid);"))

            # Add security_token
            await conn.execute(text("ALTER TABLE application ADD COLUMN IF NOT EXISTS security_token VARCHAR;"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_application_security_token ON application (security_token);"))
            
            await conn.commit()
            print("Columns added successfully.")
            
            # Now populate internal_uid for existing rows if they are null
            # This requires pgcrypto or uuid-ossp usually, but let's try python update if needed
            # For now, let's just leave them nullable to avoid migration crash on existing data
            
        except Exception as e:
            print(f"Error: {e}")
            await conn.rollback()

if __name__ == "__main__":
    asyncio.run(add_security_columns())

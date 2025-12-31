import asyncio
from sqlmodel import select
from app.db.session import engine
from app.models.audit_log import AuditLog
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

async def debug_audit_logs():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        statement = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(5)
        result = await session.exec(statement)
        logs = result.all()

        print(f"Checking last 5 audit logs:")
        print("-" * 80)
        print(f"{'ID':<5} | {'Action':<20} | {'Target ID':<10} | {'Target Label'}")
        print("-" * 80)
        
        for log in logs:
            # We access attribute directly. If column doesn't exist in mapping, this might fail or show nothing if not loaded.
            # But model has it.
            label = getattr(log, 'target_label', 'N/A (Attr Missing)')
            print(f"{log.id:<5} | {log.action:<20} | {log.target_id:<10} | {label}")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(debug_audit_logs())

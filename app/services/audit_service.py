from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.audit_log import AuditLog

async def log_audit_event(
    session: AsyncSession,
    user_id: int,
    action: str,
    target_type: str,
    target_id: int,
    target_label: str = None,
    details: str = None
):
    print(f"DEBUG LOG: action={action}, label={target_label}")
    log = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        details=details
    )
    session.add(log)
    # Note: We assume the caller will commit the session, or we can flush here.
    # To be safe and ensure log is saved even if transaction continues, 
    # usually we might want a separate transaction, but for simplicity we join the current one.
    return log

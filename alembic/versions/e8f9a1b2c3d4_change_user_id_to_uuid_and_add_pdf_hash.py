"""Change user.id to UUID and add certificate_pdf_hash

Revision ID: e8f9a1b2c3d4
Revises: d5f8a3b2c4e1
Create Date: 2026-01-26

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e8f9a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d5f8a3b2c4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add certificate_pdf_hash to application table
    op.add_column(
        "application",
        sa.Column("certificate_pdf_hash", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_application_certificate_pdf_hash"),
        "application",
        ["certificate_pdf_hash"],
        unique=False,
    )
    
    # Step 2: Change user.id from INTEGER to UUID
    # This is a complex migration - we need to:
    # 1. Create new UUID column
    # 2. Generate UUIDs for existing users
    # 3. Update all foreign key references
    # 4. Drop old column and rename new one
    
    # Create temporary UUID column
    op.add_column("user", sa.Column("id_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    
    # Generate UUIDs for existing users
    connection = op.get_bind()
    users = connection.execute(sa.text("SELECT id FROM \"user\" ORDER BY id")).fetchall()
    for user_row in users:
        old_id = user_row[0]
        new_uuid = str(uuid.uuid4())
        connection.execute(
            sa.text("UPDATE \"user\" SET id_uuid = :uuid WHERE id = :old_id"),
            {"uuid": new_uuid, "old_id": old_id}
        )
    
    # Update foreign keys in application table
    op.add_column("application", sa.Column("user_id_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("application", sa.Column("assigned_to_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    
    # Map old user_id to new UUID
    connection.execute(sa.text("""
        UPDATE application 
        SET user_id_uuid = (SELECT id_uuid FROM "user" WHERE "user".id = application.user_id)
    """))
    connection.execute(sa.text("""
        UPDATE application 
        SET assigned_to_uuid = (SELECT id_uuid FROM "user" WHERE "user".id = application.assigned_to)
        WHERE assigned_to IS NOT NULL
    """))
    
    # Update foreign keys in notification table
    op.add_column("notification", sa.Column("user_id_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    connection.execute(sa.text("""
        UPDATE notification 
        SET user_id_uuid = (SELECT id_uuid FROM "user" WHERE "user".id = notification.user_id)
    """))
    
    # Update foreign keys in audit_log/auditlog table (if it exists)
    # Check for both table name variations
    try:
        result = connection.execute(sa.text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('audit_log', 'auditlog')
            LIMIT 1
        """))
        audit_table_row = result.fetchone()
        audit_table_name = audit_table_row[0] if audit_table_row else None
        audit_table_exists = audit_table_name is not None
        
        if audit_table_exists:
            op.add_column(audit_table_name, sa.Column("user_id_uuid", postgresql.UUID(as_uuid=True), nullable=True))
            connection.execute(sa.text(f"""
                UPDATE {audit_table_name} 
                SET user_id_uuid = (SELECT id_uuid FROM "user" WHERE "user".id = {audit_table_name}.user_id)
                WHERE user_id IS NOT NULL
            """))
    except Exception as e:
        # If table doesn't exist or query fails, skip audit table updates
        print(f"Note: audit table not found or error checking: {e}")
        audit_table_exists = False
        audit_table_name = None
    
    # CRITICAL: Drop ALL foreign key constraints that reference user.id BEFORE dropping the column
    # Find and drop all foreign key constraints that depend on user.id
    try:
        # Find all foreign key constraints that reference user.id
        fk_result = connection.execute(sa.text("""
            SELECT 
                tc.table_name,
                tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND ccu.table_name = 'user'
                AND ccu.column_name = 'id'
                AND tc.table_schema = 'public'
        """))
        
        fk_constraints = fk_result.fetchall()
        for table_name, constraint_name in fk_constraints:
            try:
                op.drop_constraint(constraint_name, table_name, type_="foreignkey", if_exists=True)
                print(f"Dropped foreign key constraint: {constraint_name} from {table_name}")
            except Exception as e:
                print(f"Warning: Could not drop constraint {constraint_name} from {table_name}: {e}")
    except Exception as e:
        print(f"Note: Error finding/dropping foreign key constraints: {e}")
    
    # Drop any remaining foreign key constraints (explicit ones we know about, with if_exists)
    # The dynamic query above should have already dropped them, but this is a safety net
    op.drop_constraint("application_user_id_fkey", "application", type_="foreignkey", if_exists=True)
    op.drop_constraint("application_assigned_to_fkey", "application", type_="foreignkey", if_exists=True)
    op.drop_constraint("notification_user_id_fkey", "notification", type_="foreignkey", if_exists=True)
    
    # Check for audit table name (auditlog or audit_log)
    try:
        result = connection.execute(sa.text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('audit_log', 'auditlog')
            LIMIT 1
        """))
        audit_table_row = result.fetchone()
        audit_table_name = audit_table_row[0] if audit_table_row else None
    except:
        audit_table_name = None
    
    # Drop old columns
    op.drop_column("application", "user_id")
    op.drop_column("application", "assigned_to")
    op.drop_column("notification", "user_id")
    
    if audit_table_name:
        op.drop_column(audit_table_name, "user_id")
    op.drop_column("user", "id")
    
    # Rename UUID columns to original names
    op.alter_column("user", "id_uuid", new_column_name="id")
    op.alter_column("application", "user_id_uuid", new_column_name="user_id")
    op.alter_column("application", "assigned_to_uuid", new_column_name="assigned_to")
    op.alter_column("notification", "user_id_uuid", new_column_name="user_id")
    
    # Check audit table existence again for column rename
    try:
        result = connection.execute(sa.text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('audit_log', 'auditlog')
            LIMIT 1
        """))
        audit_table_row = result.fetchone()
        audit_table_name = audit_table_row[0] if audit_table_row else None
    except:
        audit_table_name = None
    
    if audit_table_name:
        op.alter_column(audit_table_name, "user_id_uuid", new_column_name="user_id")
    
    # Set NOT NULL constraints
    op.alter_column("user", "id", nullable=False)
    op.alter_column("application", "user_id", nullable=True)  # Keep nullable for now
    op.alter_column("notification", "user_id", nullable=False)
    
    # CRITICAL: Set primary key on user.id BEFORE creating foreign keys
    # Foreign keys require the referenced column to have a unique constraint
    op.create_primary_key("user_pkey", "user", ["id"])
    
    # Recreate foreign key constraints (now that user.id has a primary key)
    op.create_foreign_key(
        "application_user_id_fkey",
        "application",
        "user",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "application_assigned_to_fkey",
        "application",
        "user",
        ["assigned_to"],
        ["id"],
    )
    op.create_foreign_key(
        "notification_user_id_fkey",
        "notification",
        "user",
        ["user_id"],
        ["id"],
    )
    # Check audit table existence for foreign key creation
    try:
        result = connection.execute(sa.text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('audit_log', 'auditlog')
            LIMIT 1
        """))
        audit_table_row = result.fetchone()
        audit_table_name = audit_table_row[0] if audit_table_row else None
    except:
        audit_table_name = None
    
    if audit_table_name:
        # Use appropriate constraint name based on table name
        constraint_name = f"{audit_table_name}_user_id_fkey"
        op.create_foreign_key(
            constraint_name,
            audit_table_name,
            "user",
            ["user_id"],
            ["id"],
        )


def downgrade() -> None:
    # This downgrade is complex and may cause data loss
    # It's recommended to backup before running
    op.drop_index(op.f("ix_application_certificate_pdf_hash"), table_name="application")
    op.drop_column("application", "certificate_pdf_hash")
    
    # Reverting UUID to INT is complex and may lose data
    # This is a simplified downgrade - may need manual intervention
    op.execute("""
        ALTER TABLE "user" ALTER COLUMN id TYPE INTEGER USING 1;
        ALTER TABLE application ALTER COLUMN user_id TYPE INTEGER USING 1;
        ALTER TABLE application ALTER COLUMN assigned_to TYPE INTEGER;
        ALTER TABLE notification ALTER COLUMN user_id TYPE INTEGER USING 1;
        ALTER TABLE audit_log ALTER COLUMN user_id TYPE INTEGER;
    """)

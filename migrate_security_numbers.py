import asyncio
import uuid
from sqlmodel import select
from app.db.session import engine
from app.models.application import Application, ApplicationStatus
from app.services.security_service import security_service
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

async def migrate_security_numbers():
    print("Migrating existing approved applications to XSCNS...")
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Fetch approved applications without a certificate number
        query = select(Application).where(
            Application.status == ApplicationStatus.APPROVED,
            Application.certificate_number == None
        )
        result = await session.exec(query)
        apps = result.all()
        
        print(f"Found {len(apps)} applications to migrate.")
        
        for app in apps:
            print(f"Processing App #{app.id}...")
            
            # Ensure internal_uid exists
            if not app.internal_uid:
                app.internal_uid = uuid.uuid4()
            
            # Generate Secure Number
            sec_data = security_service.generate_certificate_number(
                app.certificate_class, 
                app.internal_uid
            )
            
            app.certificate_number = sec_data["full_number"]
            app.security_token = sec_data["token"]
            
            # Populate issued_date if missing
            if not app.issued_date:
                app.issued_date = app.updated_at
            
            session.add(app)
            print(f" -> Assigned: {app.certificate_number}")
        
        await session.commit()
        print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_security_numbers())

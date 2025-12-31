from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.application import Application
from app.models.document import Document, DocumentRead, DocumentType
from app.models.user import User
from app.services.storage_service import storage_service

router = APIRouter()

async def verify_application_ownership(
    session: AsyncSession, application_id: int, user_id: int
) -> Application:
    """Helper to verify if an application belongs to a user."""
    application = await session.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return application

@router.post("/upload/", response_model=DocumentRead)
async def upload_document(
    application_id: int = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Upload a document to Supabase Storage.
    """
    await verify_application_ownership(session, application_id, current_user.id)

    # Validate document type
    try:
        doc_type_enum = DocumentType(document_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document type")

    # Upload to Supabase
    # Returns the storage path (e.g. user_123/app_456/uuid.pdf)
    storage_path = await storage_service.upload_file(file, current_user.id, application_id)

    # Create DB entry
    document = Document(
        application_id=application_id,
        document_type=doc_type_enum,
        filename=file.filename,
        file_url=storage_path # Store the path, not the full signed URL
    )
    
    session.add(document)

    # Update application step to 7 (Review) if it's less than 7
    # Note: Step logic might need adjustment based on your specific flow requirements
    application = await session.get(Application, application_id)
    if application and application.current_step < 7:
        application.current_step = 7
        session.add(application)

    await session.commit()
    await session.refresh(document)
    
    # Return with signed URL for immediate display
    document.file_url = storage_service.get_signed_url(document.file_url)
    return document

@router.get("/{application_id}", response_model=List[DocumentRead])
async def read_documents(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_id: int,
    current_user: User = Depends(deps.get_current_user),
):
    """
    List documents for a specific application.
    Generates Signed URLs for secure access.
    """
    await verify_application_ownership(session, application_id, current_user.id)

    documents = await session.exec(
        select(Document).where(Document.application_id == application_id)
    )
    docs = documents.all()
    
    # Convert paths to signed URLs
    # We return a list of Pydantic models with updated URLs
    result = []
    for doc in docs:
        # Create a copy/dict to avoid mutating the DB object attached to session
        doc_data = doc.dict() # or DocumentRead.from_orm(doc)
        # Update URL
        doc_data["file_url"] = storage_service.get_signed_url(doc.file_url)
        result.append(doc_data)
        
    return result

@router.delete("/{document_id}", status_code=204)
async def delete_document(
    *,
    session: AsyncSession = Depends(deps.get_session),
    document_id: int,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Delete a document from DB and Storage.
    """
    document = await session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    await verify_application_ownership(session, document.application_id, current_user.id)
    
    # Delete file from Supabase Storage
    # document.file_url holds the storage path
    if document.file_url:
        storage_service.delete_file(document.file_url)
        
    await session.delete(document)
    await session.commit()
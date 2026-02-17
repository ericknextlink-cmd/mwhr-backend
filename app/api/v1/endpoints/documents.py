import uuid
from typing import List
from datetime import datetime
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.application import Application
from app.models.document import Document, DocumentRead, DocumentType
from app.models.user import User
from app.services.storage_service import storage_service

router = APIRouter()

@router.post("/upload/", response_model=DocumentRead)
async def upload_document(
    application_id: str = Form(...),  # UUID (internal_uid)
    document_type: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Upload a document to Supabase Storage. application_id is the application UUID (internal_uid).
    If a document of the same type already exists, replaces it.
    """
    try:
        app_uid = uuid.UUID(application_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid application ID format")
    application = await deps.get_application_by_uid(session, app_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    try:
        doc_type_enum = DocumentType(document_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document type")
    
    existing_doc_query = select(Document).where(
        Document.application_id == application.id,
        Document.document_type == doc_type_enum
    )
    existing_doc_result = await session.exec(existing_doc_query)
    existing_document = existing_doc_result.first()

    storage_path = await storage_service.upload_file(file, application.id, document_type=doc_type_enum.value)

    old_file_url = None
    if existing_document:
        old_file_url = existing_document.file_url
        existing_document.previous_file_url = old_file_url
        existing_document.file_url = storage_path
        existing_document.filename = file.filename
        existing_document.uploaded_at = datetime.utcnow()
        document = existing_document
    else:
        document = Document(
            application_id=application.id,
            document_type=doc_type_enum,
            filename=file.filename,
            file_url=storage_path
        )
        session.add(document)

    if application.current_step < 7:
        application.current_step = 7
        session.add(application)

    await session.commit()
    await session.refresh(document)

    # Delete old file from storage after successful DB update
    if old_file_url:
        try:
            storage_service.delete_file(old_file_url)
        except Exception as e:
            # Log but don't fail the request - file is already replaced in DB
            print(f"Warning: Failed to delete old file {old_file_url}: {e}")

    # Return with signed URL for immediate display
    document.file_url = storage_service.get_signed_url(document.file_url)
    return document


@router.get("/download/{document_id}")
async def download_document(
    document_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Stream the document file with a friendly filename for download/preview.
    Content-Disposition uses the stored original filename so the browser shows a proper name.
    """
    document = await session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    application = await session.get(Application, document.application_id)
    if not application or application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    file_bytes = storage_service.download_file(document.file_url)
    if not file_bytes:
        raise HTTPException(status_code=404, detail="File not found in storage.")
    # Use original filename for download; sanitize for Content-Disposition
    display_name = (document.filename or "document").strip()
    if "/" in display_name or "\\" in display_name:
        display_name = display_name.replace("\\", "/").split("/")[-1]
    display_name = display_name.replace('"', "%22")
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{display_name}"'},
    )


@router.get("/{application_uid}", response_model=List[DocumentRead])
async def read_documents(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_uid: uuid.UUID,
    current_user: User = Depends(deps.get_current_user),
):
    """
    List documents for a specific application. application_uid is the application UUID (internal_uid).
    Generates Signed URLs for secure access.
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    documents = await session.exec(
        select(Document).where(Document.application_id == application.id)
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
    
    application = await session.get(Application, document.application_id)
    if not application or application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Delete file from Supabase Storage
    # document.file_url holds the storage path
    if document.file_url:
        storage_service.delete_file(document.file_url)
        
    await session.delete(document)
    await session.commit()
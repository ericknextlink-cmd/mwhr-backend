from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
import httpx
from app.api import deps
from app.models.user import User
from app.core.config import settings

router = APIRouter()

class AnalyzeDocumentRequest(BaseModel):
    document_url: HttpUrl
    document_type: str
    strategy: Optional[str] = "hi_res"
    use_ocr: Optional[bool] = True
    extract_tables: Optional[bool] = True
    extract_forms: Optional[bool] = False
    languages: Optional[List[str]] = ["eng"]
    application_company_name: Optional[str] = None
    thread_id: Optional[str] = None

class AnalyzeDocumentResponse(BaseModel):
    success: bool
    extracted_text: str
    analysis: str
    tables: List[dict] = []
    forms: List[dict] = []
    metadata: Optional[dict] = None
    error: Optional[str] = None
    company_match: Optional[bool] = None
    company_match_detail: Optional[str] = None

class ExtractDocumentRequest(BaseModel):
    document_url: HttpUrl
    use_ocr: Optional[bool] = True

class ExtractDocumentResponse(BaseModel):
    extracted_text: str
    success: bool = True

@router.post("/document", response_model=AnalyzeDocumentResponse)
async def analyze_document(
    request: AnalyzeDocumentRequest,
    current_user: User = Depends(deps.get_current_user),
):
    if not settings.AI_SERVICE_URL:
        raise HTTPException(
            status_code=503, 
            detail="AI Analysis service is not configured. Please set AI_SERVICE_URL."
        )

    # Call External AI Microservice
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            headers = {"x-api-key": settings.AI_SERVICE_API_KEY} if settings.AI_SERVICE_API_KEY else {}
            response = await client.post(
                f"{settings.AI_SERVICE_URL}/analyze",
                json=request.model_dump(mode="json"),
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"AI Service Error: {e}")
            raise HTTPException(
                status_code=502, 
                detail=f"AI Microservice error: {str(e)}"
            )

@router.post("/document-extract", response_model=ExtractDocumentResponse)
async def extract_document_text(
    request: ExtractDocumentRequest,
    current_user: User = Depends(deps.get_current_user),
):
    if not settings.AI_SERVICE_URL:
        raise HTTPException(
            status_code=503, 
            detail="AI Extraction service is not configured."
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            headers = {"x-api-key": settings.AI_SERVICE_API_KEY} if settings.AI_SERVICE_API_KEY else {}
            response = await client.post(
                f"{settings.AI_SERVICE_URL}/extract",
                json=request.model_dump(mode="json"),
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502, 
                detail=f"AI Microservice extraction error: {str(e)}"
            )

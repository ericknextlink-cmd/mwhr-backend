from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.user import User

try:
    from app.services.pdf_analysis_service import pdf_analysis_service
except ImportError as e:
    pdf_analysis_service = None

router = APIRouter()


class AnalyzeDocumentRequest(BaseModel):
    document_url: HttpUrl
    document_type: str
    strategy: Optional[str] = "hi_res"
    use_ocr: Optional[bool] = True
    extract_tables: Optional[bool] = True
    extract_forms: Optional[bool] = False
    languages: Optional[List[str]] = ["eng"]


class AnalyzeDocumentResponse(BaseModel):
    success: bool
    extracted_text: str
    analysis: str
    tables: List[dict] = []
    forms: List[dict] = []
    metadata: Optional[dict] = None
    error: Optional[str] = None


@router.post("/document", response_model=AnalyzeDocumentResponse)
async def analyze_document(
    request: AnalyzeDocumentRequest,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    if not pdf_analysis_service:
        raise HTTPException(
            status_code=500,
            detail="PDF analysis service is not available. Please ensure all dependencies are installed."
        )
    
    if not pdf_analysis_service.openai_api_key:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API key not configured. Please configure OPENAI_API_KEY in environment variables."
        )
    
    result = await pdf_analysis_service.analyze_document(
        document_url=str(request.document_url),
        document_type=request.document_type,
        strategy=request.strategy,
        use_ocr=request.use_ocr,
        extract_tables=request.extract_tables,
        extract_forms=request.extract_forms,
        languages=request.languages
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Failed to analyze document")
        )
    
    return AnalyzeDocumentResponse(**result)

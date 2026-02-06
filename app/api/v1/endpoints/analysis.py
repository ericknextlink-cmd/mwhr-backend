from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.user import User

# Lazy imports so app startup binds to PORT quickly (avoids loading torch/langchain/chromadb at import time)
def _get_pdf_analysis_service():
    try:
        from app.services.pdf_analysis_service import pdf_analysis_service
        return pdf_analysis_service
    except ImportError:
        return None

def _get_extract_text_from_pdf_url():
    try:
        from app.services.pdf_extract_local import extract_text_from_pdf_url
        return extract_text_from_pdf_url
    except ImportError:
        return None

router = APIRouter()


class AnalyzeDocumentRequest(BaseModel):
    document_url: HttpUrl
    document_type: str
    strategy: Optional[str] = "hi_res"
    use_ocr: Optional[bool] = True
    extract_tables: Optional[bool] = True
    extract_forms: Optional[bool] = False
    languages: Optional[List[str]] = ["eng"]
    # If provided, LLM must verify document company matches this name; mismatch => company_match=False
    application_company_name: Optional[str] = None


class AnalyzeDocumentResponse(BaseModel):
    success: bool
    extracted_text: str
    analysis: str
    tables: List[dict] = []
    forms: List[dict] = []
    metadata: Optional[dict] = None
    error: Optional[str] = None
    # Guard: document company must match application company
    company_match: Optional[bool] = None
    company_match_detail: Optional[str] = None


@router.post("/document", response_model=AnalyzeDocumentResponse)
async def analyze_document(
    request: AnalyzeDocumentRequest,
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(deps.get_session),
):
    pdf_analysis_service = _get_pdf_analysis_service()
    if not pdf_analysis_service:
        raise HTTPException(
            status_code=503,
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
        languages=request.languages,
        application_company_name=request.application_company_name,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Failed to analyze document")
        )
    
    return AnalyzeDocumentResponse(**result)


class ExtractDocumentRequest(BaseModel):
    document_url: HttpUrl
    use_ocr: Optional[bool] = True


class ExtractDocumentResponse(BaseModel):
    extracted_text: str
    success: bool = True


@router.post("/document-extract", response_model=ExtractDocumentResponse)
async def extract_document_text(
    request: ExtractDocumentRequest,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Extract text from a PDF (e.g. signed URL). Uses local PyMuPDF + OCR for scanned/image pages.
    Use this when the main analyze endpoint is unavailable or when you only need text (e.g. fallback).
    """
    extract_text_from_pdf_url = _get_extract_text_from_pdf_url()
    if not extract_text_from_pdf_url:
        raise HTTPException(
            status_code=503,
            detail="Local PDF extraction is not available. Install PyMuPDF (pymupdf)."
        )
    text = await extract_text_from_pdf_url(
        document_url=str(request.document_url),
        use_ocr=request.use_ocr,
    )
    return ExtractDocumentResponse(extracted_text=text or "", success=bool(text))

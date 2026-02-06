"""
Lightweight PDF text extraction with optional OCR for scanned/image pages.
Uses only PyMuPDF (fitz) + pytesseract so it can run when the full analysis service is not available.
"""
import os
import tempfile
import httpx

try:
    import fitz
except ImportError:
    fitz = None
try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


async def extract_text_from_pdf_url(document_url: str, use_ocr: bool = True) -> str:
    """
    Download PDF from URL and extract text. For each page with little/no text, run OCR.
    Returns combined text or empty string on failure.
    """
    if not fitz:
        return ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(document_url)
        response.raise_for_status()
        pdf_bytes = response.content
    if not pdf_bytes:
        return ""
    parts: list[str] = []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        try:
            tmp.write(pdf_bytes)
            tmp.flush()
            doc = fitz.open(tmp.name)
            try:
                for page_no in range(len(doc)):
                    page = doc[page_no]
                    text = (page.get_text() or "").strip()
                    if use_ocr and len(text) < 50 and pytesseract and Image:
                        mat = fitz.Matrix(2.0, 2.0)
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        text = (pytesseract.image_to_string(img) or "").strip()
                    if text:
                        parts.append(text)
            finally:
                doc.close()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    return "\n\n".join(parts) if parts else ""

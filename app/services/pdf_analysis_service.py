import httpx
import os
import tempfile
from typing import List, Dict, Any, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from app.core.config import settings

# Optional: local PDF + OCR (scanned/image pages)
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


class PDFAnalysisService:
    def __init__(self):
        self.openai_api_key = settings.OPENAI_API_KEY
        self.unstructured_api_key = settings.UNSTRUCTURED_API_KEY
        self.unstructured_api_url = settings.UNSTRUCTURED_API_URL or "https://api.unstructured.io"
        
    async def analyze_document(
        self,
        document_url: str,
        document_type: str,
        strategy: str = "hi_res",
        use_ocr: bool = True,
        extract_tables: bool = True,
        extract_forms: bool = False,
        languages: List[str] = None,
        application_company_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if languages is None:
            languages = ["eng"]
        
        documents: List[Document] = []
        try:
            if self.unstructured_api_key:
                documents = await self._load_document(
                    document_url=document_url,
                    strategy=strategy,
                    use_ocr=use_ocr,
                    extract_tables=extract_tables,
                    extract_forms=extract_forms,
                    languages=languages
                )
            if not documents and fitz:
                documents = await self._load_document_local(
                    document_url=document_url,
                    use_ocr=use_ocr,
                )
        except Exception:
            if fitz:
                try:
                    documents = await self._load_document_local(
                        document_url=document_url,
                        use_ocr=use_ocr,
                    )
                except Exception:
                    pass
        
        try:
            
            if not documents:
                return {
                    "success": False,
                    "error": "No content extracted from document",
                    "extracted_text": "",
                    "analysis": ""
                }
            
            extracted_text = self._combine_documents(documents)
            
            analysis = await self._analyze_content(
                extracted_text=extracted_text,
                document_type=document_type,
                documents=documents,
                application_company_name=application_company_name,
            )
            
            tables = self._extract_tables(documents)
            forms = self._extract_forms(documents) if extract_forms else []
            
            # Parse company match guard from analysis (LLM outputs COMPANY_MATCH: YES or COMPANY_MISMATCH: ...)
            company_match: Optional[bool] = None
            company_match_detail: Optional[str] = None
            if application_company_name and isinstance(analysis, str):
                if "COMPANY_MISMATCH:" in analysis:
                    company_match = False
                    idx = analysis.find("COMPANY_MISMATCH:")
                    end = analysis.find("\n", idx)
                    company_match_detail = (analysis[idx:end] if end != -1 else analysis[idx:]).strip()
                elif "COMPANY_MATCH: YES" in analysis or "COMPANY_MATCH:YES" in analysis:
                    company_match = True
            
            return {
                "success": True,
                "extracted_text": extracted_text,
                "analysis": analysis,
                "tables": tables,
                "forms": forms,
                "metadata": {
                    "document_type": document_type,
                    "strategy": strategy,
                    "pages_processed": len(documents),
                    "total_chars": len(extracted_text)
                },
                "company_match": company_match,
                "company_match_detail": company_match_detail,
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "analysis": ""
            }
    
    async def _load_document(
        self,
        document_url: str,
        strategy: str,
        use_ocr: bool,
        extract_tables: bool,
        extract_forms: bool,
        languages: List[str]
    ) -> List:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(document_url)
            response.raise_for_status()
            
            files = {
                "files": (os.path.basename(document_url), response.content, "application/pdf")
            }
            
            data = {
                "strategy": strategy,
                "infer_table_structure": "true" if extract_tables else "false",
                "extract_forms": "true" if extract_forms else "false",
            }
            
            if use_ocr and languages:
                data["languages"] = languages
            
            headers = {}
            if self.unstructured_api_key:
                headers["unstructured-api-key"] = self.unstructured_api_key
            
            api_response = await client.post(
                f"{self.unstructured_api_url}/general/v0/general",
                files=files,
                data=data,
                headers=headers
            )
            api_response.raise_for_status()
            
            result = api_response.json()
            elements = result if isinstance(result, list) else result.get("elements", [])
            
            documents = []
            for element in elements:
                text = element.get("text") or element.get("text_content")
                if text:
                    metadata = element.get("metadata", {})
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "type": element.get("type", "unknown"),
                            "page_number": metadata.get("page_number", 0),
                            "filename": metadata.get("filename", ""),
                            "filetype": metadata.get("filetype", "pdf")
                        }
                    ))
            
            return documents
    
    async def _load_document_local(
        self,
        document_url: str,
        use_ocr: bool = True,
    ) -> List[Document]:
        """Extract text from PDF using PyMuPDF; for pages with little/no text, run OCR (pytesseract). Handles scanned/image-only PDFs."""
        if not fitz:
            return []
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(document_url)
            response.raise_for_status()
            pdf_bytes = response.content
        if not pdf_bytes:
            return []
        documents = []
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
                            img = Image.frombytes(
                                "RGB", [pix.width, pix.height], pix.samples
                            )
                            text = (pytesseract.image_to_string(img) or "").strip()
                        if text:
                            documents.append(
                                Document(
                                    page_content=text,
                                    metadata={
                                        "type": "Page",
                                        "page_number": page_no + 1,
                                        "filename": os.path.basename(document_url),
                                        "filetype": "pdf",
                                    },
                                )
                            )
                finally:
                    doc.close()
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
        return documents
    
    def _combine_documents(self, documents: List) -> str:
        return "\n\n".join([doc.page_content for doc in documents if doc.page_content])
    
    def _extract_tables(self, documents: List) -> List[Dict[str, Any]]:
        tables = []
        for doc in documents:
            if doc.metadata.get("type") == "Table":
                tables.append({
                    "text": doc.page_content,
                    "html": doc.metadata.get("text_as_html", ""),
                    "page": doc.metadata.get("page_number", 0)
                })
        return tables
    
    def _extract_forms(self, documents: List) -> List[Dict[str, Any]]:
        forms = []
        for doc in documents:
            if doc.metadata.get("type") == "Form":
                forms.append({
                    "text": doc.page_content,
                    "page": doc.metadata.get("page_number", 0)
                })
        return forms
    
    async def _analyze_content(
        self,
        extracted_text: str,
        document_type: str,
        documents: List,
        application_company_name: Optional[str] = None,
    ) -> str:
        if not self.openai_api_key:
            return "OpenAI API key not configured. Analysis unavailable."
        
        if not extracted_text or len(extracted_text.strip()) < 50:
            return "Insufficient text extracted from document for analysis."
        
        try:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
            
            splits = text_splitter.split_documents(documents)
            
            embeddings = OpenAIEmbeddings(openai_api_key=self.openai_api_key)
            vectorstore = Chroma.from_documents(
                documents=splits,
                embedding=embeddings
            )
            
            retriever = vectorstore.as_retriever(k=4)
            
            llm = ChatOpenAI(
                model_name="gpt-4o-mini",
                temperature=0,
                openai_api_key=self.openai_api_key
            )
            
            company_guard = ""
            if application_company_name:
                company_guard = """
CRITICAL - Company name verification (mandatory):
This document is being reviewed for an application submitted on behalf of the company: "{application_company_name}".
- Extract ALL company names mentioned in the document (e.g. on certificates, letterheads, forms).
- If the document clearly refers to a DIFFERENT company (different name) than the application company above, you MUST output exactly one line at the END of your analysis: COMPANY_MISMATCH: The document refers to [company name(s) from document] which does not match the application company ({application_company_name}). This document does not belong to this application.
- If the document clearly refers to the SAME company (or the same legal entity) as the application company, output at the END: COMPANY_MATCH: YES
- Do not approve or state that the document is compliant if there is a company name mismatch; treat mismatch as a critical compliance failure.
"""
            
            template_str = """Analyze this {document_type} document for completeness, accuracy, and compliance with ministry requirements.
{company_guard}

Extract and verify:
- Company details (name, registration number, address)
- Registration dates and validity periods
- Required certifications and clearances
- Director information
- Any missing or incomplete information
- Compliance issues or discrepancies

Document Content:
{context}

Provide a comprehensive analysis focusing on compliance, completeness, and any issues that need attention. At the end, you MUST output either COMPANY_MATCH: YES or COMPANY_MISMATCH: [reason] as specified above if an application company name was provided."""
            template_str = template_str.replace("{company_guard}", company_guard if application_company_name else "").replace("{application_company_name}", application_company_name or "")
            prompt_template = PromptTemplate(
                input_variables=["context", "document_type"],
                template=template_str,
            )
            
            qa_chain = RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",
                retriever=retriever,
                chain_type_kwargs={"prompt": prompt_template}
            )
            
            query = f"Analyze this {document_type} document for compliance and completeness"
            result = qa_chain.invoke({"query": query, "document_type": document_type})
            
            return result.get("result", "Analysis completed but no result returned.")
            
        except Exception as e:
            return f"Analysis error: {str(e)}"


pdf_analysis_service = PDFAnalysisService()

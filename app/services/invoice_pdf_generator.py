"""
Generate the 2-page post-payment PDF using templates:
Page 1 = invoice.pdf (Letter)
Page 2 = invoice2.pdf (Invoice Details)
Overlays dynamic text, barcodes, and QR codes onto the provided templates.
"""
import os
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import qrcode
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4

from app.core.config import settings
from app.models.application import Application
from app.models.company_info import CompanyInfo
from app.services.storage_service import storage_service

try:
    import barcode
    from barcode.writer import ImageWriter
    _BARCODE_AVAILABLE = True
except ImportError:
    _BARCODE_AVAILABLE = False

# Resolve paths relative to this file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = BASE_DIR / "certificate_templates"

def _format_date(d: datetime) -> str:
    if not hasattr(d, "strftime"):
        return str(d)
    return d.strftime("%d %B %Y")

def _make_barcode_image(serial_code: str) -> Optional[BytesIO]:
    """Return a vertical (rotated) barcode image for the serial code."""
    if not _BARCODE_AVAILABLE:
        return None
    barcode_payload = "".join(c for c in serial_code if c.isalnum())[:40]
    if not barcode_payload:
        barcode_payload = serial_code.replace("-", "")[:40]
    try:
        code128 = barcode.get_barcode_class("code128")
        writer = code128(barcode_payload, writer=ImageWriter())
        buf = BytesIO()
        writer.write(buf, options={"module_height": 8.0, "quiet_zone": 2.0, "font_size": 26, "write_text": False})
        buf.seek(0)
        
        # Rotate using PIL
        from PIL import Image
        img = Image.open(buf).convert("RGB")
        rotated = img.rotate(90, expand=True)
        out = BytesIO()
        rotated.save(out, format="PNG")
        out.seek(0)
        return out
    except Exception:
        return None

def _make_qr_image(data: str, box_size: int = 4) -> BytesIO:
    qr = qrcode.QRCode(box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

class InvoicePdfGenerator:
    # Layout constants (A4 default)
    BARCODE_MARGIN_LEFT = 114
    CONTENT_LEFT = 400
    MARGIN_RIGHT = 50
    # Adjusted top margin assuming header is in template
    # Previous code had MARGIN_TOP = 52. If template has header, we start writing below it.
    # Let's assume header takes ~100-120pt.
    CONTENT_TOP_START = 2750
    MARGIN_BOTTOM = 1700
    MARGIN_BOTTOM_QR = 200

    def __init__(self):
        self.font_regular = "Helvetica"
        self.font_bold = "Helvetica-Bold"
        self.font_size_body = 38
        self.font_size_body2 = 34
        self.font_size_heading = 30
        self.font_size_small = 18

    def _get_template_buffer(self, filename: str) -> BytesIO:
        # Production: load from Supabase Storage (same bucket/path as certificates: templates/)
        if storage_service.client and settings.SUPABASE_BUCKET_NAME:
            content = storage_service.download_file(f"templates/{filename}")
            if content:
                return BytesIO(content)
        # Local / testing: load from certificate_templates/
        path = TEMPLATE_DIR / filename
        if path.exists():
            with open(path, "rb") as f:
                return BytesIO(f.read())
        # Template missing everywhere
        print(f"Warning: Template {filename} not found (Supabase or local at {path})")
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.drawString(100, 700, f"Template {filename} missing")
        c.save()
        buf.seek(0)
        return buf

    def _draw_page1_overlay(
        self,
        c: canvas.Canvas,
        width: float,
        height: float,
        company: Optional[CompanyInfo],
        application: Application,
        invoice_number: str,
        invoice_date: datetime,
        payment_due_date: datetime,
        serial_code: str,
        qr_data: str,
    ) -> None:
        """
        Draw dynamic content for Page 1 (Letter).
        Assumes template has Header and Footer structure.
        """
        x = self.CONTENT_LEFT
        QR_X = 88
        y = self.CONTENT_TOP_START

        # 1. Company Details (Left)
        c.setFont(self.font_regular, self.font_size_body)
        
        company_name = company.company_name if company else "Applicant"
        reg_no = company.registration_number if company else "—"
        if company:
            address = company.address or (f"{company.city or ''}, {company.country or ''}".strip()).strip(", ")
        else:
            address = "—"
        if not address or address == ",":
            address = "—"
        phone = company.phone_number if company else "—"
        email_company = company.email if company else "—"

        c.drawString(x, y, f"Company Name: {company_name}")
        y -= 54
        c.drawString(x, y, f"Business Registration No.: {reg_no}")
        y -= 54
        c.drawString(x, y, f"Address: {address}")
        y -= 54
        c.drawString(x, y, f"Phone: {phone}")
        y -= 54
        c.drawString(x, y, f"Email: {email_company}")
        y -= 320  # Gap before body

        # 2. Letter Body
        # Subject
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(x, y, "Re: Payment Advice for Certificate of Classification Application")
        y -= 140
        
        # Salutation
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(x, y, f"Dear {company_name},")
        y -= 120

        # Paragraph 1
        cert_type = getattr(application.certificate_type, "value", str(application.certificate_type)).replace("_", " ").title()
        
        # "We acknowledge receipt of your application for a [Certificate of Classification- {type}] under the [Ministry of Works, Housing and Water Resources]."
        text_start = "We acknowledge receipt of your application for a "
        c.drawString(x, y, text_start)
        cur_x = x + c.stringWidth(text_start, self.font_bold, self.font_size_body)
        
        text_bold1 = f"Certificate of Classification- {cert_type}"
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(cur_x, y, text_bold1)
        cur_x += c.stringWidth(text_bold1, self.font_bold, self.font_size_body)
        
        text_mid = " under the"
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(cur_x, y, text_mid)
        y -= 80

        text_bold2 = "Ministry of Works, Housing and Water Resources."
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(x, y, text_bold2)
        y -= 160

        # Paragraph 2 & 3 (line breaks: after "This is to", after "the Classification", then "within 24 hours.")
        c.setFont(self.font_bold, self.font_size_body)
        text_p2_1 = "Please find attached your official payment advice ("
        c.drawString(x, y, text_p2_1)
        cur_x = x + c.stringWidth(text_p2_1, self.font_bold, self.font_size_body)
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(cur_x, y, invoice_number)
        cur_x += c.stringWidth(invoice_number, self.font_bold, self.font_size_body)
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(cur_x, y, ") for the application. This is to")
        y -= 80

        c.drawString(x, y, "confirm your payment for the said application. Your Application will undergo a review by the Classification")
        y -= 80

        c.drawString(x, y, "Certificate Processing Unit and its status will be determined within 24 hours.")
        y -= 160

        # Paragraph 4 (line break after "Please keep this")
        c.drawString(x, y, "For verification, the payment advice includes a unique serial number and QR code. Please keep this")
        y -= 80
        c.drawString(x, y, "document for your records.")
        y -= 160
        
        ministry_email = getattr(settings, "MINISTRY_EMAIL", "info@mwhwr.gov.gh")
        c.drawString(x, y, f"For assistance, contact us at {ministry_email} or call +233 2268 3737")
        y -= 140
        c.drawString(x, y, "Thank you for your cooperation.")
        
        # 3. Barcodes & QR
        # Vertical barcode (Left margin)
        # Draw white background rectangle to cover template placeholder
        barcode_h = 20
        barcode_w = 20 # wider to cover text too
        c.setFillColorRGB(1, 1, 1) # White
        c.rect(self.BARCODE_MARGIN_LEFT - 2, self.MARGIN_BOTTOM + 45, barcode_w, barcode_h + 5, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0) # Back to black

        barcode_buf = _make_barcode_image(serial_code)
        if barcode_buf:
            try:
                # Positioned low on the left
                c.drawImage(ImageReader(barcode_buf), self.BARCODE_MARGIN_LEFT - 20, self.MARGIN_BOTTOM + 35, width=200, height=740)
            finally:
                barcode_buf.close()

        # Serial code text: separate from barcode, rotated
        c.saveState()
        c.translate(self.BARCODE_MARGIN_LEFT + 74, self.MARGIN_BOTTOM - 702)
        c.rotate(90)
        c.setFont(self.font_regular, self.font_size_body2)
        c.drawString(0, 0, serial_code)
        c.restoreState()

        # QR Code (Bottom Left, near footer)
        # Draw white background square to cover template placeholder
        c.setFillColorRGB(1, 1, 1)
        c.rect(QR_X - 2, self.MARGIN_BOTTOM_QR - 2, 166, 166, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)

        qr_buf = _make_qr_image(qr_data)
        c.drawImage(ImageReader(qr_buf), QR_X + 60, self.MARGIN_BOTTOM_QR, width=166, height=166)
        qr_buf.close()

    def _draw_page2_overlay(
        self,
        c: canvas.Canvas,
        width: float,
        height: float,
        company: Optional[CompanyInfo],
        application: Application,
        invoice_number: str,
        application_ref: str,
        invoice_date: datetime,
        payment_due_date: datetime,
        serial_code: str,
        qr_data: str,
        application_fee: float,
        processing_fee: float,
    ) -> None:
        """
        Draw dynamic content for Page 2 (Invoice).
        Assumes template has fields/grid. We just fill values.
        """
        x = self.CONTENT_LEFT
        # Assume start y is similar to page 1
        y = 2800

        # Invoice Header Info
        c.setFont(self.font_regular, self.font_size_body)
        c.drawString(x, y, f"Invoice Number: {invoice_number}")
        y -= 52
        c.drawString(x, y, f"Application Reference: {application_ref}")
        y -= 52
        c.setFont(self.font_regular, self.font_size_body)
        c.drawString(x, y, f"Invoice Date: {_format_date(invoice_date)}")
        y -= 52
        c.drawString(x, y, f"Payment Due Date: {_format_date(payment_due_date)}")
        y -= 140

        # Billed To
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(x, y, "Billed To")
        y -= 52
        c.setFont(self.font_regular, self.font_size_body)
        
        company_name = company.company_name if company else "Applicant"
        c.drawString(x, y, f"Company Name: {company_name}")
        y -= 54
        reg_no = company.registration_number if company else "—"
        c.drawString(x, y, f"Business Registration No.: {reg_no}")
        y -= 54
        phone = company.phone_number if company else "—"
        c.drawString(x, y, f"Phone: {phone}")
        y -= 54
        email = company.email if company else "—"
        c.drawString(x, y, f"Email: {email}")
        y -= 250
        
        cert_type = getattr(application.certificate_type, "value", str(application.certificate_type)).replace("_", " ").title()
        
        # Item 1
        c.setFont(self.font_regular, self.font_size_body)
        c.drawString(x + 280, y, f"Certificate of Classification {cert_type} Application Fee")
        # Amount aligned right
        amt_x = width - self.MARGIN_RIGHT
        c.drawRightString(amt_x -100, y, f"{application_fee:,.2f}")
        y -= 170

        # Item 2
        c.drawString(x + 280, y, "Processing & Administrative Fee")
        c.drawRightString(amt_x - 100, y, f"{processing_fee:,.2f}")
        y -= 240

        # Total
        c.setFont(self.font_bold, self.font_size_body)
        total = application_fee + processing_fee
        # c.drawString(x, y, "Total Amount Payable:")
        c.drawRightString(amt_x - 100, y, f"{total:,.2f}")
        y -= 120
        
        # Barcodes & QR (same layout as Page 1)
        # Vertical barcode — same white rect and image size/position as page 1
        barcode_h = 20
        barcode_w = 20
        c.setFillColorRGB(1, 1, 1)
        c.rect(self.BARCODE_MARGIN_LEFT - 2, self.MARGIN_BOTTOM + 45, barcode_w, barcode_h + 5, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)

        barcode_buf = _make_barcode_image(serial_code)
        if barcode_buf:
            try:
                c.drawImage(ImageReader(barcode_buf), self.BARCODE_MARGIN_LEFT - 20, self.MARGIN_BOTTOM + 35, width=200, height=740)
            finally:
                barcode_buf.close()

        # Serial code text: same as page 1 (rotated, same font and position)
        c.saveState()
        c.translate(self.BARCODE_MARGIN_LEFT + 74, self.MARGIN_BOTTOM - 702)
        c.rotate(90)
        c.setFont(self.font_regular, self.font_size_body2)
        c.drawString(0, 0, serial_code)
        c.restoreState()

        # QR (same size and positioning as page 1)
        QR_X = 88
        MARGIN_BOTTOM_QR = 200
        c.setFillColorRGB(1, 1, 1)
        c.rect(QR_X - 2, MARGIN_BOTTOM_QR - 2, 166, 166, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)

        qr_buf = _make_qr_image(qr_data)
        c.drawImage(ImageReader(qr_buf), QR_X + 60, MARGIN_BOTTOM_QR, width=166, height=166)
        qr_buf.close()


    def generate(
        self,
        application: Application,
        company: Optional[CompanyInfo] = None,
    ) -> Tuple[BytesIO, str]:
        """
        Generate 2-page invoice PDF by overlaying data on templates.
        """
        invoice_date = datetime.now(timezone.utc)
        due_days = getattr(settings, "INVOICE_PAYMENT_DAYS_DUE", 7)
        payment_due_date = invoice_date + timedelta(days=due_days)
        invoice_number = f"INV-{invoice_date.year}-{application.id:06d}"
        application_ref = application.certificate_number or f"MWHWR-CC-{invoice_date.year}-{application.id:05d}"
        serial_code = f"MWHWR-CC-{invoice_date.strftime('%Y%m%d')}-{application.id:06d}"
        qr_data = f"{application_ref}|{invoice_number}|{serial_code}"

        application_fee = getattr(settings, "INVOICE_APPLICATION_FEE_GHS", 1000.0)
        processing_fee = getattr(settings, "INVOICE_PROCESSING_FEE_GHS", 500.0)

        writer = PdfWriter()

        # --- Process Page 1 (Letter) ---
        template1 = self._get_template_buffer("invoice.pdf")
        reader1 = PdfReader(template1)
        if len(reader1.pages) > 0:
            page1 = reader1.pages[0]
            width1 = float(page1.mediabox.width)
            height1 = float(page1.mediabox.height)
            
            overlay1_buf = BytesIO()
            c1 = canvas.Canvas(overlay1_buf, pagesize=(width1, height1))
            self._draw_page1_overlay(
                c1, width1, height1, company, application, invoice_number, 
                invoice_date, payment_due_date, serial_code, qr_data
            )
            c1.save()
            overlay1_buf.seek(0)
            
            # Merge
            page1.merge_page(PdfReader(overlay1_buf).pages[0])
            writer.add_page(page1)

        # --- Process Page 2 (Invoice) ---
        template2 = self._get_template_buffer("invoice2.pdf")
        reader2 = PdfReader(template2)
        if len(reader2.pages) > 0:
            page2 = reader2.pages[0]
            width2 = float(page2.mediabox.width)
            height2 = float(page2.mediabox.height)
            
            overlay2_buf = BytesIO()
            c2 = canvas.Canvas(overlay2_buf, pagesize=(width2, height2))
            self._draw_page2_overlay(
                c2, width2, height2, company, application, invoice_number, 
                application_ref, invoice_date, payment_due_date, serial_code, qr_data,
                application_fee, processing_fee
            )
            c2.save()
            overlay2_buf.seek(0)
            
            # Merge
            page2.merge_page(PdfReader(overlay2_buf).pages[0])
            writer.add_page(page2)

        output = BytesIO()
        writer.write(output)
        output.seek(0)
        return output, invoice_number

invoice_pdf_generator = InvoicePdfGenerator()

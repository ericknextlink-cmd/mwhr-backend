"""
Generate the 2-page post-payment PDF: Page 1 = informing letter, Page 2 = invoice.
Includes vertical serial barcode and QR code. No template PDF; fully generated in code.
"""
from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Optional, Tuple

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.core.config import settings
from app.models.application import Application
from app.models.company_info import CompanyInfo

try:
    import barcode
    from barcode.writer import ImageWriter
    _BARCODE_AVAILABLE = True
except ImportError:
    _BARCODE_AVAILABLE = False


def _format_date(d: datetime) -> str:
    if not hasattr(d, "strftime"):
        return str(d)
    return d.strftime("%d %B %Y")


def _make_barcode_image(serial_code: str) -> Optional[BytesIO]:
    """Return a vertical (rotated) barcode image for the serial code, or None if barcode lib missing."""
    if not _BARCODE_AVAILABLE:
        return None
    # Code128 accepts ASCII; use alphanumeric only to avoid encoding issues across implementations
    barcode_payload = "".join(c for c in serial_code if c.isalnum())[:40]
    if not barcode_payload:
        barcode_payload = serial_code.replace("-", "")[:40]
    try:
        code128 = barcode.get_barcode_class("code128")
        writer = code128(barcode_payload, writer=ImageWriter())
        buf = BytesIO()
        writer.write(buf, options={"module_height": 8.0, "quiet_zone": 2.0, "font_size": 6})
        buf.seek(0)
        try:
            from PIL import Image
            img = Image.open(buf).convert("RGB")
            rotated = img.rotate(90, expand=True)
            out = BytesIO()
            rotated.save(out, format="PNG")
            out.seek(0)
            return out
        except Exception:
            buf.seek(0)
            return buf
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
    def __init__(self):
        self.font_regular = "Helvetica"
        self.font_bold = "Helvetica-Bold"
        self.font_size_title = 16
        self.font_size_heading = 11
        self.font_size_body = 10
        self.font_size_small = 8
        self.margin_left = 90  # leave space for vertical barcode
        self.margin_right = 50
        self.margin_top = 80
        self.margin_bottom = 60
        self.page_w, self.page_h = A4

    def _draw_header(self, c: canvas.Canvas, page_label: str = "") -> None:
        """Draw ministry header (logo placeholder, name, contact)."""
        y = self.page_h - self.margin_top
        c.setFont(self.font_bold, self.font_size_title)
        c.drawString(self.margin_left, y, getattr(settings, "MINISTRY_NAME", "Ministry of Works, Housing & Water Resources"))
        y -= 6
        c.setFont(self.font_regular, self.font_size_small)
        addr = getattr(settings, "MINISTRY_ADDRESS", "Ministries Area, Off Starlets 91 Road, Accra, Ghana, P.O. Box M43, Ministries - Accra, Digital Address: GA-144-0550")
        for line in addr.split(", "):
            c.drawString(self.margin_left, y, line.strip())
            y -= 10
        phone = getattr(settings, "MINISTRY_PHONE", "+233 (0)577 902 988 / +233 (0)577 902 933")
        email = getattr(settings, "MINISTRY_EMAIL", "info@mwhwr.gov.gh")
        c.drawString(self.margin_left, y, f"{phone}  |  {email}")
        if page_label:
            c.setFont(self.font_regular, self.font_size_small)
            c.drawRightString(self.page_w - self.margin_right, self.margin_bottom, page_label)

    def _draw_letter_page(
        self,
        c: canvas.Canvas,
        company: Optional[CompanyInfo],
        application: Application,
        invoice_number: str,
        invoice_date: datetime,
        payment_due_date: datetime,
        serial_code: str,
        qr_data: str,
    ) -> None:
        """Page 1: Informing letter."""
        y = self.page_h - self.margin_top - 50
        c.setFont(self.font_regular, self.font_size_body)

        company_name = company.company_name if company else "Applicant"
        reg_no = company.registration_number if company else "—"
        address = company.address or (f"{company.city or ''}, {company.country or ''}".strip() if company else "—")
        if not address or address == ",":
            address = "—"
        phone = company.phone_number if company else "—"
        email = company.email if company else "—"

        c.drawString(self.margin_left, y, company_name)
        y -= 14
        c.drawString(self.margin_left, y, f"Business Registration No.: {reg_no}")
        y -= 14
        c.drawString(self.margin_left, y, f"Address: {address}")
        y -= 14
        c.drawString(self.margin_left, y, f"Phone: {phone}")
        y -= 14
        c.drawString(self.margin_left, y, f"Email: {email}")
        y -= 24

        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(self.margin_left, y, "Re: Invoice for Certificate of Classification Application")
        y -= 24
        c.setFont(self.font_regular, self.font_size_body)

        salutation = f"Dear {company_name},"
        c.drawString(self.margin_left, y, salutation)
        y -= 18

        c.drawString(self.margin_left, y, "We acknowledge receipt of your application for a Certificate of Classification under the Ministry of Works, Housing and Water Resources.")
        y -= 18
        c.drawString(self.margin_left, y, f"Please find attached your official invoice ({invoice_number}) for the application. Kindly proceed with payment using the instructions provided in the invoice. Payment must be completed by {_format_date(payment_due_date)} to avoid delays in processing your application.")
        y -= 18
        c.drawString(self.margin_left, y, "For verification, the invoice includes a unique serial number and QR code. Please keep this document for your records.")
        y -= 18
        c.drawString(self.margin_left, y, f"For assistance, contact us at {getattr(settings, 'MINISTRY_EMAIL', 'info@mwhwr.gov.gh')} or call +233 2268 3737")
        y -= 18
        c.drawString(self.margin_left, y, "Thank you for your cooperation.")
        y -= 40

        c.setFont(self.font_regular, self.font_size_small)
        c.drawString(self.margin_left, y, "Issued By:")
        c.drawString(self.margin_left, y - 10, "Certificate Processing Unit")
        c.drawString(self.margin_left, y - 20, "Ministry of Works, Housing and Water Resources (MWHWR)")

        # Vertical serial text (left margin)
        c.saveState()
        c.translate(28, self.page_h // 2)
        c.rotate(90)
        c.setFont(self.font_regular, 8)
        c.drawString(0, 0, serial_code)
        c.restoreState()

        # QR code bottom left
        qr_buf = _make_qr_image(qr_data)
        c.drawImage(ImageReader(qr_buf), self.margin_left, self.margin_bottom, width=50, height=50)
        qr_buf.close()

        # Vertical barcode (left margin)
        barcode_buf = _make_barcode_image(serial_code)
        if barcode_buf:
            try:
                c.drawImage(ImageReader(barcode_buf), 12, self.margin_bottom, width=55, height=180)
            finally:
                barcode_buf.close()

        self._draw_header(c, "1 of 2")

    def _draw_invoice_page(
        self,
        c: canvas.Canvas,
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
        """Page 2: Invoice with line items."""
        y = self.page_h - self.margin_top - 40
        c.setFont(self.font_bold, self.font_size_heading)
        c.drawString(self.margin_left, y, f"Invoice Number: {invoice_number}")
        y -= 12
        c.drawString(self.margin_left, y, f"Application Reference: {application_ref}")
        y -= 12
        c.setFont(self.font_regular, self.font_size_body)
        c.drawString(self.margin_left, y, f"Invoice Date: {_format_date(invoice_date)}")
        y -= 10
        c.drawString(self.margin_left, y, f"Payment Due Date: {_format_date(payment_due_date)}")
        y -= 24

        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(self.margin_left, y, "Billed To")
        y -= 12
        c.setFont(self.font_regular, self.font_size_body)
        company_name = company.company_name if company else "Applicant"
        reg_no = company.registration_number if company else "—"
        address = company.address or (f"{company.city or ''}, {company.country or ''}".strip() if company else "—")
        if not address or address == ",":
            address = "—"
        phone = company.phone_number if company else "—"
        email = company.email if company else "—"
        c.drawString(self.margin_left, y, f"Company Name: {company_name}")
        y -= 10
        c.drawString(self.margin_left, y, f"Business Registration No.: {reg_no}")
        y -= 10
        c.drawString(self.margin_left, y, f"Address: {address}")
        y -= 10
        c.drawString(self.margin_left, y, f"Phone: {phone}")
        y -= 10
        c.drawString(self.margin_left, y, f"Email: {email}")
        y -= 24

        cert_type = getattr(application.certificate_type, "value", str(application.certificate_type)).replace("_", " ").title()
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(self.margin_left, y, "Line Items")
        y -= 14
        c.setFont(self.font_regular, self.font_size_body)
        c.drawString(self.margin_left, y, "No. 1")
        c.drawString(self.margin_left + 80, y, f"Certificate of Classification {cert_type} Application Fee")
        c.drawRightString(self.page_w - self.margin_right, y, f"{application_fee:,.2f} GHS")
        y -= 16
        c.drawString(self.margin_left, y, "No. 2")
        c.drawString(self.margin_left + 80, y, "Processing & Administrative Fee")
        c.drawRightString(self.page_w - self.margin_right, y, f"{processing_fee:,.2f} GHS")
        y -= 24
        total = application_fee + processing_fee
        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(self.margin_left, y, f"Total Amount Payable: {total:,.2f} GHS")
        y -= 28

        c.setFont(self.font_bold, self.font_size_body)
        c.drawString(self.margin_left, y, "Payment Instructions")
        y -= 12
        c.setFont(self.font_regular, self.font_size_small)
        c.drawString(self.margin_left, y, "USSD: Dial *222# and enter your Application Reference Number")
        y -= 10
        c.drawString(self.margin_left, y, "Online Portal: Log in and click Make Payment")
        y -= 10
        c.drawString(self.margin_left, y, "Mobile Money / Card: Available via the portal")
        y -= 18
        c.setFont(self.font_regular, self.font_size_small)
        c.drawString(self.margin_left, y, "Note:")
        y -= 10
        c.drawString(self.margin_left, y, "• This is a system-generated invoice and does not require a signature.")
        y -= 10
        c.drawString(self.margin_left, y, "• Application processing will begin only after payment confirmation.")
        y -= 28

        c.setFont(self.font_regular, self.font_size_small)
        c.drawString(self.margin_left, y, "Issued By:")
        c.drawString(self.margin_left, y - 10, "Certificate Processing Unit")
        c.drawString(self.margin_left, y - 20, "Ministry of Works, Housing and Water Resources (MWHWR)")

        # Vertical serial text
        c.saveState()
        c.translate(28, self.page_h // 2)
        c.rotate(90)
        c.setFont(self.font_regular, 8)
        c.drawString(0, 0, serial_code)
        c.restoreState()

        # QR code
        qr_buf = _make_qr_image(qr_data)
        c.drawImage(ImageReader(qr_buf), self.margin_left, self.margin_bottom, width=50, height=50)
        qr_buf.close()

        # Vertical barcode
        barcode_buf = _make_barcode_image(serial_code)
        if barcode_buf:
            try:
                c.drawImage(ImageReader(barcode_buf), 12, self.margin_bottom, width=55, height=180)
            finally:
                barcode_buf.close()

        self._draw_header(c, "2 of 2")

    def generate(
        self,
        application: Application,
        company: Optional[CompanyInfo] = None,
    ) -> Tuple[BytesIO, str]:
        """
        Generate 2-page invoice PDF (letter + invoice). Returns (buffer, invoice_number).
        Uses application.id for invoice number and serial; fees from settings.
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

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)

        # Page 1: Letter
        self._draw_letter_page(
            c, company, application, invoice_number, invoice_date, payment_due_date, serial_code, qr_data
        )
        c.showPage()

        # Page 2: Invoice
        self._draw_invoice_page(
            c, company, application, invoice_number, application_ref, invoice_date, payment_due_date,
            serial_code, qr_data, application_fee, processing_fee
        )

        c.save()
        buf.seek(0)
        return buf, invoice_number


invoice_pdf_generator = InvoicePdfGenerator()

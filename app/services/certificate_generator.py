import os
import qrcode
import hashlib
from typing import Tuple, Optional
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from datetime import datetime
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
from app.core.config import settings

from app.services.storage_service import storage_service

# Resolve paths relative to this file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = str(BASE_DIR / "certificate_templates")
FONT_DIR = str(BASE_DIR / "fonts")

class CertificateGenerator:
    def __init__(self):
        self.template_cache = {}
        self.fonts = {
            'regular': 'Times-Roman',
            'bold': 'Times-Bold',
            'italic': 'Times-Italic',
            'bold_italic': 'Times-BoldItalic'
        }
        
        try:
            if os.path.exists(os.path.join(FONT_DIR, 'Century Gothic.TTF')):
                pdfmetrics.registerFont(TTFont('Century Gothic', os.path.join(FONT_DIR, 'Century Gothic.TTF')))
                self.fonts['regular'] = 'Century Gothic'
                
            if os.path.exists(os.path.join(FONT_DIR, 'Century Gothic Bold.TTF')):
                pdfmetrics.registerFont(TTFont('Century Gothic-Bold', os.path.join(FONT_DIR, 'Century Gothic Bold.TTF')))
                self.fonts['bold'] = 'Century Gothic-Bold'

            if os.path.exists(os.path.join(FONT_DIR, 'Century Gothic Italic.TTF')):
                pdfmetrics.registerFont(TTFont('Century Gothic-Italic', os.path.join(FONT_DIR, 'Century Gothic Italic.TTF')))
                self.fonts['italic'] = 'Century Gothic-Italic'

            if os.path.exists(os.path.join(FONT_DIR, 'Century Gothic Bold Italic.TTF')):
                pdfmetrics.registerFont(TTFont('Century Gothic-BoldItalic', os.path.join(FONT_DIR, 'Century Gothic Bold Italic.TTF')))
                self.fonts['bold_italic'] = 'Century Gothic-BoldItalic'
        except Exception as e:
            print(f"Warning: Could not register fonts: {e}")

    def get_template_bytes(self, template_name: str) -> BytesIO | None:
        if template_name in self.template_cache:
            return BytesIO(self.template_cache[template_name])

        file_bytes = storage_service.download_file(f"templates/{template_name}")
        if file_bytes:
            self.template_cache[template_name] = file_bytes
            return BytesIO(file_bytes)
        
        local_path = os.path.join(TEMPLATE_DIR, template_name)
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                content = f.read()
                self.template_cache[template_name] = content
                return BytesIO(content)
        return None

    def format_date_ordinal(self, dt: datetime) -> str:
        day = dt.day
        suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return f"{day}{suffix} {dt.strftime('%B %Y')}"

    def format_date_professional(self, dt: datetime) -> str:
        """Professional date format for certificates: e.g. 2 February 2026."""
        if not hasattr(dt, "strftime"):
            return str(dt)
        return f"{dt.day} {dt.strftime('%B %Y')}"

    def generate(
        self,
        application,
        company_name: str,
        renewal_token: Optional[str] = None,
        is_expired: bool = False,
        certificate_open_password: Optional[str] = None,
    ) -> Tuple[BytesIO, str]:
        raw_type = application.certificate_type
        base_name = raw_type.value if hasattr(raw_type, 'value') else str(raw_type)
        if "CertificateType." in base_name:
             base_name = base_name.split(".")[-1].lower()
        
        if base_name in ["building", "civil"]:
            display_type = "General Building & Civil"
            template_filename = "building.pdf"
        else:
            display_type = base_name.title()
            template_filename = f"{base_name}.pdf"

        template_buffer = self.get_template_bytes(template_filename)
        if not template_buffer:
            buffer = BytesIO(); c = canvas.Canvas(buffer); c.drawString(100, 700, "Missing Template"); c.save(); buffer.seek(0)
            return buffer

        reader_orig = PdfReader(template_buffer) 
        page_orig = reader_orig.pages[0]
        width = float(page_orig.mediabox.width)
        height = float(page_orig.mediabox.height)

        # Mapping (Ref: A4 @ 300 DPI = 2480 x 3508)
        ref_w, ref_h = 2480.0, 3508.0
        def sx(x): return (x / ref_w) * width
        def sy(y): return height - (y / ref_h * height)
        def sp(h): return (h / ref_h) * height * (72/72) # Approx font scale

        overlay_buffer = BytesIO()
        c = canvas.Canvas(overlay_buffer, pagesize=(width, height))

        # Data
        company_address = application.company_info.address if application.company_info else ""
        
        # XSCNS: Use stored secure number if available, else legacy fallback
        if getattr(application, "certificate_number", None):
            cert_no = application.certificate_number
        else:
            cert_no = f"MWHWR-CC-25-{application.certificate_class or 'X'}-{application.id:03d}"
            
        # Use stored issued_date if available, else fallback to updated_at
        issued_at_date = application.issued_date or application.updated_at or datetime.now()
        issued_date = self.format_date_professional(issued_at_date)
        
        expiry_date = self.format_date_professional(application.expiry_date) if application.expiry_date else "N/A"
        
        financial_map = {
            "D1K1": "Over $500,000.00", "D2K2": "$200,000 - $500,000", "D3K3": "$75,000 - $200,000",
            "E1": "Over $200,000.00", "E2": "$75,000 - $200,000", "E3": "Up to $75,000.00",
            "G1": "Over $200,000.00", "G2": "Up to $50,000.00"
        }
        f_class = financial_map.get(application.certificate_class or "", "Up to $75,000.00")

        # Define text elements based on CSS specifications
        # Font sizes are derived from CSS pixel values (px / 2)
        # Coordinates are from CSS, with horizontal centering calculated for specific fields.
        text_elements = {
            'company_name': {
                'text': company_name.upper(),
                'x': 1423.5,  # Center calculated from left: 937px, width: 973px
                'y': 901,
                'size': 64, 
                'font': self.fonts['bold'],
                'align': 'center'
            },
            'location': {
                'text': company_address,
                'x': 1455.5,  # Center calculated from left: 861px, width: 1189px
                'y': 1025,
                'size': 64, 
                'font': self.fonts['regular'],
                'align': 'center'
            },
            'cert_no': {
                'text': f"Certificate No. {cert_no}",
                'x': 957,
                'y': 1281,
                'size': 44, 
                'font': self.fonts['regular'],
                'align': 'left'
            },
            'issued_date': {
                'text': f"Issued Date:  {issued_date}",
                'x': 1105,
                'y': 1371,
                'size': 44, 
                'font': self.fonts['regular'],
                'align': 'left'
            },
            'expiry_date': {
                'text': f"Expiry Date:  {expiry_date}",
                'x': 1105,
                'y': 1460,
                'size': 44, 
                'font': self.fonts['regular'],
                'align': 'left'
            },
            'category': {
                'text': f"Category {application.certificate_class or ''} – {display_type} Works, Financial Class- {f_class}",
                'x': 1516.5,  # Center calculated from left: 655px, width: 1723px
                'y': 1682,
                'size': 44, 
                'font': self.fonts['bold'],
                'align': 'center'
            }
        }

        center_x = width / 2

        if is_expired:
            # Expired certificate layout: SORRY / CERTIFICATE / HAS EXPIRED (blocky, prominent)
            c.setFont(self.fonts["bold"], 36)
            c.drawCentredString(center_x, sy(1550), "SORRY")
            c.drawCentredString(center_x, sy(1480), "CERTIFICATE")
            c.drawCentredString(center_x, sy(1410), "HAS EXPIRED")
            c.setFont(self.fonts["regular"], 9)
            c.drawCentredString(center_x, sy(1280), "CERTIFICATE HAS EXPIRED")
        else:
            # Normal certificate: draw all text elements
            for item in text_elements.values():
                c.setFont(item["font"], item["size"])
                if item["align"] == "center":
                    c.drawCentredString(sx(item["x"]), sy(item["y"]), item["text"])
                else:
                    c.drawString(sx(item["x"]), sy(item["y"]), item["text"])

        # QR Code (x: 2118, y: 3202)
        # Use security token for verification if available (XSCNS), else legacy ID
        if getattr(application, "security_token", None):
             verify_url = f"{settings.FRONTEND_URL}/verify/cert/{application.security_token}"
        else:
             verify_url = f"{settings.FRONTEND_URL}/verify?id={application.id}" 
             
        qr = qrcode.make(verify_url)
        qr_img = ImageReader(qr.get_image())
        qr_size = sx(300)
        c.drawImage(qr_img, sx(2118), sy(3202) - qr_size, width=qr_size, height=qr_size)

        # Renewal link under signatures: show "RENEW NOW" in blocky style; click opens renewal URL
        if renewal_token:
            renewal_url = f"{settings.FRONTEND_URL}/renewal?token={renewal_token}"
            c.setFont(self.fonts["bold"], 22)
            c.setFillColorRGB(0.35, 0.35, 0.35)  # grey to match stencil/expired text
            renew_text = "RENEW NOW"
            y_renew = sy(600)
            c.drawCentredString(center_x, y_renew, renew_text)
            # Make the "RENEW NOW" text a clickable link (same URL as before)
            text_w = c.stringWidth(renew_text, self.fonts["bold"], 22)
            half_w = text_w / 2
            c.linkURL(
                renewal_url,
                (center_x - half_w, y_renew - 22, center_x + half_w, y_renew + 4),
                relative=0,
            )
            c.setFillColorRGB(0, 0, 0)

        c.save(); overlay_buffer.seek(0)
        overlay_reader = PdfReader(overlay_buffer); overlay_page = overlay_reader.pages[0]
        page_orig.merge_page(overlay_page)

        # Create final PDF
        output_buffer = BytesIO()
        writer = PdfWriter()
        writer.add_page(page_orig)

        # PDF encryption: optional open password (user-provided at generation time, hashed in DB);
        # owner password from env restricts copy/edit in viewers that support it.
        user_pwd = certificate_open_password if certificate_open_password else ""
        owner_pwd = getattr(settings, "CERTIFICATE_OWNER_PASSWORD", None) or "mwhwr-cert-secure"
        try:
            no_copy_flag = 0xFFFFFFFC & ~32
            writer.encrypt(
                user_password=user_pwd,
                owner_password=owner_pwd,
                permissions_flag=no_copy_flag,
                algorithm="AES-256",
            )
        except Exception:
            try:
                writer.encrypt(user_password=user_pwd, owner_password=owner_pwd)
            except Exception:
                pass

        writer.write(output_buffer)
        output_buffer.seek(0)

        # Generate SHA-256 hash for tamper detection
        pdf_bytes = output_buffer.read()
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        output_buffer.seek(0)
        return output_buffer, pdf_hash

certificate_generator = CertificateGenerator()
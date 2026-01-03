import os
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from datetime import datetime
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path

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

    def generate(self, application, company_name: str):
        raw_type = application.certificate_type
        base_name = raw_type.value if hasattr(raw_type, 'value') else str(raw_type)
        if "CertificateType." in base_name:
             base_name = base_name.split(".")[-1].lower()
        
        # Consolidate labels as requested
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
        cert_no = f"MWHWR-CC-25-{application.certificate_class or 'X'}-{application.id:03d}"
        issued_date = self.format_date_ordinal(datetime.now())
        expiry_date = self.format_date_ordinal(application.expiry_date) if application.expiry_date else "N/A"
        
        financial_map = {
            "D1K1": "Over $500,000.00", "D2K2": "$200,000 - $500,000", "D3K3": "$75,000 - $200,000",
            "E1": "Over $200,000.00", "E2": "$75,000 - $200,000", "E3": "Up to $75,000.00",
            "G1": "Over $200,000.00", "G2": "Up to $50,000.00"
        }
        f_class = financial_map.get(application.certificate_class or "", "Up to $75,000.00")

        # Define text elements based on CSS specifications
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

        # Draw each text element on the canvas
        for item in text_elements.values():
            c.setFont(item['font'], item['size'])
            if item['align'] == 'center':
                c.drawCentredString(sx(item['x']), sy(item['y']), item['text'])
            else:
                c.drawString(sx(item['x']), sy(item['y']), item['text'])

        # 7) QR Code (x: 2118, y: 3202)
        verify_url = f"https://ministry-app.vercel.app/verify?id={application.id}" 
        qr = qrcode.make(verify_url)
        qr_img = ImageReader(qr.get_image())
        qr_size = sx(300)
        c.drawImage(qr_img, sx(2118), sy(3202) - qr_size, width=qr_size, height=qr_size)

        c.save(); overlay_buffer.seek(0)
        overlay_reader = PdfReader(overlay_buffer); overlay_page = overlay_reader.pages[0]
        page_orig.merge_page(overlay_page)

        output_buffer = BytesIO(); writer = PdfWriter(); writer.add_page(page_orig); writer.write(output_buffer); output_buffer.seek(0)
        return output_buffer

certificate_generator = CertificateGenerator()
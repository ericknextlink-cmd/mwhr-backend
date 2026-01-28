import os
import qrcode
import hashlib
from typing import Tuple
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

    def generate(self, application, company_name: str) -> Tuple[BytesIO, str]:
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
        issued_date = self.format_date_ordinal(issued_at_date)
        
        expiry_date = self.format_date_ordinal(application.expiry_date) if application.expiry_date else "N/A"
        
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

        # Draw each text element on the canvas as images (OCR-proof)
        # Render text to PIL Images to prevent OCR scanning
        try:
            from PIL import Image, ImageDraw, ImageFont
            import textwrap
            
            for item in text_elements.values():
                # Calculate text dimensions
                font_size = int(item['size'] * 0.75)  # Convert points to pixels (approx)
                text = item['text']
                
                # Create image with transparent background
                # Estimate size: width based on text length, height based on font size
                img_width = int(font_size * len(text) * 0.6)
                img_height = int(font_size * 1.5)
                img = Image.new('RGBA', (img_width, img_height), (255, 255, 255, 0))
                draw = ImageDraw.Draw(img)
                
                # Try to load font, fallback to default
                try:
                    # Use default font (system font)
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                except:
                    try:
                        font = ImageFont.load_default()
                    except:
                        font = None
                
                # Draw text on image
                text_bbox = draw.textbbox((0, 0), text, font=font) if font else (0, 0, img_width, img_height)
                text_x = (img_width - (text_bbox[2] - text_bbox[0])) / 2 if item['align'] == 'center' else 0
                text_y = (img_height - (text_bbox[3] - text_bbox[1])) / 2
                
                draw.text((text_x, text_y), text, fill=(0, 0, 0, 255), font=font)
                
                # Convert to bytes and create ImageReader
                img_bytes = BytesIO()
                img.save(img_bytes, format='PNG', dpi=(300, 300))
                img_bytes.seek(0)
                img_reader = ImageReader(img_bytes)
                
                # Draw image on canvas
                img_width_pts = sx(img_width * 0.75)  # Convert pixels to points
                img_height_pts = sy(img_height * 0.75) - sy(0)
                
                if item['align'] == 'center':
                    c.drawImage(img_reader, sx(item['x']) - img_width_pts/2, sy(item['y']) - img_height_pts, width=img_width_pts, height=img_height_pts)
                else:
                    c.drawImage(img_reader, sx(item['x']), sy(item['y']) - img_height_pts, width=img_width_pts, height=img_height_pts)
        except Exception as e:
            # Fallback to text rendering if image conversion fails
            print(f"Warning: OCR-proof rendering failed, using text fallback: {e}")
            for item in text_elements.values():
                c.setFont(item['font'], item['size'])
                if item['align'] == 'center':
                    c.drawCentredString(sx(item['x']), sy(item['y']), item['text'])
                else:
                    c.drawString(sx(item['x']), sy(item['y']), item['text'])

        # 7) QR Code (x: 2118, y: 3202)
        # Use security token for verification if available (XSCNS), else legacy ID
        if getattr(application, "security_token", None):
             verify_url = f"{settings.FRONTEND_URL}/verify/cert/{application.security_token}"
        else:
             verify_url = f"{settings.FRONTEND_URL}/verify?id={application.id}" 
             
        qr = qrcode.make(verify_url)
        qr_img = ImageReader(qr.get_image())
        qr_size = sx(300)
        c.drawImage(qr_img, sx(2118), sy(3202) - qr_size, width=qr_size, height=qr_size)

        c.save(); overlay_buffer.seek(0)
        overlay_reader = PdfReader(overlay_buffer); overlay_page = overlay_reader.pages[0]
        page_orig.merge_page(overlay_page)

        # Create final PDF
        output_buffer = BytesIO()
        writer = PdfWriter()
        writer.add_page(page_orig)
        writer.write(output_buffer)
        output_buffer.seek(0)
        
        # Generate SHA-256 hash for tamper detection
        # Any modification to the PDF (even if reverted) will change this hash
        pdf_bytes = output_buffer.read()
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        
        # Reset buffer for return
        output_buffer.seek(0)
        
        # Return both PDF and hash
        # Hash is stored in database - any mismatch indicates tampering
        return output_buffer, pdf_hash

certificate_generator = CertificateGenerator()
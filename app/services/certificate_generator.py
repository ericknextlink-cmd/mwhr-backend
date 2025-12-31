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
BASE_DIR = Path(__file__).resolve().parent.parent.parent # Go up to 'backend'
TEMPLATE_DIR = str(BASE_DIR / "certificate_templates")
FONT_DIR = str(BASE_DIR / "fonts")

class CertificateGenerator:
    def __init__(self):
        # Cache for template bytes: { "electrical.pdf": b'...', ... }
        self.template_cache = {}
        
        # Default fallback fonts
        self.fonts = {
            'regular': 'Times-Roman',
            'bold': 'Times-Bold',
            'italic': 'Times-Italic',
            'bold_italic': 'Times-BoldItalic'
        }
        
        # Try to register Century Gothic fonts
        try:
            # Check if files exist first to avoid partial registration or errors
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
                
            print(f"Fonts configured: {self.fonts}")
        except Exception as e:
            print(f"Warning: Could not register Century Gothic fonts. Using defaults. Error: {e}")

    def get_template_bytes(self, template_name: str) -> BytesIO | None:
        """
        Fetches template from Cache -> Supabase -> Local Disk.
        Returns a BytesIO object or None.
        """
        # 1. Check Cache
        if template_name in self.template_cache:
            return BytesIO(self.template_cache[template_name])

        # 2. Check Supabase
        print(f"Fetching template '{template_name}' from Supabase...")
        file_bytes = storage_service.download_file(f"templates/{template_name}")
        
        if file_bytes:
            self.template_cache[template_name] = file_bytes
            print("Template fetched from Supabase and cached.")
            return BytesIO(file_bytes)
        
        # 3. Fallback to Local Disk
        local_path = os.path.join(TEMPLATE_DIR, template_name)
        print(f"Supabase fetch failed. Falling back to local: {local_path}")
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                content = f.read()
                self.template_cache[template_name] = content # Cache local file too
                return BytesIO(content)
        
        return None

    def generate(self, application, company_name: str):
        """
        Generates a certificate PDF by overlaying text onto a PDF template.
        """
        # 1. Resolve Template Name
        raw_type = application.certificate_type
        if hasattr(raw_type, 'value'):
            base_name = raw_type.value
        else:
            base_name = str(raw_type)
            
        if "CertificateType." in base_name:
             base_name = base_name.split(".")[-1].lower()
        
        template_filename = f"{base_name}.pdf"
        
        # 2. Get Template Bytes
        template_buffer = self.get_template_bytes(template_filename)

        if not template_buffer:
            print(f"Error: Template {template_filename} not found in Storage or Local.")
            buffer = BytesIO()
            c = canvas.Canvas(buffer)
            c.drawString(50, 700, f"Error: Certificate Template Not Found")
            c.drawString(50, 680, f"Type: {base_name}")
            c.save()
            buffer.seek(0)
            return buffer

        # 3. Read Template PDF to get dimensions
        reader_orig = PdfReader(template_buffer) 
        page_orig = reader_orig.pages[0]
        width = float(page_orig.mediabox.width)
        height = float(page_orig.mediabox.height)

        # 4. Create Overlay PDF (Text + QR)
        overlay_buffer = BytesIO()
        c = canvas.Canvas(overlay_buffer, pagesize=(width, height))

        # --- Draw Text (Adjust coordinates as needed) ---
        # Note: PDF coordinates start Bottom-Left (0,0)
        
        # Company Name (Center, Big)
        c.setFont(self.fonts['bold'], 32)
        c.drawCentredString(width / 2, height * 0.65, company_name.upper())

        # Classification Text
        c.setFont(self.fonts['regular'], 18)
        text = f"Has been classified as a {application.certificate_class or 'Registered'} Contractor"
        c.drawCentredString(width / 2, height * 0.58, text)
        
        # Category
        c.setFont(self.fonts['bold_italic'], 22)
        category_text = f"in {application.certificate_type.replace('_', ' ').title()} Works"
        c.drawCentredString(width / 2, height * 0.51, category_text)

        # Date
        c.setFont(self.fonts['regular'], 16)
        date_str = datetime.now().strftime("%d day of %B, %Y")
        c.drawCentredString(width / 2, height * 0.44, f"Given this {date_str}")

        # --- Draw QR Code ---
        verify_url = f"https://mwhr-domain.com/verify?id={application.id}" 
        qr = qrcode.make(verify_url)
        qr_img = ImageReader(qr.get_image())
        
        # Place QR Code (Bottom Center)
        qr_size = 100
        c.drawImage(qr_img, (width / 2) - (qr_size / 2), height * 0.11, width=qr_size, height=qr_size)

        c.save()
        overlay_buffer.seek(0)

        # 5. Merge Overlay with Template
        # We need to reset template_buffer cursor because PdfReader might have moved it? 
        # Actually PdfReader already read it. We need a fresh reader for merge or reuse the page.
        # Safest to just use the page object we already have: page_orig
        
        overlay_reader = PdfReader(overlay_buffer)
        overlay_page = overlay_reader.pages[0]

        # Merge: Put overlay ON TOP of template
        page_orig.merge_page(overlay_page)

        # 6. Write Output
        output_buffer = BytesIO()
        writer = PdfWriter()
        writer.add_page(page_orig)
        writer.write(output_buffer)
        output_buffer.seek(0)

        return output_buffer

certificate_generator = CertificateGenerator()
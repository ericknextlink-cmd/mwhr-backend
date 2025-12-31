import asyncio
import os
from app.services.certificate_generator import certificate_generator
from app.models.application import Application, CertificateType
from app.models.company_info import CompanyInfo

# Mock objects
class MockApp:
    id = 123
    certificate_type = CertificateType.BUILDING
    certificate_class = "A"
    
class MockCompany:
    company_name = "Test Construction Ltd"

async def test_generation():
    print("Testing PDF Generation...")
    app = MockApp()
    company_name = "Test Construction Ltd"
    
    try:
        pdf_buffer = certificate_generator.generate(app, company_name)
        
        output_path = "test_certificate.pdf"
        with open(output_path, "wb") as f:
            f.write(pdf_buffer.getvalue())
            
        print(f"Success! PDF generated at {output_path}")
        print(f"Size: {os.path.getsize(output_path)} bytes")
        
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_generation())

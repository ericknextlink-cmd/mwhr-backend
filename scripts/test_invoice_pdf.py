#!/usr/bin/env python3
"""
Standalone script to generate a test invoice PDF with mock data.
No server, no DB, no email.

Run from mwhr-backend directory (use the project venv so dependencies are available):

    .venv/bin/python scripts/test_invoice_pdf.py

  or, with venv activated:

    python scripts/test_invoice_pdf.py

Output: test_invoice_output.pdf in mwhr-backend/
Tweak make_mock_application / make_mock_company below, or the generator layout
in app/services/invoice_pdf_generator.py, then re-run to iterate on the design.
"""
from pathlib import Path
import sys

# Add backend root so "app" is importable
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

# Optional: load .env for any config the generator might use (e.g. fees)
_env = _backend_root / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

from app.models.application import Application, CertificateType
from app.models.company_info import CompanyInfo
from app.services.invoice_pdf_generator import invoice_pdf_generator


def make_mock_application(
    app_id: int = 214,
    certificate_type: str = "electrical",
    certificate_class: str = "E1",
    certificate_number: str | None = "MWHWR-CC-2026-000214",
) -> Application:
    cert_type = getattr(CertificateType, certificate_type.upper(), CertificateType.ELECTRICAL)
    return Application(
        id=app_id,
        certificate_type=cert_type,
        certificate_class=certificate_class,
        certificate_number=certificate_number,
    )


def make_mock_company(
    application_id: int = 214,
    company_name: str = "Quantum Engineering Ltd.",
    registration_number: str = "CS123456",
    address: str = "Accra, Ghana",
    city: str = "Accra",
    country: str = "Ghana",
    phone_number: str = "+233 54 233 8787",
    email: str = "info@mensaheng.com",
) -> CompanyInfo:
    return CompanyInfo(
        application_id=application_id,
        company_name=company_name,
        registration_number=registration_number,
        address=address,
        city=city,
        country=country,
        phone_number=phone_number,
        email=email,
    )


def main() -> None:
    out_name = "test_invoice_output.pdf"
    out_path = _backend_root / out_name

    app = make_mock_application()
    company = make_mock_company(application_id=app.id or 214)

    print("Generating invoice PDF with mock data...")
    print(f"  Company: {company.company_name}")
    print(f"  Application id: {app.id}, type: {app.certificate_type}")

    pdf_buffer, invoice_number = invoice_pdf_generator.generate(app, company)

    out_path.write_bytes(pdf_buffer.getvalue())
    print(f"  Invoice number: {invoice_number}")
    print(f"  Written to: {out_path.resolve()}")
    print("  Open the PDF to check layout; re-run this script after changing the generator or template.")


if __name__ == "__main__":
    main()

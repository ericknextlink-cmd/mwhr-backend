#!/usr/bin/env python3
"""
Standalone script to generate a test certificate PDF with mock data.
No server, no DB. Uses local certificate_templates/ (or Supabase if configured).

Run from mwhr-backend directory (use the project venv so dependencies are available):

    .venv/bin/python scripts/test_certificate_pdf.py

  or, with venv activated:

    python scripts/test_certificate_pdf.py

Output: test_certificate_output.pdf in mwhr-backend/

For a full layout test, ensure a template exists for the certificate type, e.g.:
  - certificate_templates/electrical.pdf (or building.pdf, plumbing.pdf, civil.pdf)
  - or upload the same file to Supabase Storage under templates/ (e.g. templates/electrical.pdf)

Tweak make_mock_application / make_mock_company below, or run with --expired / --renewal to test variants.

sample command:
python scripts/test_certificate_pdf.py
python scripts/test_certificate_pdf.py --type building -o building_cert.pdf
python scripts/test_certificate_pdf.py --expired
python scripts/test_certificate_pdf.py --renewal --password "open-me"
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import sys

# Add backend root so "app" is importable
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

# Optional: load .env for config (e.g. FRONTEND_URL, CERTIFICATE_OWNER_PASSWORD)
_env = _backend_root / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

from app.models.application import Application, CertificateType
from app.models.company_info import CompanyInfo
from app.services.certificate_generator import certificate_generator


def make_mock_company(
    application_id: int = 1,
    company_name: str = "Quantum Engineering Ltd.",
    address: str = "Accra, Ghana",
    registration_number: str = "CS123456",
    city: str = "Accra",
    country: str = "Ghana",
    phone_number: str = "+233 54 233 8787",
    email: str = "info@example.com",
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


def make_mock_application(
    app_id: int = 1,
    certificate_type: str = "electrical",
    certificate_class: str = "E1",
    certificate_number: str | None = "MWHWR-CC-2026-000001",
    security_token: str | None = "test-token-abc123",
    issued_date: datetime | None = None,
    expiry_date: datetime | None = None,
) -> Application:
    cert_type = getattr(CertificateType, certificate_type.upper(), CertificateType.ELECTRICAL)
    now = datetime.now(timezone.utc)
    issued = issued_date or now
    expiry = expiry_date or (now + timedelta(days=365))
    app = Application(
        id=app_id,
        certificate_type=cert_type,
        certificate_class=certificate_class,
        certificate_number=certificate_number,
        security_token=security_token,
        issued_date=issued,
        updated_at=now,
        expiry_date=expiry,
    )
    company = make_mock_company(application_id=app_id)
    app.company_info = company
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a test certificate PDF")
    parser.add_argument(
        "--type",
        default="electrical",
        choices=["electrical", "building", "plumbing", "civil"],
        help="Certificate type (template must exist: <type>.pdf)",
    )
    parser.add_argument(
        "--expired",
        action="store_true",
        help="Render certificate as expired (SORRY CERTIFICATE HAS EXPIRED)",
    )
    parser.add_argument(
        "--renewal",
        action="store_true",
        help="Include renewal token and RENEW NOW link",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Optional owner password (edit protection only; PDF is viewable without password)",
    )
    parser.add_argument(
        "-o", "--output",
        default="test_certificate_output.pdf",
        help="Output filename (default: test_certificate_output.pdf)",
    )
    args = parser.parse_args()

    app = make_mock_application(certificate_type=args.type)
    company_name = app.company_info.company_name if app.company_info else "Applicant"
    renewal_token = "test-renewal-token" if args.renewal else None

    print("Generating certificate PDF with mock data...")
    print(f"  Company: {company_name}")
    print(f"  Application id: {app.id}, type: {app.certificate_type}, class: {app.certificate_class}")
    print(f"  Expired: {args.expired}, Renewal link: {args.renewal}")

    pdf_buffer, pdf_hash = certificate_generator.generate(
        app,
        company_name,
        renewal_token=renewal_token,
        is_expired=args.expired,
        certificate_owner_password=args.password,
    )

    out_path = _backend_root / args.output
    out_path.write_bytes(pdf_buffer.getvalue())
    print(f"  PDF hash: {pdf_hash[:16]}...")
    print(f"  Written to: {out_path.resolve()}")
    print("  Open the PDF to check layout (edit-protected if --password was set).")


if __name__ == "__main__":
    main()

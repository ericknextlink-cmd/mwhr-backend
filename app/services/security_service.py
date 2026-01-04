import hmac
import hashlib
import secrets
import uuid
from datetime import datetime
from app.core.config import settings

class SecurityService:
    # Crockford's Base32 Alphabet (canonical)
    # Excludes I, L, O, U to avoid confusion
    ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

    @staticmethod
    def _encode_base32_crockford(data_bytes: bytes) -> str:
        """Encodes bytes to Crockford Base32 string."""
        # Convert bytes to a large integer
        num = int.from_bytes(data_bytes, 'big')
        
        result = []
        while num > 0:
            num, rem = divmod(num, 32)
            result.append(SecurityService.ALPHABET[rem])
        
        # Reverse because we appended least significant digits first
        return "".join(reversed(result))

    @staticmethod
    def generate_token(internal_uid: uuid.UUID) -> str:
        """
        Generates a 15-char Custom Base32 token using HMAC-SHA256.
        Format: XXXXX-XXXXX-XXXXX
        """
        timestamp = str(datetime.utcnow().timestamp())
        random_entropy = secrets.token_bytes(32)
        
        # Inputs: UUID + Timestamp + Random
        data = f"{internal_uid}{timestamp}".encode() + random_entropy
        
        # HMAC
        secret = settings.SECRET_KEY.encode()
        # Use SHA256 -> 32 bytes
        h = hmac.new(secret, data, hashlib.sha256).digest()
        
        # Encode
        token_str = SecurityService._encode_base32_crockford(h)
        
        # Pad if necessary (unlikely with 32 bytes, which is huge number)
        # We need 15 chars for 3 blocks of 5
        # 32 bytes is plenty for 15 base32 chars (15 * 5 = 75 bits needed)
        
        # Take the last 15 characters (more randomness propagation) or first. 
        # Let's take from middle to ensure mixing.
        if len(token_str) < 15:
            # Should not happen with sha256 (256 bits -> ~51 chars)
            token_str = token_str.rjust(15, '0')
            
        final_token = token_str[:15]
        
        # Format: XXXXX-XXXXX-XXXXX
        return f"{final_token[:5]}-{final_token[5:10]}-{final_token[10:15]}"

    @staticmethod
    def generate_certificate_number(cert_class: str, internal_uid: uuid.UUID) -> dict:
        """
        Generates the full XSCNS certificate number.
        Returns dict with parts for flexibility.
        """
        year_suffix = datetime.utcnow().strftime("%y") # 25
        token = SecurityService.generate_token(internal_uid)
        
        # Class handling
        cls = cert_class if cert_class else "XX"
        
        # Format: MWHWR-{Class}-{Year}-{Token}
        full_number = f"MWHWR-{cls}-{year_suffix}-{token}"
        
        return {
            "full_number": full_number,
            "token": token,
            "year": year_suffix,
            "class": cls
        }

security_service = SecurityService()

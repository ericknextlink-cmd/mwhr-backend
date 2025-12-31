from datetime import datetime, timedelta
import secrets
import random

class OTPStore:
    def __init__(self):
        # Format: {phone_number: {"otp": str, "expires_at": datetime}}
        self._otps = {}
        # Format: {token: {"phone_number": str, "expires_at": datetime}}
        self._verified_tokens = {}

    def generate_otp(self, phone_number: str) -> str:
        # Generate 6-digit OTP
        otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
        self._otps[phone_number] = {
            "otp": otp,
            "expires_at": datetime.utcnow() + timedelta(minutes=5)
        }
        return otp

    def verify_otp(self, phone_number: str, otp: str) -> str | None:
        data = self._otps.get(phone_number)
        
        if not data:
            return None
            
        if datetime.utcnow() > data["expires_at"]:
            del self._otps[phone_number]
            return None
            
        if data["otp"] != otp:
            return None

        # Success: Generate a verification token
        del self._otps[phone_number] # Consume OTP
        token = secrets.token_urlsafe(32)
        self._verified_tokens[token] = {
            "phone_number": phone_number,
            "expires_at": datetime.utcnow() + timedelta(minutes=15) # Token valid for 15 mins
        }
        return token

    def is_token_valid(self, token: str) -> bool:
        data = self._verified_tokens.get(token)
        if not data:
            return False
            
        if datetime.utcnow() > data["expires_at"]:
            del self._verified_tokens[token]
            return False
            
        return True

# Global instance
otp_store = OTPStore()

"""
Generate Data Matrix 2D barcode as PNG image bytes.
Uses pylibdmtx when available; falls back to standard QR code so layout/size stay the same.
"""
from io import BytesIO

# Data Matrix via pylibdmtx (on Linux you may need: apt-get install libdmtx0)
_DMTX_AVAILABLE = False
try:
    from pylibdmtx.pylibdmtx import encode as dmtx_encode
    from PIL import Image
    _DMTX_AVAILABLE = True
except ImportError:
    pass

# Fallback: standard QR
try:
    import qrcode
    _QR_AVAILABLE = True
except ImportError:
    _QR_AVAILABLE = False


def make_datamatrix_image(data: str) -> BytesIO:
    """
    Return a BytesIO containing PNG image of a Data Matrix (or QR fallback) for the given string.
    Same usage as before: pass to ImageReader and draw at existing positions/sizes.
    """
    if not data:
        data = " "
    payload = data.encode("utf-8") if isinstance(data, str) else data

    if _DMTX_AVAILABLE:
        try:
            encoded = dmtx_encode(payload)
            if encoded and getattr(encoded, "pixels", None) is not None:
                img = Image.frombytes("RGB", (encoded.width, encoded.height), encoded.pixels)
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                return buf
        except Exception:
            pass

    if _QR_AVAILABLE:
        qr = qrcode.make(data)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)
        return buf

    raise RuntimeError("Neither pylibdmtx nor qrcode available for barcode generation.")

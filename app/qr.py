"""Generates a QR code PNG for an asset's check-in URL, on the fly (nothing
is cached to disk, so if you change the base URL setting, every QR code
updates automatically the next time it's viewed or printed)."""
import io

import qrcode
from qrcode.image.pil import PilImage


def checkin_url(base_url: str, code: str) -> str:
    return f"{base_url.rstrip('/')}/c/{code}"


def make_qr_png(url: str) -> bytes:
    qr = qrcode.QRCode(border=2, box_size=10,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

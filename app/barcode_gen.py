"""
Generates a Code128 barcode PNG encoding an asset's internal `code` (the
same short identifier baked into its QR link) — not the user-editable
Asset Code, since that field is optional and not guaranteed unique.
Code128 handles any letters/numbers, which is all `Asset.code` ever is.
"""
import io

import barcode
from barcode.writer import ImageWriter

CODE128 = barcode.get_barcode_class("code128")


def make_barcode_png(data: str, write_text: bool = True) -> bytes:
    code = CODE128(data, writer=ImageWriter())
    buf = io.BytesIO()
    code.write(buf, options={
        "module_height": 13.0, "module_width": 0.5,
        "font_size": 9, "text_distance": 4, "quiet_zone": 3,
        # The printed label shows the asset code as text already, so it asks
        # for write_text=False to avoid printing the same string twice.
        "write_text": write_text,
    })
    buf.seek(0)
    return buf.read()

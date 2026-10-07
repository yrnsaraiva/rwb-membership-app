import re
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.utils.safestring import mark_safe


def qr_svg(data: str) -> str:
    """Devolve o QR code como SVG inline (leve, nítido em qualquer ecrã)."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    img.save(buffer)
    svg = buffer.getvalue().decode("utf-8")
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg).strip()
    # Remove dimensões fixas para o SVG escalar com o contentor
    svg = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
    return mark_safe(svg)


def member_qr_svg(user) -> str:
    return qr_svg(f"{settings.SITE_URL}{user.get_verify_url()}")

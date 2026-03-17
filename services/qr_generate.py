from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import qrcode
from PIL import Image

if TYPE_CHECKING:
    from PySide6.QtGui import QPixmap


def generate_qr_image(data: str, box_size: int = 10, border: int = 4) -> Image.Image:
    if not data.strip():
        raise ValueError("Please enter text or a URL to generate a QR code.")

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def save_qr_image(image: Image.Image, target_path: str | Path) -> Path:
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    from PIL.ImageQt import ImageQt
    from PySide6.QtGui import QPixmap

    qt_image = ImageQt(image)
    return QPixmap.fromImage(qt_image)


def pil_to_png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

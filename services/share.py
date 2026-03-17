from __future__ import annotations

import os
import subprocess
import tempfile
from enum import Enum
from pathlib import Path

from PIL import Image

from services.qr_generate import save_qr_image


class ShareMode(str, Enum):
    OPEN_WITH = "open_with"
    EMAIL = "email"
    FOLDER = "folder"


def export_share_image(image: Image.Image) -> Path:
    share_dir = Path(tempfile.gettempdir()) / "qr_scanner_share"
    share_dir.mkdir(parents=True, exist_ok=True)
    target = share_dir / "shared_qr.png"
    return save_qr_image(image, target)


def open_share_flow(file_path: str | Path, mode: ShareMode = ShareMode.OPEN_WITH) -> None:
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Share file not found: {path}")

    if os.name == "nt":
        if mode == ShareMode.OPEN_WITH:
            subprocess.run(
                ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", str(path)],
                check=False,
            )
            return
        if mode == ShareMode.EMAIL:
            email_script = (
                "$p = [System.IO.Path]::GetFullPath('" + str(path).replace("'", "''") + "');"
                "try {"
                "$outlook = New-Object -ComObject Outlook.Application;"
                "$mail = $outlook.CreateItem(0);"
                "$mail.Subject = 'Shared QR Code';"
                "$mail.Body = 'Please find the generated QR image attached.';"
                "$mail.Attachments.Add($p) | Out-Null;"
                "$mail.Display();"
                "exit 0;"
                "} catch {"
                "exit 1;"
                "}"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", email_script],
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "Could not create email with attachment. Please make sure Outlook is installed."
                )
            return
        subprocess.run(["explorer", f"/select,{path}"], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)

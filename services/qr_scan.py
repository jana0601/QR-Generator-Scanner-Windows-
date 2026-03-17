from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

try:
    from pyzbar.pyzbar import decode as decode_barcodes
except Exception:  # pragma: no cover - fallback path
    decode_barcodes = None


@dataclass(slots=True)
class ScanResult:
    content: str
    code_type: str
    source: str
    timestamp: datetime


class QRScannerService:
    def __init__(self) -> None:
        self._camera: cv2.VideoCapture | None = None
        self._qr_detector = cv2.QRCodeDetector()

    def open_camera(self, index: int = 0) -> bool:
        self.release_camera()
        camera = cv2.VideoCapture(index)
        if not camera.isOpened():
            return False
        self._camera = camera
        return True

    def release_camera(self) -> None:
        if self._camera is not None:
            self._camera.release()
            self._camera = None

    def read_frame(self) -> tuple[np.ndarray | None, list[ScanResult]]:
        if self._camera is None:
            return None, []

        ok, frame = self._camera.read()
        if not ok or frame is None:
            return None, []

        return frame, self.decode_frame(frame, source="camera")

    def decode_image_file(self, file_path: str | Path) -> list[ScanResult]:
        path = Path(file_path)
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError("Could not read image file.")
        return self.decode_frame(frame, source=str(path))

    def decode_frame(self, frame: np.ndarray, source: str) -> list[ScanResult]:
        now = datetime.now()
        pyzbar_results = self._decode_with_pyzbar(frame, source, now)
        if pyzbar_results:
            return pyzbar_results
        return self._decode_with_opencv(frame, source, now)

    def _decode_with_pyzbar(
        self, frame: np.ndarray, source: str, now: datetime
    ) -> list[ScanResult]:
        if decode_barcodes is None:
            return []
        decoded_items = decode_barcodes(frame)
        results: list[ScanResult] = []
        for item in decoded_items:
            raw_data = item.data.decode("utf-8", errors="replace")
            if raw_data:
                results.append(
                    ScanResult(
                        content=raw_data,
                        code_type=item.type or "QR",
                        source=source,
                        timestamp=now,
                    )
                )
        return results

    def _decode_with_opencv(
        self, frame: np.ndarray, source: str, now: datetime
    ) -> list[ScanResult]:
        text, _, _ = self._qr_detector.detectAndDecode(frame)
        if text:
            return [
                ScanResult(
                    content=text,
                    code_type="QR",
                    source=source,
                    timestamp=now,
                )
            ]
        return []

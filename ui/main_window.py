from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import pyperclip
from PIL import Image
from PySide6.QtCore import QMimeData, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.qr_generate import generate_qr_image, pil_to_qpixmap, save_qr_image
from services.qr_scan import QRScannerService, ScanResult
from services.share import ShareMode, export_share_image, open_share_flow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("QR Generator + Scanner")
        self.resize(980, 720)

        self.settings = QSettings("HistoryProjects", "QRScanner")
        self.scanner = QRScannerService()
        self.camera_timer = QTimer(self)
        self.camera_timer.setInterval(35)
        self.camera_timer.timeout.connect(self._on_camera_tick)
        self.min_font_size = 9
        self.max_font_size = 22
        saved_font_size = self.settings.value("font_size", 10)
        try:
            self.font_size = int(saved_font_size)
        except (TypeError, ValueError):
            self.font_size = 10
        self.font_size = max(self.min_font_size, min(self.font_size, self.max_font_size))

        self.current_qr_image: Image.Image | None = None
        self.current_generated_text = ""
        self.last_scan_value = ""
        self.last_scan_seen_at: datetime | None = None

        self._build_ui()
        self._apply_font_size(show_status=False)
        self.statusBar().showMessage("Ready")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.camera_timer.stop()
        self.scanner.release_camera()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        self._build_view_menu()
        tabs = QTabWidget(self)
        self.setCentralWidget(tabs)

        generate_tab = QWidget()
        generate_layout = QVBoxLayout(generate_tab)

        form_layout = QFormLayout()
        self.input_text = QPlainTextEdit()
        self.input_text.setPlaceholderText("Enter text or URL...")
        self.input_text.setFixedHeight(130)
        form_layout.addRow("Text / URL", self.input_text)
        generate_layout.addLayout(form_layout)

        button_row = QHBoxLayout()
        self.generate_button = QPushButton("Generate")
        self.save_button = QPushButton("Save PNG")
        self.copy_button = QPushButton("Copy")
        self.share_button = QPushButton("Share")
        for button in (
            self.generate_button,
            self.save_button,
            self.copy_button,
            self.share_button,
        ):
            button_row.addWidget(button)
        generate_layout.addLayout(button_row)

        self.qr_preview = QLabel("QR preview appears here")
        self.qr_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_preview.setMinimumHeight(380)
        self.qr_preview.setStyleSheet("border: 1px solid #888;")
        generate_layout.addWidget(self.qr_preview)

        tabs.addTab(generate_tab, "Generate")

        scan_tab = QWidget()
        scan_layout = QVBoxLayout(scan_tab)

        camera_row = QHBoxLayout()
        self.camera_index_input = QLineEdit("0")
        self.camera_index_input.setFixedWidth(60)
        self.start_camera_button = QPushButton("Start Camera")
        self.stop_camera_button = QPushButton("Stop Camera")
        self.scan_image_button = QPushButton("Scan from Image")
        camera_row.addWidget(QLabel("Camera index"))
        camera_row.addWidget(self.camera_index_input)
        camera_row.addWidget(self.start_camera_button)
        camera_row.addWidget(self.stop_camera_button)
        camera_row.addWidget(self.scan_image_button)
        camera_row.addStretch()
        scan_layout.addLayout(camera_row)

        self.camera_preview = QLabel("Camera preview appears here")
        self.camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview.setMinimumHeight(310)
        self.camera_preview.setStyleSheet("border: 1px solid #888;")
        scan_layout.addWidget(self.camera_preview)

        self.scan_result = QPlainTextEdit()
        self.scan_result.setReadOnly(True)
        self.scan_result.setPlaceholderText("Decoded QR result appears here.")
        self.scan_result.setFixedHeight(120)
        scan_layout.addWidget(self.scan_result)

        result_actions = QHBoxLayout()
        self.copy_scan_button = QPushButton("Copy Result")
        self.open_url_button = QPushButton("Open as URL")
        self.clear_history_button = QPushButton("Clear History")
        result_actions.addWidget(self.copy_scan_button)
        result_actions.addWidget(self.open_url_button)
        result_actions.addWidget(self.clear_history_button)
        result_actions.addStretch()
        scan_layout.addLayout(result_actions)

        self.scan_history = QListWidget()
        scan_layout.addWidget(QLabel("Scan History"))
        scan_layout.addWidget(self.scan_history)

        tabs.addTab(scan_tab, "Scan")

        self.generate_button.clicked.connect(self.on_generate_clicked)
        self.save_button.clicked.connect(self.on_save_clicked)
        self.copy_button.clicked.connect(self.on_copy_generated_clicked)
        self.share_button.clicked.connect(self.on_share_clicked)

        self.start_camera_button.clicked.connect(self.on_start_camera_clicked)
        self.stop_camera_button.clicked.connect(self.on_stop_camera_clicked)
        self.scan_image_button.clicked.connect(self.on_scan_image_clicked)
        self.copy_scan_button.clicked.connect(self.on_copy_scan_clicked)
        self.open_url_button.clicked.connect(self.on_open_url_clicked)
        self.clear_history_button.clicked.connect(self.on_clear_history_clicked)
        self.scan_history.itemClicked.connect(self.on_history_item_clicked)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.on_generate_clicked)

        self._set_generate_actions_enabled(False)
        self._set_scan_actions_enabled(False)

    def _build_view_menu(self) -> None:
        view_menu = self.menuBar().addMenu("View")

        increase_font_action = QAction("Increase Font Size", self)
        increase_font_action.setShortcut(QKeySequence("Ctrl+="))
        increase_font_action.triggered.connect(self.on_increase_font_size_clicked)
        view_menu.addAction(increase_font_action)

        decrease_font_action = QAction("Decrease Font Size", self)
        decrease_font_action.setShortcut(QKeySequence("Ctrl+-"))
        decrease_font_action.triggered.connect(self.on_decrease_font_size_clicked)
        view_menu.addAction(decrease_font_action)

        reset_font_action = QAction("Reset Font Size", self)
        reset_font_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_font_action.triggered.connect(self.on_reset_font_size_clicked)
        view_menu.addAction(reset_font_action)

    def _set_generate_actions_enabled(self, enabled: bool) -> None:
        self.save_button.setEnabled(enabled)
        self.copy_button.setEnabled(enabled)
        self.share_button.setEnabled(enabled)

    def _set_scan_actions_enabled(self, enabled: bool) -> None:
        self.copy_scan_button.setEnabled(enabled)
        self.open_url_button.setEnabled(enabled)

    def on_generate_clicked(self) -> None:
        text = self.input_text.toPlainText().strip()
        try:
            image = generate_qr_image(text)
        except ValueError as error:
            self._show_error(str(error))
            return
        except Exception as error:
            self._show_error(f"QR generation failed: {error}")
            return

        self.current_qr_image = image
        self.current_generated_text = text
        self.qr_preview.setPixmap(
            pil_to_qpixmap(image).scaled(
                self.qr_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._set_generate_actions_enabled(True)
        self.statusBar().showMessage("QR generated.")

    def on_save_clicked(self) -> None:
        if self.current_qr_image is None:
            return

        initial_dir = self.settings.value("last_save_dir", str(Path.home()))
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save QR as PNG",
            str(Path(initial_dir) / "qr_code.png"),
            "PNG Image (*.png)",
        )
        if not file_path:
            return
        try:
            saved_path = save_qr_image(self.current_qr_image, file_path)
        except Exception as error:
            self._show_error(f"Save failed: {error}")
            return

        self.settings.setValue("last_save_dir", str(saved_path.parent))
        self.statusBar().showMessage(f"Saved: {saved_path}")

    def on_copy_generated_clicked(self) -> None:
        if self.current_qr_image is None:
            return

        clipboard = QApplication.clipboard()
        mime_data = QMimeData()
        pixmap = pil_to_qpixmap(self.current_qr_image)
        mime_data.setImageData(pixmap.toImage())
        clipboard.setMimeData(mime_data)
        self.statusBar().showMessage("Copied QR image to clipboard.")

    def on_share_clicked(self) -> None:
        if self.current_qr_image is None:
            return

        try:
            share_path = export_share_image(self.current_qr_image)
            mode = self._ask_share_mode()
            if mode is None:
                return
            open_share_flow(share_path, mode)
        except Exception as error:
            self._show_error(f"Share failed: {error}")
            return

        self.statusBar().showMessage(f"Shared QR image ready: {share_path}")

    def on_start_camera_clicked(self) -> None:
        camera_text = self.camera_index_input.text().strip()
        camera_index = int(camera_text) if camera_text.isdigit() else 0

        if not self.scanner.open_camera(camera_index):
            self._show_error("Could not open camera. Check camera index and permissions.")
            return

        self.camera_timer.start()
        self.statusBar().showMessage("Camera started.")

    def on_stop_camera_clicked(self) -> None:
        self.camera_timer.stop()
        self.scanner.release_camera()
        self.statusBar().showMessage("Camera stopped.")

    def on_scan_image_clicked(self) -> None:
        initial_dir = self.settings.value("last_scan_dir", str(Path.home()))
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select image to scan",
            str(initial_dir),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not file_path:
            return

        self.settings.setValue("last_scan_dir", str(Path(file_path).parent))

        try:
            results = self.scanner.decode_image_file(file_path)
        except Exception as error:
            self._show_error(f"Scan failed: {error}")
            return

        if not results:
            self.statusBar().showMessage("No QR code found in selected image.")
            return

        for result in results:
            self._append_scan_result(result)
        self.statusBar().showMessage("Image scan complete.")

    def on_copy_scan_clicked(self) -> None:
        value = self.scan_result.toPlainText().strip()
        if not value:
            return
        QApplication.clipboard().setText(value)
        try:
            pyperclip.copy(value)
        except pyperclip.PyperclipException:
            pass
        self.statusBar().showMessage("Scan result copied.")

    def on_open_url_clicked(self) -> None:
        value = self.scan_result.toPlainText().strip()
        if not value:
            return
        url = QUrl.fromUserInput(value)
        if not url.isValid():
            self._show_error("Result is not a valid URL.")
            return
        QDesktopServices.openUrl(url)

    def on_clear_history_clicked(self) -> None:
        self.scan_history.clear()
        self.scan_result.clear()
        self.last_scan_value = ""
        self.last_scan_seen_at = None
        self._set_scan_actions_enabled(False)
        self.statusBar().showMessage("Scan history cleared.")

    def on_history_item_clicked(self, item: QListWidgetItem) -> None:
        value = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(value, str):
            self.scan_result.setPlainText(value)
            self._set_scan_actions_enabled(True)

    def on_increase_font_size_clicked(self) -> None:
        if self.font_size >= self.max_font_size:
            self.statusBar().showMessage(f"Maximum font size is {self.max_font_size}pt.")
            return
        self.font_size += 1
        self._apply_font_size()

    def on_decrease_font_size_clicked(self) -> None:
        if self.font_size <= self.min_font_size:
            self.statusBar().showMessage(f"Minimum font size is {self.min_font_size}pt.")
            return
        self.font_size -= 1
        self._apply_font_size()

    def on_reset_font_size_clicked(self) -> None:
        self.font_size = 10
        self._apply_font_size()

    def _append_scan_result(self, result: ScanResult) -> None:
        now = datetime.now()
        is_duplicate = (
            result.content == self.last_scan_value
            and self.last_scan_seen_at is not None
            and (now - self.last_scan_seen_at).total_seconds() < 1.2
        )
        self.last_scan_value = result.content
        self.last_scan_seen_at = now
        if is_duplicate:
            return

        self.scan_result.setPlainText(result.content)
        self._set_scan_actions_enabled(True)

        label = f"[{result.timestamp.strftime('%H:%M:%S')}] {result.code_type}: {result.content[:80]}"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, result.content)
        self.scan_history.insertItem(0, item)

    def _on_camera_tick(self) -> None:
        frame, results = self.scanner.read_frame()
        if frame is None:
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = frame_rgb.shape
        bytes_per_line = channels * width
        qimage = QImage(
            frame_rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        self.camera_preview.setPixmap(
            QPixmap.fromImage(qimage).scaled(
                self.camera_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        if not results:
            return
        for result in results:
            self._append_scan_result(result)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)
        self.statusBar().showMessage(message)

    def _apply_font_size(self, show_status: bool = True) -> None:
        app = QApplication.instance()
        if app is None:
            return
        font = app.font()
        font.setPointSize(self.font_size)
        app.setFont(font)
        self.settings.setValue("font_size", self.font_size)
        if show_status:
            self.statusBar().showMessage(f"Font size set to {self.font_size}pt.")

    def _ask_share_mode(self) -> ShareMode | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Share QR")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Choose how to share the generated QR image:"))

        open_with_button = QPushButton("Open With (choose app)")
        email_button = QPushButton("Email")
        folder_button = QPushButton("Open Containing Folder")
        cancel_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)

        layout.addWidget(open_with_button)
        layout.addWidget(email_button)
        layout.addWidget(folder_button)
        layout.addWidget(cancel_box)

        selected_mode: ShareMode | None = None

        def choose(mode: ShareMode) -> None:
            nonlocal selected_mode
            selected_mode = mode
            dialog.accept()

        open_with_button.clicked.connect(lambda: choose(ShareMode.OPEN_WITH))
        email_button.clicked.connect(lambda: choose(ShareMode.EMAIL))
        folder_button.clicked.connect(lambda: choose(ShareMode.FOLDER))
        cancel_box.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return selected_mode

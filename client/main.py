"""
client/main.py
--------------
Client application entry point.

Launch flow:
  1. Initialise local database
  2. Load config (server URL from local config.yaml)
  3. If first launch → SetupDialog (PIN + department)
  4. If logged out → PIN entry dialog
  5. If session active → open system tray widget directly

Widget implementation:
  ATTEMPTED: Windows taskbar band integration via COM.
  RESULT: Not achievable in pure Python without native C extensions.
  IMPLEMENTED: System tray icon + frameless floating popup anchored near taskbar.
  This is fully cross-platform (Windows + Linux).
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QFont, QPixmap

ICON_PATH = os.path.join(os.path.dirname(__file__), "ui", "icon.png")

try:
    import pystray
    from PIL import Image as PILImage
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

from client.storage.db import init_db
from client.storage.session import (
    is_first_launch, is_setup_complete, is_logged_in,
    verify_pin, create_session, logout, get_department
)
from client.api.submit import ServerClient
from client.ui.setup import SetupDialog
from client.ui.widget import StressWidget
from client.ui.letterbox import LetterboxWindow
from client.ui.styles import CLIENT_STYLESHEET


# ── Config loading ─────────────────────────────────────────

def load_client_config() -> dict:
    """Load server URL from config.yaml; fall back to localhost."""
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("client", {})
    except Exception:
        return {}


# ── PIN entry dialog ───────────────────────────────────────

class PinDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stress Letterbox")
        self.setFixedWidth(320)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setStyleSheet(CLIENT_STYLESHEET)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)

        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(ICON_PATH):
            pixmap = QPixmap(ICON_PATH).scaled(
                84, 84, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon.setPixmap(pixmap)
        else:
            icon.setText("✉")
            icon.setFont(QFont("Segoe UI", 56))
            icon.setStyleSheet("color: #7c6f5e;")

        brand = QLabel("Stress Letterbox")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFont(QFont("Segoe UI", 15, QFont.Weight.DemiBold))
        brand.setStyleSheet("color: #2c2825;")

        title = QLabel("Welcome back")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 12))
        title.setStyleSheet("color: #6a5f55;")

        self.pin_input = QLineEdit()
        self.pin_input.setObjectName("PinInput")
        self.pin_input.setPlaceholderText("Enter your PIN")
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_input.returnPressed.connect(self._check_pin)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: #b85c4a; font-size: 12px;")

        unlock_btn = QPushButton("Unlock")
        unlock_btn.setObjectName("LogButton")
        unlock_btn.clicked.connect(self._check_pin)

        layout.addWidget(icon)
        layout.addWidget(brand)
        layout.addWidget(title)
        layout.addWidget(self.pin_input)
        layout.addWidget(self.error_label)
        layout.addWidget(unlock_btn)

    def _check_pin(self):
        pin = self.pin_input.text()
        if verify_pin(pin):
            create_session()
            self.accept()
        else:
            self.error_label.setText("Incorrect PIN. Please try again.")
            self.pin_input.clear()
            self.pin_input.setFocus()


# ── Tray icon builder ──────────────────────────────────────

def _make_tray_image() -> "PILImage.Image":
    """Load the app icon for the tray; fall back to a simple drawn envelope."""
    if os.path.exists(ICON_PATH):
        return PILImage.open(ICON_PATH).convert("RGBA").resize((64, 64))
    from PIL import ImageDraw
    img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Envelope icon (simple geometric)
    draw.rectangle([4, 14, 60, 50], fill=(124, 111, 94, 255))
    draw.polygon([4, 14, 32, 34, 60, 14], fill=(100, 89, 76, 255))
    return img


# ── Application bootstrap ──────────────────────────────────

class LetterboxApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Stress Letterbox")
        self.app.setQuitOnLastWindowClosed(False)  # Keep running in tray
        if os.path.exists(ICON_PATH):
            self.app.setWindowIcon(QIcon(ICON_PATH))

        # Bootstrap
        init_db()
        client_cfg = load_client_config()
        server_url = client_cfg.get("server_url", "http://localhost:5000")
        self.server_client = ServerClient(server_url)
        self.config = {}
        self.widget = None
        self.letterbox_window = None
        self.tray_icon = None

    def run(self):
        # First launch → setup
        just_finished_setup = False
        if is_first_launch() or not is_setup_complete():
            setup = SetupDialog(self.server_client)
            if setup.exec() != QDialog.DialogCode.Accepted:
                sys.exit(0)
            just_finished_setup = True

        # Require PIN if not logged in — but not immediately after the wizard,
        # where the user just typed and confirmed the same PIN moments ago.
        if just_finished_setup:
            create_session()
        elif not is_logged_in():
            pin_dlg = PinDialog()
            if pin_dlg.exec() != QDialog.DialogCode.Accepted:
                sys.exit(0)

        # Fetch config from server (departments, reason cats, etc.)
        server_config = self.server_client.fetch_config()
        if server_config:
            self.config = server_config
        else:
            # Fall back to local config if server unreachable
            self.config = {
                "reason_categories": [],
                "departments": [],
                "entry_char_limit": 280,
                "reminder_frequency": "weekly",
            }

        # Build the main widget
        self.widget = StressWidget(self.server_client, self.config)
        self.widget.open_letterbox_requested.connect(self._open_letterbox)
        self.widget.logout_requested.connect(self._do_logout)

        # Set up system tray
        self._setup_tray()

        # Show widget on first open
        self.widget.show_near_taskbar()

        sys.exit(self.app.exec())

    def _setup_tray(self):
        if HAS_PYSTRAY:
            import threading

            def run_tray():
                img = _make_tray_image()
                menu = pystray.Menu(
                    pystray.MenuItem("Open Letterbox", lambda: self._toggle_widget()),
                    pystray.MenuItem("My Letterbox", lambda: self._open_letterbox()),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Sign out", lambda: self._do_logout()),
                    pystray.MenuItem("Quit", lambda: self._quit()),
                )
                self.tray_icon = pystray.Icon(
                    "stress_letterbox", img, "Stress Letterbox", menu
                )
                self.tray_icon.run()

            tray_thread = threading.Thread(target=run_tray, daemon=True)
            tray_thread.start()
        else:
            # pystray unavailable — widget stays open, no tray
            pass

    def _toggle_widget(self):
        # Must run UI changes on the main thread
        QTimer.singleShot(0, self.widget.toggle_visibility)

    def _open_letterbox(self):
        def _open():
            if self.letterbox_window is None or not self.letterbox_window.isVisible():
                self.letterbox_window = LetterboxWindow(
                    self.server_client, self.config
                )
            self.letterbox_window.show()
            self.letterbox_window.raise_()
            self.letterbox_window.activateWindow()
        QTimer.singleShot(0, _open)

    def _do_logout(self):
        def _logout():
            logout()
            if self.widget:
                self.widget.hide()
            if self.letterbox_window:
                self.letterbox_window.close()
            if self.tray_icon:
                self.tray_icon.stop()
            self.app.quit()
        QTimer.singleShot(0, _logout)

    def _quit(self):
        QTimer.singleShot(0, self.app.quit)


def main():
    LetterboxApp().run()


if __name__ == "__main__":
    main()

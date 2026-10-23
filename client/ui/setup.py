"""
client/ui/setup.py
------------------
First-launch setup dialog: PIN creation and department selection.
This runs once and stores results locally. Nothing is sent to the server here.
"""

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QWidget, QMessageBox, QStackedWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from client.storage.session import create_pin, set_department
from client.api.submit import ServerClient
from client.ui.styles import CLIENT_STYLESHEET

ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.png")


class SetupDialog(QDialog):
    """
    Multi-step first-launch setup.
    Step 1: Welcome
    Step 2: Create PIN
    Step 3: Select department
    """

    def __init__(self, server_client: ServerClient, parent=None):
        super().__init__(parent)
        self.server_client = server_client
        self.departments = []
        self.setWindowTitle("Welcome to Stress Letterbox")
        self.setMinimumWidth(400)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setStyleSheet(CLIENT_STYLESHEET)

        self._build_ui()
        self._fetch_departments()

    def _build_ui(self):
        self.stack = QStackedWidget()
        self.stack.addWidget(self._make_welcome_page())    # 0
        self.stack.addWidget(self._make_pin_page())        # 1
        self.stack.addWidget(self._make_dept_page())       # 2

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

    def _make_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(16)

        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(ICON_PATH):
            pixmap = QPixmap(ICON_PATH).scaled(
                96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon.setPixmap(pixmap)
        else:
            icon.setText("✉")
            icon.setFont(QFont("Segoe UI", 64))
            icon.setStyleSheet("color: #7c6f5e;")

        title = QLabel("Welcome to Stress Letterbox")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        title.setStyleSheet("color: #2c2825;")

        desc = QLabel(
            "A private space to note moments of workplace stress — just for you.\n\n"
            "What you log stays on this device until you choose to share it.\n"
            "Nothing identifies you when it's submitted."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #6a5f55; font-size: 13px; line-height: 1.5;")

        btn = QPushButton("Get started →")
        btn.setObjectName("LogButton")
        btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        layout.addStretch()
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addSpacing(12)
        layout.addWidget(btn)
        layout.addStretch()
        return page

    def _make_pin_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(14)

        title = QLabel("Create a PIN")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        title.setStyleSheet("color: #2c2825;")

        desc = QLabel(
            "This PIN protects your letterbox if others use this computer.\n"
            "It's stored only on this device and never sent anywhere."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #6a5f55; font-size: 12px;")

        self.pin_input = QLineEdit()
        self.pin_input.setObjectName("PinInput")
        self.pin_input.setPlaceholderText("Enter a PIN (4+ characters)")
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pin_confirm = QLineEdit()
        self.pin_confirm.setObjectName("PinInput")
        self.pin_confirm.setPlaceholderText("Confirm your PIN")
        self.pin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_confirm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pin_error = QLabel("")
        self.pin_error.setStyleSheet("color: #b85c4a; font-size: 12px;")
        self.pin_error.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("Next →")
        btn.setObjectName("LogButton")
        btn.clicked.connect(self._validate_pin)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addSpacing(8)
        layout.addWidget(QLabel("PIN"))
        layout.addWidget(self.pin_input)
        layout.addWidget(QLabel("Confirm PIN"))
        layout.addWidget(self.pin_confirm)
        layout.addWidget(self.pin_error)
        layout.addSpacing(4)
        layout.addWidget(btn)
        layout.addStretch()
        return page

    def _make_dept_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(14)

        title = QLabel("Which department are you in?")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        title.setStyleSheet("color: #2c2825;")

        desc = QLabel(
            "This is the only identifier attached to your entries.\n"
            "Departments are kept broad to protect your privacy."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #6a5f55; font-size: 12px;")

        self.dept_combo = QComboBox()
        self.dept_combo.addItem("— Select your department —", "")
        self.dept_status = QLabel("Fetching departments…")
        self.dept_status.setStyleSheet("color: #9a8f84; font-size: 12px;")

        self.dept_error = QLabel("")
        self.dept_error.setStyleSheet("color: #b85c4a; font-size: 12px;")

        btn = QPushButton("Start using Stress Letterbox")
        btn.setObjectName("LogButton")
        btn.clicked.connect(self._save_department)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addSpacing(8)
        layout.addWidget(QLabel("Department"))
        layout.addWidget(self.dept_combo)
        layout.addWidget(self.dept_status)
        layout.addWidget(self.dept_error)
        layout.addSpacing(4)
        layout.addWidget(btn)
        layout.addStretch()
        return page

    def _fetch_departments(self):
        cfg = self.server_client.fetch_config()
        if cfg and cfg.get("departments"):
            self.departments = cfg["departments"]
            self.dept_combo.clear()
            self.dept_combo.addItem("— Select your department —", "")
            for d in self.departments:
                self.dept_combo.addItem(d["name"], d["id"])
            self.dept_status.setText("")
        else:
            self.dept_status.setText(
                "⚠ Could not reach server. Check config and retry."
            )

    def _validate_pin(self):
        pin = self.pin_input.text()
        confirm = self.pin_confirm.text()
        if len(pin) < 4:
            self.pin_error.setText("PIN must be at least 4 characters.")
            return
        if pin != confirm:
            self.pin_error.setText("PINs do not match.")
            return
        self.pin_error.setText("")
        create_pin(pin)
        self.stack.setCurrentIndex(2)
        if not self.departments:
            self._fetch_departments()

    def _save_department(self):
        dept_id = self.dept_combo.currentData()
        if not dept_id:
            self.dept_error.setText("Please select your department.")
            return
        set_department(dept_id)
        self.accept()

"""
client/ui/widget.py
-------------------
System tray icon + floating popup widget (PyQt6).

TASKBAR INTEGRATION NOTE:
True Windows Shell Band embedding (like the Search bar) requires COM DLL
registration and is not achievable in pure Python without native C extensions.
The best Python-achievable equivalent is implemented here:
  - A system tray icon for persistent access
  - A frameless, always-on-top popup that appears anchored near the taskbar
    when the tray icon is left-clicked or activated
  - On Linux, this becomes a standard tray icon popup

This approach is fully documented as the primary implementation.
The pystray library handles the tray icon; PyQt6 handles the rich popup UI.
"""

import sys
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QApplication, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QScreen

from client.storage.session import (
    is_logged_in, logout, get_department,
    get_last_reminder_date, set_last_reminder_date
)
from client.storage.entries import add_entry, get_pending_count
from client.ui.styles import CLIENT_STYLESHEET
from shared.constants import STRESS_LEVELS


class DraggableHeader(QWidget):
    """A header bar that lets the user drag the frameless parent window by it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None


class StressWidget(QWidget):
    """
    The main floating popup widget.
    Frameless, always-on-top, positioned near the taskbar.
    """
    open_letterbox_requested = pyqtSignal()
    logout_requested = pyqtSignal()

    def __init__(self, server_client, config: dict, parent=None):
        super().__init__(parent)
        self.server_client = server_client
        self.config = config
        self.department = get_department()
        self.selected_stress = None
        self.char_limit = config.get("entry_char_limit", 280)

        self._setup_window()
        self._build_ui()
        self._check_reminder()

    def _setup_window(self):
        self.setObjectName("MainWidget")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumWidth(340)
        self.setMaximumWidth(420)
        self.setStyleSheet(CLIENT_STYLESHEET)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────
        header = DraggableHeader()
        header.setObjectName("HeaderBar")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(14, 10, 14, 10)

        title_col = QVBoxLayout()
        title = QLabel("Stress Letterbox")
        title.setObjectName("AppTitle")
        sub = QLabel("How are you doing?")
        sub.setObjectName("AppSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        title_col.setSpacing(1)

        pending = get_pending_count()
        self.count_badge = QLabel(f"{pending}" if pending else "")
        self.count_badge.setObjectName("CountBadge")
        self.count_badge.setVisible(pending > 0)
        self.count_badge.setToolTip(f"{pending} entries waiting to review")

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: #9a8f84; font-size: 18px; } "
            "QPushButton:hover { color: #4a3f35; }"
        )
        close_btn.clicked.connect(self.hide)

        hlay.addLayout(title_col)
        hlay.addStretch()
        hlay.addWidget(self.count_badge)
        hlay.addSpacing(6)
        hlay.addWidget(close_btn)
        root.addWidget(header)

        # ── Body ──────────────────────────────────────────
        body = QWidget()
        body.setObjectName("MainWidget")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(16, 14, 16, 14)
        blay.setSpacing(12)

        # Reminder bar (hidden by default)
        self.reminder_bar = QWidget()
        self.reminder_bar.setObjectName("ReminderBar")
        rlay = QHBoxLayout(self.reminder_bar)
        rlay.setContentsMargins(10, 8, 10, 8)
        self.reminder_label = QLabel()
        self.reminder_label.setObjectName("ReminderText")
        self.reminder_label.setWordWrap(True)
        dismiss = QPushButton("Later")
        dismiss.setObjectName("SecondaryButton")
        dismiss.setFixedWidth(60)
        dismiss.clicked.connect(self._dismiss_reminder)
        review_btn = QPushButton("Review →")
        review_btn.setObjectName("LogButton")
        review_btn.setFixedWidth(84)
        review_btn.clicked.connect(self.open_letterbox_requested.emit)
        rlay.addWidget(self.reminder_label, 1)
        rlay.addWidget(dismiss)
        rlay.addWidget(review_btn)
        self.reminder_bar.setVisible(False)
        blay.addWidget(self.reminder_bar)

        # Text input
        note_label = QLabel("What's on your mind?")
        note_label.setObjectName("SectionLabel")
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText(
            "Briefly describe what happened… (optional)"
        )
        self.text_input.setMaximumHeight(80)
        self.text_input.textChanged.connect(self._on_text_changed)

        self.char_counter = QLabel(f"0 / {self.char_limit}")
        self.char_counter.setStyleSheet("color: #b0a898; font-size: 11px;")
        self.char_counter.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Stress level selector
        level_label = QLabel("How does it feel?")
        level_label.setObjectName("SectionLabel")

        stress_row = QHBoxLayout()
        stress_row.setSpacing(6)
        self.stress_buttons = {}
        for level, name in STRESS_LEVELS.items():
            btn = QPushButton(f"{level}")
            btn.setToolTip(name)
            btn.setProperty("stress", str(level))
            btn.setProperty("selected", "false")
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda checked, l=level: self._select_stress(l))
            self.stress_buttons[level] = btn
            stress_row.addWidget(btn)

        # Level name display
        self.level_name = QLabel("")
        self.level_name.setStyleSheet("color: #9a8f84; font-size: 12px;")
        self.level_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Log button
        self.log_btn = QPushButton("Log this moment")
        self.log_btn.setObjectName("LogButton")
        self.log_btn.clicked.connect(self._log_entry)
        self.log_btn.setEnabled(False)

        # Bottom actions
        btn_row = QHBoxLayout()
        letterbox_btn = QPushButton("📬 My Letterbox")
        letterbox_btn.setObjectName("LetterboxButton")
        letterbox_btn.clicked.connect(self.open_letterbox_requested.emit)

        logout_btn = QPushButton("Sign out")
        logout_btn.setObjectName("LogoutButton")
        logout_btn.clicked.connect(self.logout_requested.emit)

        btn_row.addWidget(letterbox_btn)
        btn_row.addStretch()
        btn_row.addWidget(logout_btn)

        blay.addWidget(note_label)
        blay.addWidget(self.text_input)
        blay.addWidget(self.char_counter)
        blay.addWidget(level_label)
        blay.addLayout(stress_row)
        blay.addWidget(self.level_name)
        blay.addWidget(self.log_btn)
        blay.addLayout(btn_row)

        root.addWidget(body)

    def _on_text_changed(self):
        text = self.text_input.toPlainText()
        if len(text) > self.char_limit:
            # Enforce character limit silently
            cursor = self.text_input.textCursor()
            self.text_input.setPlainText(text[:self.char_limit])
            self.text_input.setTextCursor(cursor)
            text = text[:self.char_limit]
        self.char_counter.setText(f"{len(text)} / {self.char_limit}")
        self._update_log_button()

    def _select_stress(self, level: int):
        self.selected_stress = level
        for l, btn in self.stress_buttons.items():
            btn.setProperty("selected", "true" if l == level else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.level_name.setText(STRESS_LEVELS.get(level, ""))
        self._update_log_button()

    def _update_log_button(self):
        has_stress = self.selected_stress is not None
        self.log_btn.setEnabled(has_stress)

    def _log_entry(self):
        if not self.selected_stress:
            return
        description = self.text_input.toPlainText().strip()
        dept = self.department or get_department() or "unknown"

        entry_id = add_entry(
            description=description,
            stress_level=self.selected_stress,
            department=dept,
        )

        # Reset UI
        self.text_input.clear()
        self._select_stress_none()

        # Update badge
        pending = get_pending_count()
        self.count_badge.setText(str(pending))
        self.count_badge.setVisible(pending > 0)

        # Brief confirmation
        self.log_btn.setText("✓ Logged")
        QTimer.singleShot(1500, lambda: self.log_btn.setText("Log this moment"))

    def _select_stress_none(self):
        self.selected_stress = None
        for btn in self.stress_buttons.values():
            btn.setProperty("selected", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.level_name.setText("")
        self.log_btn.setEnabled(False)

    def _check_reminder(self):
        """
        Show a gentle reminder if the submission schedule says it's time.

        The reminder threshold is checked against the last time the reminder
        was SHOWN (not just dismissed). This prevents the bar appearing on
        every launch within the same week/month.
        """
        from datetime import date
        freq = self.config.get("reminder_frequency", "weekly")
        last = get_last_reminder_date()

        if last:
            last_date = datetime.fromisoformat(last).date()
            days_since = (date.today() - last_date).days
            threshold = 7 if freq == "weekly" else 30
            if days_since < threshold:
                return  # Not due yet

        pending = get_pending_count()
        if pending > 0:
            self.reminder_label.setText(
                f"You have {pending} note{'s' if pending != 1 else ''} waiting. "
                f"Ready to review and submit?"
            )
            self.reminder_bar.setVisible(True)
            # Record that we showed the reminder today.
            # This suppresses it for the next threshold period regardless
            # of whether the user dismisses or ignores it.
            set_last_reminder_date(date.today().isoformat())

    def _dismiss_reminder(self):
        """Hide the reminder bar. The date was already recorded when it was shown."""
        self.reminder_bar.setVisible(False)

    def show_near_taskbar(self):
        """Position the widget near the bottom of the screen (taskbar area)."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.adjustSize()
            x = geo.right() - self.width() - 20
            y = geo.bottom() - self.height() - 10
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show_near_taskbar()

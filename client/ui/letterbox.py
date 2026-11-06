"""
client/ui/letterbox.py
----------------------
The letterbox view: review, enrich, delete, and submit entries.
Opened from the main widget's "My Letterbox" button.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QDialog, QTextEdit, QComboBox, QMessageBox,
    QCheckBox, QFrame, QSizePolicy, QSplitter, QLineEdit,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor

from client.storage.entries import (
    get_all_entries, update_entry, delete_entry,
    mark_submitted, get_pending_entries
)
from client.storage.session import get_department
from client.api.submit import ServerClient
from client.ui.styles import CLIENT_STYLESHEET
from shared.constants import STRESS_LEVELS


def _category_label(categories: list, cat_id: str) -> str:
    """Label for a reason/solution id, falling back to the id itself."""
    return next((c["label"] for c in categories if c["id"] == cat_id), cat_id)


class EntryCard(QFrame):
    """A single entry displayed in the letterbox."""
    delete_requested = pyqtSignal(int)
    edit_requested   = pyqtSignal(int)

    LEVEL_COLOURS = {
        1: "#a8c5a0", 2: "#d4c88a", 3: "#e8b96a",
        4: "#d4845a", 5: "#b85c4a"
    }

    def __init__(self, entry: dict, reason_categories: list,
                 solution_categories: list, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.reason_categories = reason_categories
        self.solution_categories = solution_categories
        self.setObjectName("EntryCard")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(14, 12, 14, 12)

        # Top row: timestamp + stress badge + actions
        top = QHBoxLayout()
        ts = datetime.fromisoformat(self.entry["timestamp"])
        ts_label = QLabel(ts.strftime("%d %b %Y, %H:%M"))
        ts_label.setObjectName("EntryTimestamp")

        level = self.entry["stress_level"]
        badge_text = f"{level} · {STRESS_LEVELS.get(level, '')}"
        badge = QLabel(badge_text)
        badge.setObjectName("StressBadge")
        colour = self.LEVEL_COLOURS.get(level, "#ccc")
        badge.setStyleSheet(
            f"background-color: {colour}20; color: {colour}; "
            f"border: 1px solid {colour}60; border-radius: 6px; "
            f"font-size: 11px; font-weight: 600; padding: 2px 8px;"
        )

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("SecondaryButton")
        edit_btn.setFixedHeight(26)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.entry["id"]))

        del_btn = QPushButton("Delete")
        del_btn.setFixedHeight(26)
        del_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #b85c4a; "
            "border: 1px solid #d4845a; border-radius: 6px; "
            "font-size: 12px; padding: 3px 10px; } "
            "QPushButton:hover { background: #fde8e0; }"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.entry["id"]))

        if self.entry.get("submitted"):
            submitted_label = QLabel("✓ Submitted")
            submitted_label.setStyleSheet("color: #5a8050; font-size: 11px; font-weight: 600;")
            top.addWidget(submitted_label)

        top.addWidget(ts_label)
        top.addStretch()
        top.addWidget(badge)
        top.addSpacing(6)
        top.addWidget(edit_btn)
        top.addWidget(del_btn)
        layout.addLayout(top)

        # Description
        desc = self.entry.get("description", "")
        if desc:
            desc_label = QLabel(desc)
            desc_label.setObjectName("EntryDescription")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
        else:
            no_desc = QLabel("(no description)")
            no_desc.setStyleSheet("color: #b0a898; font-style: italic; font-size: 12px;")
            layout.addWidget(no_desc)

        # Metadata row: reason + suggested solution
        meta_parts = []
        if cat := self.entry.get("reason_category"):
            meta_parts.append(f"📌 {_category_label(self.reason_categories, cat)}")
        if sol := self.entry.get("solution_category"):
            meta_parts.append(f"💡 {_category_label(self.solution_categories, sol)}")
        if meta_parts:
            meta = QLabel("  ·  ".join(meta_parts))
            meta.setObjectName("EntryMeta")
            layout.addWidget(meta)


class EditEntryDialog(QDialog):
    """Edit an entry's description, reason, suggested solution, and elaboration."""

    def __init__(self, entry: dict, reason_categories: list,
                 solution_categories: list, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.reason_categories = reason_categories
        self.solution_categories = solution_categories
        self.setWindowTitle("Edit entry")
        self.setMinimumWidth(440)
        self.setStyleSheet(CLIENT_STYLESHEET)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        layout.addWidget(QLabel("Description — stays on this device, never sent"))
        self.desc_input = QTextEdit()
        self.desc_input.setPlainText(self.entry.get("description", ""))
        self.desc_input.setMaximumHeight(90)
        layout.addWidget(self.desc_input)

        layout.addWidget(QLabel("Reason (optional) — this is shared when you submit"))
        self.reason_combo = QComboBox()
        self.reason_combo.addItem("— No reason selected —", "")
        for cat in self.reason_categories:
            self.reason_combo.addItem(cat["label"], cat["id"])
        current_cat = self.entry.get("reason_category") or ""
        idx = self.reason_combo.findData(current_cat)
        if idx >= 0:
            self.reason_combo.setCurrentIndex(idx)
        layout.addWidget(self.reason_combo)

        # Only offered when the server's config.yaml lists solutions
        self.solution_combo = None
        if self.solution_categories:
            layout.addWidget(QLabel(
                "What would help? (optional) — this is shared when you submit"
            ))
            self.solution_combo = QComboBox()
            self.solution_combo.addItem("— No suggestion —", "")
            for sol in self.solution_categories:
                self.solution_combo.addItem(sol["label"], sol["id"])
            idx = self.solution_combo.findData(self.entry.get("solution_category") or "")
            if idx >= 0:
                self.solution_combo.setCurrentIndex(idx)
            layout.addWidget(self.solution_combo)

        layout.addWidget(QLabel("Personal notes (optional) — stays on this device, never sent"))
        self.elab_input = QTextEdit()
        self.elab_input.setPlaceholderText("A note to yourself — this never leaves your device…")
        self.elab_input.setPlainText(self.entry.get("elaboration") or "")
        self.elab_input.setMaximumHeight(70)
        layout.addWidget(self.elab_input)

        # Buttons
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save changes")
        save_btn.setObjectName("LogButton")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def get_values(self) -> dict:
        return {
            "description":     self.desc_input.toPlainText().strip(),
            "reason_category": self.reason_combo.currentData() or None,
            "solution_category": (self.solution_combo.currentData() or None
                                  if self.solution_combo else
                                  self.entry.get("solution_category")),
            "elaboration":     self.elab_input.toPlainText().strip() or None,
        }


class LetterboxWindow(QWidget):
    """The main letterbox window: lists all entries, allows edit/delete/submit."""

    def __init__(self, server_client: ServerClient, config: dict, parent=None):
        super().__init__(parent)
        self.server_client = server_client
        self.config = config
        self.reason_categories = config.get("reason_categories", [])
        self.solution_categories = config.get("solution_categories", [])
        self.setWindowTitle("My Letterbox")
        self.setMinimumSize(520, 600)
        self.setStyleSheet(CLIENT_STYLESHEET)
        self._build_ui()
        self._refresh_entries()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title = QLabel("My Letterbox")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.DemiBold))
        title.setStyleSheet("color: #2c2825;")

        self.count_label = QLabel()
        self.count_label.setObjectName("CountBadge")

        submit_btn = QPushButton("Review & Submit →")
        submit_btn.setObjectName("LogButton")
        submit_btn.clicked.connect(self._open_submit_dialog)

        header.addWidget(title)
        header.addWidget(self.count_label)
        header.addStretch()
        header.addWidget(submit_btn)
        layout.addLayout(header)

        # Scroll area for entries
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.entries_container = QWidget()
        self.entries_layout = QVBoxLayout(self.entries_container)
        self.entries_layout.setContentsMargins(0, 0, 0, 0)
        self.entries_layout.setSpacing(8)
        self.entries_layout.addStretch()

        self.scroll.setWidget(self.entries_container)
        layout.addWidget(self.scroll)

    def _refresh_entries(self):
        # Clear existing cards
        while self.entries_layout.count() > 1:
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        entries = get_all_entries(include_submitted=True)
        self.count_label.setText(f"{len(entries)}")
        self.count_label.setVisible(bool(entries))

        if not entries:
            empty = QLabel("Nothing here yet.\nLog your first moment from the main widget.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #b0a898; font-size: 13px; padding: 40px;")
            self.entries_layout.insertWidget(0, empty)
            return

        for entry in entries:
            card = EntryCard(entry, self.reason_categories, self.solution_categories)
            card.delete_requested.connect(self._confirm_delete)
            card.edit_requested.connect(self._open_edit)
            self.entries_layout.insertWidget(self.entries_layout.count() - 1, card)

    def _confirm_delete(self, entry_id: int):
        msg = QMessageBox(self)
        msg.setWindowTitle("Delete entry")
        msg.setText("Delete this entry permanently?")
        msg.setInformativeText(
            "This cannot be undone. The entry will be removed from your device "
            "and will never be submitted."
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setStyleSheet(CLIENT_STYLESHEET)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            delete_entry(entry_id)
            self._refresh_entries()

    def _open_edit(self, entry_id: int):
        from client.storage.entries import get_entry
        entry = get_entry(entry_id)
        if not entry:
            return
        dlg = EditEntryDialog(entry, self.reason_categories,
                              self.solution_categories, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            update_entry(entry_id, **dlg.get_values())
            self._refresh_entries()

    def _open_submit_dialog(self):
        pending = get_pending_entries()
        if not pending:
            QMessageBox.information(
                self, "Nothing to submit",
                "You have no pending entries to submit.",
            )
            return
        dlg = SubmitDialog(pending, self.server_client, self.reason_categories,
                           self.solution_categories, self)
        dlg.exec()
        self._refresh_entries()


class SubmitDialog(QDialog):
    """
    Review and confirm submission.
    Shows exactly what will be sent (anonymised fields only).
    User can deselect entries before confirming.
    """

    def __init__(self, entries: list[dict], server_client: ServerClient,
                 reason_categories: list, solution_categories: list, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.server_client = server_client
        self.reason_categories = reason_categories
        self.solution_categories = solution_categories
        self.checkboxes = {}
        self.setWindowTitle("Review & Submit")
        self.setMinimumSize(480, 500)
        self.setStyleSheet(CLIENT_STYLESHEET)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Review before submitting")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))

        desc = QLabel(
            "Only department, timestamp, stress level, reason, and suggested solution\n"
            "are sent — no names, no machine identifiers, no location, and none of\n"
            "your written notes.\n"
            "Untick any entry you'd rather not send right now."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #6a5f55; font-size: 12px;")

        layout.addWidget(title)
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        clay = QVBoxLayout(container)
        clay.setSpacing(6)

        for entry in self.entries:
            row = QHBoxLayout()
            cb = QCheckBox()
            cb.setChecked(True)
            self.checkboxes[entry["id"]] = cb

            ts = datetime.fromisoformat(entry["timestamp"]).strftime("%d %b, %H:%M")
            level = STRESS_LEVELS.get(entry["stress_level"], str(entry["stress_level"]))
            cat_label = _category_label(self.reason_categories,
                                        entry.get("reason_category") or "—")
            sol_label = _category_label(self.solution_categories,
                                        entry.get("solution_category") or "—")
            summary = QLabel(
                f"<b>{ts}</b> · Level {entry['stress_level']} ({level})"
                f"<br><small style='color:#9a8f84'>"
                f"Dept: {entry['department']} · Reason: {cat_label}"
                f" · Solution: {sol_label}"
                f"</small>"
            )
            summary.setTextFormat(Qt.TextFormat.RichText)

            row.addWidget(cb)
            row.addWidget(summary, 1)
            clay.addLayout(row)

        clay.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Action row
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.clicked.connect(self.reject)

        self.submit_btn = QPushButton("Submit selected")
        self.submit_btn.setObjectName("LogButton")
        self.submit_btn.clicked.connect(self._do_submit)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.submit_btn)
        layout.addLayout(btn_row)

    def _do_submit(self):
        selected_ids = [eid for eid, cb in self.checkboxes.items() if cb.isChecked()]
        if not selected_ids:
            QMessageBox.information(self, "Nothing selected",
                                    "Please select at least one entry to submit.")
            return

        selected_entries = [e for e in self.entries if e["id"] in selected_ids]
        self.submit_btn.setEnabled(False)
        self.submit_btn.setText("Submitting…")

        success, message = self.server_client.submit_entries(selected_entries)

        if success:
            mark_submitted(selected_ids)
            QMessageBox.information(
                self, "Submitted",
                f"Done. {message}\n\nThank you for sharing."
            )
            self.accept()
        else:
            self.submit_btn.setEnabled(True)
            self.submit_btn.setText("Submit selected")
            QMessageBox.warning(self, "Could not submit", message)

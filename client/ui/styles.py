"""
client/ui/styles.py
-------------------
Centralised PyQt6 stylesheet (QSS) for the client application.

Design language: Calm, warm, non-clinical.
- Soft warm neutrals (not clinical white or alarm red)
- Rounded corners throughout
- Gentle typography
- No urgency-signalling colours
"""

import os


def _checkmark_asset_path() -> str:
    """
    Return an absolute path to a small white checkmark PNG, generating it
    once with Pillow if missing (same lightweight approach main.py already
    uses for the tray icon). QSS can't draw a tick glyph directly — a
    checked QCheckBox indicator needs an actual image.
    """
    path = os.path.join(os.path.dirname(__file__), "checkmark.png")
    if not os.path.exists(path):
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.line([(3, 8), (7, 12), (13, 4)], fill=(255, 255, 255, 255), width=2)
        img.save(path)
    return path.replace(os.sep, "/")


# Warm off-white background, soft terracotta/sage accents
CLIENT_STYLESHEET = """
QWidget {
    background-color: #f7f4f0;
    color: #2c2825;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* ── Main widget frame ──────────────────────────────── */
#MainWidget {
    background-color: #faf8f5;
    border: 1px solid #e0d9d0;
    border-radius: 16px;
}

/* ── Header ─────────────────────────────────────────── */
#HeaderBar {
    background-color: #f0ebe3;
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
    border-bottom: 1px solid #e0d9d0;
    padding: 10px 16px;
}

#AppTitle {
    font-size: 14px;
    font-weight: 600;
    color: #4a3f35;
    letter-spacing: -0.3px;
}

#AppSubtitle {
    font-size: 11px;
    color: #9a8f84;
    font-weight: 400;
}

/* ── Text input ─────────────────────────────────────── */
QTextEdit, QLineEdit {
    background-color: #ffffff;
    border: 1px solid #ddd5c8;
    border-radius: 10px;
    padding: 10px 12px;
    color: #2c2825;
    font-size: 13px;
    selection-background-color: #d4c8b8;
}

QTextEdit:focus, QLineEdit:focus {
    border-color: #b09880;
    outline: none;
}

QTextEdit::placeholder, QLineEdit::placeholder {
    color: #b8afa6;
}

/* ── Stress level buttons ───────────────────────────── */
#StressBar {
    background-color: transparent;
    spacing: 6px;
}

QPushButton[stress="1"] { background-color: #a8c5a0; color: #2a3a28; }
QPushButton[stress="2"] { background-color: #d4c88a; color: #3a3218; }
QPushButton[stress="3"] { background-color: #e8b96a; color: #3a2c10; }
QPushButton[stress="4"] { background-color: #d4845a; color: #3a1a0a; }
QPushButton[stress="5"] { background-color: #b85c4a; color: #ffffff; }

QPushButton[stress="1"][selected="true"] { border: 2px solid #5a8050; }
QPushButton[stress="2"][selected="true"] { border: 2px solid #8a7a20; }
QPushButton[stress="3"][selected="true"] { border: 2px solid #9a6010; }
QPushButton[stress="4"][selected="true"] { border: 2px solid #8a4020; }
QPushButton[stress="5"][selected="true"] { border: 2px solid #6a1a10; }

QPushButton[stress] {
    border-radius: 8px;
    font-size: 12px;
    font-weight: 500;
    padding: 6px 10px;
    min-width: 52px;
    border: 2px solid transparent;
}

QPushButton[stress]:hover { opacity: 0.85; }

/* ── Primary action button ──────────────────────────── */
QPushButton#LogButton {
    background-color: #7c6f5e;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    padding: 10px 20px;
    letter-spacing: 0.2px;
}

QPushButton#LogButton:hover {
    background-color: #5c5248;
}

QPushButton#LogButton:pressed {
    background-color: #4a4038;
}

QPushButton#LogButton:disabled {
    background-color: #c8c0b8;
    color: #a09898;
}

/* ── Secondary buttons ──────────────────────────────── */
QPushButton#SecondaryButton, QPushButton#LetterboxButton, QPushButton#LogoutButton {
    background-color: transparent;
    color: #7c6f5e;
    border: 1px solid #d0c8be;
    border-radius: 8px;
    font-size: 12px;
    padding: 7px 14px;
}

QPushButton#SecondaryButton:hover,
QPushButton#LetterboxButton:hover,
QPushButton#LogoutButton:hover {
    background-color: #ede8e0;
    border-color: #b0a898;
}

/* ── Letterbox view ─────────────────────────────────── */
QScrollArea {
    background-color: transparent;
    border: none;
}

QScrollBar:vertical {
    background: #f0ebe3;
    width: 6px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background: #c8bfb4;
    border-radius: 3px;
    min-height: 20px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* ── Entry card ─────────────────────────────────────── */
#EntryCard {
    background-color: #ffffff;
    border: 1px solid #ede5da;
    border-radius: 12px;
    padding: 14px;
    margin: 4px 2px;
}

#EntryCard:hover {
    border-color: #c8bfb4;
    background-color: #fdfbf8;
}

#EntryTimestamp {
    font-size: 11px;
    color: #b0a898;
}

#EntryDescription {
    font-size: 13px;
    color: #2c2825;
    margin: 4px 0;
}

#EntryMeta {
    font-size: 11px;
    color: #9a8f84;
}

/* ── Stress badge ───────────────────────────────────── */
#StressBadge {
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
}

/* ── Labels ─────────────────────────────────────────── */
QLabel#SectionLabel {
    font-size: 11px;
    color: #9a8f84;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QLabel#CountBadge {
    background-color: #e8e0d5;
    color: #7c6f5e;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
}

/* ── Checkboxes ─────────────────────────────────────── */
/* Qt switches a checkbox's indicator to CSS rendering as soon as any
   stylesheet touches the window, so it needs an explicit style here —
   otherwise the box outline is nearly invisible while checked. */
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #b0a898;
    border-radius: 4px;
    background-color: #ffffff;
}

QCheckBox::indicator:hover {
    border-color: #7c6f5e;
}

QCheckBox::indicator:checked {
    background-color: #7c6f5e;
    border-color: #7c6f5e;
    image: url("__CHECKMARK_PATH__");
}

/* ── Combo boxes ────────────────────────────────────── */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #ddd5c8;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 13px;
    color: #2c2825;
    min-width: 140px;
}

QComboBox:focus { border-color: #b09880; }

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #ddd5c8;
    border-radius: 8px;
    selection-background-color: #ede8e0;
    selection-color: #2c2825;
    padding: 4px;
}

/* ── PIN entry ──────────────────────────────────────── */
QLineEdit#PinInput {
    letter-spacing: 4px;
    font-size: 18px;
    text-align: center;
    border: 2px solid #ddd5c8;
    border-radius: 12px;
    padding: 12px;
}

/* ── Notification / reminder bar ───────────────────── */
#ReminderBar {
    background-color: #f0e8d8;
    border: 1px solid #d8c8a8;
    border-radius: 10px;
    padding: 10px 14px;
}

#ReminderText {
    font-size: 12px;
    color: #6a5840;
}

/* ── Tooltips ───────────────────────────────────────── */
QToolTip {
    background-color: #4a3f35;
    color: #f7f4f0;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ── Dialog buttons ─────────────────────────────────── */
QDialogButtonBox QPushButton {
    background-color: #7c6f5e;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    min-width: 80px;
}

QDialogButtonBox QPushButton:hover {
    background-color: #5c5248;
}

QDialogButtonBox QPushButton[text="Cancel"],
QDialogButtonBox QPushButton[text="No"] {
    background-color: transparent;
    color: #7c6f5e;
    border: 1px solid #d0c8be;
}

QDialogButtonBox QPushButton[text="Cancel"]:hover,
QDialogButtonBox QPushButton[text="No"]:hover {
    background-color: #ede8e0;
}
"""

CLIENT_STYLESHEET = CLIENT_STYLESHEET.replace("__CHECKMARK_PATH__", _checkmark_asset_path())

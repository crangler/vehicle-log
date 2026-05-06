from PySide6.QtGui import QColor, QPalette


# ── themes ──────────────────────────────────────────────────────────────────

def _make_palette(
    window, window_text, base, alt_base, text, button, button_text,
    highlight, highlighted_text,
) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(window))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(window_text))
    p.setColor(QPalette.ColorRole.Base,            QColor(base))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(alt_base))
    p.setColor(QPalette.ColorRole.Text,            QColor(text))
    p.setColor(QPalette.ColorRole.Button,          QColor(button))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(button_text))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(highlight))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(highlighted_text))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(base))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(text))
    return p


def dark_palette() -> QPalette:
    return _make_palette(
        window="#2d2d2d", window_text="#dcdcdc",
        base="#1e1e1e",   alt_base="#282828",
        text="#dcdcdc",
        button="#373737", button_text="#dcdcdc",
        highlight="#2a82da", highlighted_text="#000000",
    )


def light_palette() -> QPalette:
    return _make_palette(
        window="#f0f0f0", window_text="#000000",
        base="#ffffff",   alt_base="#e9e9e9",
        text="#000000",
        button="#f0f0f0", button_text="#000000",
        highlight="#0078d7", highlighted_text="#ffffff",
    )

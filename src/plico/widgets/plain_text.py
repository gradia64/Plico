"""Text from a document is shown as text, never as markup.

A QLabel left on its default format decides by itself whether a string is
rich text, and anything that looks like a tag is enough: a field name, a file
name, a certificate subject or a library error built from them could print
styled text -- a green "valid signature", a clickable link -- inside Plico's
own interface (reported by a pentest). Every label that shows something read
from a file says it is plain text; this module covers the dialogs Plico does
not build itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget


def plain_labels(widget: QWidget) -> None:
    """Turn every label of *widget* that is left to guess into plain text.

    A label set to rich text explicitly keeps it: that is a decision, not a
    guess.
    """
    for label in widget.findChildren(QLabel):
        if label.textFormat() == Qt.TextFormat.AutoText:
            label.setTextFormat(Qt.TextFormat.PlainText)

"""Auswahl von Symbolen (Unicode-Zeichen aus DejaVu Sans)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ptlabel.document import SYMBOL_FONT

CATEGORIES = {
    "Allgemein": "★☆✓✔✗✘⚠⚡⚙♻☢☣♨⚕⚗⚛⚑⚐⚓⚒⚖♿⌂⏏⌨✂✎✏✉☎☏✆☕✈",
    "Musik & Freizeit": "♩♪♫♬♥♡♦♣♠☀☁☂☃❄❅❆✿❀☺☹☻☯☮",
    "Pfeile": "←→↑↓↔↕⇐⇒⇑⇓⇔⇦⇨⇧⇩➜➔➞➡⬅⬆⬇↺↻⟲⟳",
    "Formen": "●○◆◇■□▲△▼▽◀▶☐☑☒⊕⊖",
    "Zeichen & Einheiten": "€$£¥°±×÷µΩ∞≈≠≤≥√∑πΔ⌀‰§¶©®™℃℉∿♀♂",
    "Nummern": "①②③④⑤⑥⑦⑧⑨⑩",
}


class SymbolDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Symbol einfügen")
        self.symbol: str | None = None

        font = QFont(SYMBOL_FONT, 20)
        metrics = QFontMetrics(font)
        content = QWidget()
        layout = QVBoxLayout(content)
        for title, chars in CATEGORIES.items():
            heading = QLabel(title)
            heading.setStyleSheet("font-weight:600; margin-top:8px;")
            layout.addWidget(heading)
            grid = QGridLayout()
            grid.setSpacing(4)
            chars = [c for c in chars if metrics.inFontUcs4(ord(c))]
            for index, char in enumerate(chars):
                button = QToolButton()
                button.setText(char)
                button.setFont(font)
                button.setFixedSize(QSize(44, 44))
                button.setToolTip(f"U+{ord(char):04X}")
                button.clicked.connect(lambda _=False, c=char: self._choose(c))
                grid.addWidget(button, index // 10, index % 10)
            layout.addLayout(grid)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll)
        outer.addWidget(buttons)
        self.resize(560, 520)

    def _choose(self, char: str) -> None:
        self.symbol = char
        self.accept()

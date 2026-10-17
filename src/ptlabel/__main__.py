"""Einstiegspunkt: minimales Fenster zum Testen der Kette Oberfläche → Bild → Drucker.

Die eigentliche Oberfläche (nach Vorbild des P-touch Editors) entsteht hier später.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ptlabel import printer

MARGIN_PX = 10


def render_label(text: str, font: QFont, height_px: int) -> QImage:
    """Zeichnet den Text so groß wie möglich in die Bandhöhe."""
    font = QFont(font)
    font.setPixelSize(max(8, int(height_px * 0.8)))
    width = QFontMetrics(font).horizontalAdvance(text or " ") + 2 * MARGIN_PX

    image = QImage(width, height_px, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return image


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ptlabel")

        self.text = QLineEdit("Hallo Welt")
        self.font_box = QFontComboBox()
        self.tape = QComboBox()
        self.tape.addItems(printer.TAPE_HEIGHT_PX.keys())
        self.tape.setCurrentText("12 mm")
        self.preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(160)
        self.preview.setStyleSheet("background:#ddd;")

        info_btn = QPushButton("Drucker prüfen")
        print_btn = QPushButton("Drucken")
        info_btn.clicked.connect(self.show_info)
        print_btn.clicked.connect(self.do_print)

        row = QHBoxLayout()
        row.addWidget(QLabel("Band:"))
        row.addWidget(self.tape)
        row.addWidget(self.font_box, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(info_btn)
        buttons.addWidget(print_btn)

        layout = QVBoxLayout()
        layout.addWidget(self.text)
        layout.addLayout(row)
        layout.addWidget(self.preview, 1)
        layout.addLayout(buttons)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        for signal in (self.text.textChanged, self.font_box.currentFontChanged,
                       self.tape.currentTextChanged):
            signal.connect(self.update_preview)
        self.update_preview()
        self.resize(600, 320)

    def current_image(self) -> QImage:
        height = printer.TAPE_HEIGHT_PX[self.tape.currentText()]
        return render_label(self.text.text(), self.font_box.currentFont(), height)

    def update_preview(self, *_args) -> None:
        pix = QPixmap.fromImage(self.current_image())
        self.preview.setPixmap(pix.scaledToHeight(128, Qt.TransformationMode.SmoothTransformation))

    def show_info(self) -> None:
        try:
            QMessageBox.information(self, "Drucker", printer.info())
        except printer.PrinterError as err:
            QMessageBox.warning(self, "Drucker", str(err))

    def do_print(self) -> None:
        try:
            printer.print_image(self.current_image())
        except printer.PrinterError as err:
            QMessageBox.warning(self, "Druckfehler", str(err))


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

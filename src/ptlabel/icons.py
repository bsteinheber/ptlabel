"""Einfache, selbst gezeichnete Symbole für die Werkzeugleiste (kein Icon-Theme nötig)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

ACCENT = QColor("#1a56c8")
SIZE = 64


def _canvas() -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(ACCENT, 4)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    return pixmap, painter


def glyph(char: str, family: str = "DejaVu Sans", bold: bool = False) -> QIcon:
    pixmap, painter = _canvas()
    font = QFont(family)
    font.setPixelSize(44)
    font.setBold(bold)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, SIZE, SIZE), Qt.AlignmentFlag.AlignCenter, char)
    painter.end()
    return QIcon(pixmap)


def text() -> QIcon:
    pixmap, painter = _canvas()
    painter.drawRoundedRect(QRectF(10, 10, 44, 44), 6, 6)
    font = QFont("DejaVu Sans")
    font.setPixelSize(32)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(10, 10, 44, 44), Qt.AlignmentFlag.AlignCenter, "T")
    painter.end()
    return QIcon(pixmap)


def image() -> QIcon:
    pixmap, painter = _canvas()
    painter.drawRoundedRect(QRectF(8, 12, 48, 40), 5, 5)
    path = QPainterPath(QPointF(12, 48))
    path.lineTo(26, 30)
    path.lineTo(36, 40)
    path.lineTo(42, 34)
    path.lineTo(52, 48)
    painter.drawPath(path)
    painter.drawEllipse(QPointF(42, 22), 4, 4)
    painter.end()
    return QIcon(pixmap)


def printer() -> QIcon:
    pixmap, painter = _canvas()
    painter.drawRect(QRectF(20, 8, 24, 14))
    painter.drawRoundedRect(QRectF(8, 22, 48, 22), 4, 4)
    painter.drawRect(QRectF(20, 36, 24, 20))
    painter.drawLine(QPointF(25, 44), QPointF(39, 44))
    painter.drawLine(QPointF(25, 50), QPointF(39, 50))
    painter.end()
    return QIcon(pixmap)


def save() -> QIcon:
    pixmap, painter = _canvas()
    path = QPainterPath(QPointF(10, 10))
    path.lineTo(46, 10)
    path.lineTo(54, 18)
    path.lineTo(54, 54)
    path.lineTo(10, 54)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawRect(QRectF(20, 10, 22, 14))
    painter.drawRect(QRectF(18, 34, 28, 20))
    painter.end()
    return QIcon(pixmap)


def home() -> QIcon:
    pixmap, painter = _canvas()
    path = QPainterPath(QPointF(8, 30))
    path.lineTo(32, 8)
    path.lineTo(56, 30)
    painter.drawPath(path)
    path = QPainterPath(QPointF(16, 24))
    path.lineTo(16, 54)
    path.lineTo(48, 54)
    path.lineTo(48, 24)
    painter.drawPath(path)
    painter.drawRect(QRectF(27, 38, 10, 16))
    painter.end()
    return QIcon(pixmap)


def delete() -> QIcon:
    pixmap, painter = _canvas()
    painter.drawLine(QPointF(10, 16), QPointF(54, 16))
    painter.drawLine(QPointF(26, 16), QPointF(26, 9))
    painter.drawLine(QPointF(26, 9), QPointF(38, 9))
    painter.drawLine(QPointF(38, 9), QPointF(38, 16))
    path = QPainterPath(QPointF(16, 16))
    path.lineTo(19, 56)
    path.lineTo(45, 56)
    path.lineTo(48, 16)
    painter.drawPath(path)
    painter.drawLine(QPointF(27, 26), QPointF(27, 46))
    painter.drawLine(QPointF(37, 26), QPointF(37, 46))
    painter.end()
    return QIcon(pixmap)


def align(kind: str) -> QIcon:
    """Textausrichtung: left, center, right, justify."""
    pixmap, painter = _canvas()
    for index, length in enumerate((44, 30, 44, 30)):
        if kind == "justify":
            length = 44
        y = 14 + index * 12
        if kind == "left":
            x = 10
        elif kind == "right":
            x = 54 - length
        else:
            x = 32 - length / 2
        painter.drawLine(QPointF(x, y), QPointF(x + length, y))
    painter.end()
    return QIcon(pixmap)


def band_position(kind: str) -> QIcon:
    """Lage auf dem Band: top, middle, bottom."""
    pixmap, painter = _canvas()
    painter.setPen(QPen(QColor("#9aa3b0"), 3))
    painter.drawLine(QPointF(8, 8), QPointF(56, 8))
    painter.drawLine(QPointF(8, 56), QPointF(56, 56))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ACCENT)
    y = {"top": 14, "middle": 25, "bottom": 36}[kind]
    painter.drawRoundedRect(QRectF(16, y, 32, 14), 3, 3)
    painter.end()
    return QIcon(pixmap)

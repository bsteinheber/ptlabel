"""Etikett als Grafikszene: Text- und Bildobjekte, Serialisierung und Rendern.

Koordinaten der Szene sind Druckerpixel (180 dpi). Die Bandhöhe läuft von y=0 bis
y=tape_px, das Etikett beginnt bei x=0. Schriftgrößen in pt beziehen sich ebenfalls
auf 180 dpi und entsprechen damit der echten Größe auf dem Band.
"""

from __future__ import annotations

import base64
import logging
import math

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from ptlabel import printer

log = logging.getLogger(__name__)

FORMAT_VERSION = 1
DPI = printer.DPI
DEFAULT_MARGIN_MM = 2.0
MIN_LENGTH_MM = 10.0
SYMBOL_FONT = "DejaVu Sans"


def mm_to_px(mm: float) -> float:
    return mm * DPI / 25.4


def px_to_mm(px: float) -> float:
    return px * 25.4 / DPI


_layout_device: QImage | None = None


def layout_device() -> QImage:
    """Zeichenfläche mit 180 dpi, damit pt-Angaben im Text der Druckgröße entsprechen."""
    global _layout_device
    if _layout_device is None:
        _layout_device = QImage(1, 1, QImage.Format.Format_RGB32)
        dpm = round(DPI / 0.0254)
        _layout_device.setDotsPerMeterX(dpm)
        _layout_device.setDotsPerMeterY(dpm)
    return _layout_device


def default_family() -> str:
    families = QFontDatabase.families()
    for name in ("Liberation Sans", "DejaVu Sans", "Arial", "Helvetica"):
        if name in families:
            return name
    return QFont().family()


def fitting_point_size(tape_px: int, lines: int = 1) -> float:
    """Schriftgröße, bei der ``lines`` Zeilen gerade aufs Band passen (auf 0,5 pt gerundet)."""
    probe = TextItem()
    probe.setPlainText("Ag")
    font = QFont(default_family())
    size = 4.0
    while size < 200:
        font.setPointSizeF(size + 0.5)
        probe.document().setDefaultFont(font)
        probe.fit_width()
        if probe.document().size().height() * lines > tape_px * 0.9:
            break
        size += 0.5
    return size


def image_to_base64(image: QImage) -> str:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return base64.b64encode(bytes(data)).decode("ascii")


def image_from_base64(text: str) -> QImage:
    image = QImage()
    image.loadFromData(base64.b64decode(text), "PNG")
    return image


def prepare_image(image: QImage, max_height: int = 512) -> QImage:
    """Transparenz auf Weiß setzen, in Graustufen wandeln und zu große Bilder verkleinern."""
    if image.height() > max_height:
        image = image.scaledToHeight(max_height, Qt.TransformationMode.SmoothTransformation)
    flat = QImage(image.size(), QImage.Format.Format_RGB32)
    flat.fill(QColor("white"))
    painter = QPainter(flat)
    painter.drawImage(0, 0, image)
    painter.end()
    return flat.convertToFormat(QImage.Format.Format_Grayscale8)


class TextItem(QGraphicsTextItem):
    """Text mit Formatierung, direkt im Etikett bearbeitbar.

    Ein Klick setzt den Cursor an die angeklickte Stelle, Ziehen verschiebt den Text.
    Kommt beim Tippen eine Zeile hinzu und passt der Text nicht mehr aufs Band, wird die
    Schrift gleichmäßig verkleinert.
    """

    def __init__(self, html: str | None = None) -> None:
        super().__init__()
        doc = self.document()
        doc.setDocumentMargin(0)
        doc.documentLayout().setPaintDevice(layout_device())
        doc.setDefaultFont(QFont(default_family(), 12))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self._fitting = False
        self._shrinking = False
        self._dragged = False
        doc.contentsChanged.connect(self.fit_width)
        doc.contentsChanged.connect(self._lines_changed)
        if html is not None:
            self.setHtml(html)
        self._line_count = doc.blockCount()

    # Die Breite folgt dem Inhalt, damit Zentriert/Rechtsbündig bei mehreren Zeilen wirkt.
    def fit_width(self) -> None:
        if self._fitting:
            return
        self._fitting = True
        try:
            self.setTextWidth(-1)
            self.setTextWidth(self.document().idealWidth())
        finally:
            self._fitting = False

    def _lines_changed(self) -> None:
        if self._shrinking:
            return
        count = self.document().blockCount()
        added = count > getattr(self, "_line_count", count)
        self._line_count = count
        scene = self.scene()
        if not added or not isinstance(scene, LabelScene):
            return
        self._shrinking = True
        try:
            if self.fit_to_height(scene.tape_px):
                self.setY((scene.tape_px - self.boundingRect().height()) / 2)
        finally:
            self._shrinking = False

    def fit_to_height(self, height: float) -> bool:
        """Verkleinert alle Schriftgrößen gleichmäßig, bis der Text in ``height`` passt."""
        doc = self.document()
        changed = False
        for _ in range(60):
            if doc.size().height() <= height:
                break
            if not self._scale_font_sizes(0.95):
                break  # kleiner geht es nicht
            changed = True
        return changed

    def _scale_font_sizes(self, factor: float) -> bool:
        """Multipliziert jede Schriftgröße mit ``factor`` (abgerundet auf 0,5 pt, min. 4 pt)."""
        doc = self.document()
        default = doc.defaultFont().pointSizeF()
        changed = False

        def smaller(size: float) -> float:
            nonlocal changed
            new = max(4.0, math.floor(size * factor * 2) / 2)
            changed |= new < size
            return new

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        block = doc.begin()
        while block.isValid():
            fmt = QTextCharFormat()
            # Blockformat bestimmt die Höhe leerer Zeilen (z. B. direkt nach Enter)
            fmt.setFontPointSize(smaller(block.charFormat().fontPointSize() or default))
            cursor.setPosition(block.position())
            cursor.mergeBlockCharFormat(fmt)
            for pos in range(block.position(), block.position() + block.length() - 1):
                cursor.setPosition(pos)
                cursor.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setFontPointSize(smaller(cursor.charFormat().fontPointSize() or default))
                cursor.mergeCharFormat(fmt)
            block = block.next()
        cursor.endEditBlock()
        return changed

    @property
    def editing(self) -> bool:
        return self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction

    def start_editing(self, select_all: bool = False) -> None:
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setSelected(True)
        # Tastatureingaben landen nur im Text, wenn auch die Ansicht den Fokus hat
        if self.scene() is not None:
            for view in self.scene().views():
                view.setFocus(Qt.FocusReason.MouseFocusReason)
        # Hatte der Text den Fokus schon (beim Klick bekommt er ihn vor dem Bearbeitbar-
        # Werden), den Fokus neu setzen: Erst ein frisches FocusIn schaltet den Cursor ein.
        if self.hasFocus():
            self.clearFocus()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        log.debug("Text: Bearbeitung gestartet (Fokus: %s)", self.hasFocus())
        if select_all:
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            self.setTextCursor(cursor)
        self._notify()

    def stop_editing(self) -> None:
        if not self.editing:
            return
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.clearFocus()
        if not self.document().toPlainText().strip() and self.scene() is not None:
            # leere Texte verschwinden, aber nicht mitten in itemChange
            QTimer.singleShot(0, lambda: self.scene() and self.scene().removeItem(self))

    def mouseDoubleClickEvent(self, event) -> None:
        if not self.editing:
            self.start_editing()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        self._dragged = False
        log.debug("Text: Maustaste %s gedrückt bei %s (Bearbeitung: %s, Modifikatoren: %s)",
                  event.button(), event.pos(), self.editing, event.modifiers())
        super().mousePressEvent(event)
        if (self.editing and event.button() == Qt.MouseButton.LeftButton
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            # Cursor ausdrücklich an die Klickstelle setzen (Umschalt erweitert die Auswahl)
            self._place_cursor(event.pos())

    def _place_cursor(self, pos: QPointF) -> None:
        position = self.document().documentLayout().hitTest(pos, Qt.HitTestAccuracy.FuzzyHit)
        cursor = self.textCursor()
        cursor.setPosition(max(0, position))
        self.setTextCursor(cursor)
        log.debug("Text: Cursor an Position %s gesetzt", self.textCursor().position())

    def mouseMoveEvent(self, event) -> None:
        if not self.editing and not self._dragged:
            moved = event.screenPos() - event.buttonDownScreenPos(Qt.MouseButton.LeftButton)
            if moved.manhattanLength() < QApplication.startDragDistance():
                return  # leichtes Zittern beim Klicken verschiebt den Text nicht
            self._dragged = True
            log.debug("Text: wird verschoben")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        was_editing = self.editing
        super().mouseReleaseEvent(event)
        plain_click = (
            event.button() == Qt.MouseButton.LeftButton
            and not self._dragged
            # Strg/Umschalt wählen mehrere Objekte aus
            and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                         | Qt.KeyboardModifier.ShiftModifier)
        )
        log.debug("Text: Maustaste losgelassen bei %s (einfacher Klick: %s, war in Bearbeitung: %s)",
                  event.pos(), plain_click, was_editing)
        if not was_editing and plain_click:
            self.start_editing()
            self._place_cursor(event.pos())
        log.debug("Text: nach dem Klick Cursor %s, Markierung ab %s",
                  self.textCursor().position(), self.textCursor().anchor())
        self._dragged = False
        self._notify()

    def keyReleaseEvent(self, event) -> None:
        super().keyReleaseEvent(event)
        self._notify()

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged
                and not value):
            self.stop_editing()
        return super().itemChange(change, value)

    def _notify(self) -> None:
        scene = self.scene()
        if isinstance(scene, LabelScene):
            scene.formatChanged.emit()

    def to_dict(self) -> dict:
        return {"type": "text", "x": self.x(), "y": self.y(), "z": self.zValue(),
                "html": self.toHtml()}


class ImageItem(QGraphicsPixmapItem):
    """Bild (Graustufen); die Größe wird über die Skalierung eingestellt."""

    def __init__(self, image: QImage) -> None:
        super().__init__(QPixmap.fromImage(image))
        self.image = image
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    def set_height_px(self, height: float) -> None:
        if self.image.height():
            self.setScale(height / self.image.height())

    def height_px(self) -> float:
        return self.image.height() * self.scale()

    def to_dict(self) -> dict:
        return {"type": "image", "x": self.x(), "y": self.y(), "z": self.zValue(),
                "scale": self.scale(), "png": image_to_base64(self.image)}


class LabelScene(QGraphicsScene):
    """Ein Etikett. Zeichnet Band, Etikettenfläche und Ränder als Hintergrund."""

    formatChanged = Signal()  # Cursor/Auswahl im Text geändert → Seitenleiste aktualisieren
    geometryChanged = Signal()  # Etikettenlänge kann sich geändert haben

    def __init__(self, tape: str = "12 mm") -> None:
        super().__init__()
        self.tape = tape
        self.margin_mm = DEFAULT_MARGIN_MM
        self.fixed_length_mm: float | None = None
        self.tape_color = "#ffffff"
        self._rendering = False
        self._last_width = -1.0
        self.changed.connect(self._on_changed)
        self._update_scene_rect()

    # --- Geometrie -----------------------------------------------------------------------
    @property
    def tape_px(self) -> int:
        return printer.TAPE_HEIGHT_PX.get(self.tape, 76)

    @property
    def margin_px(self) -> float:
        return mm_to_px(self.margin_mm)

    def content_items(self) -> list[QGraphicsItem]:
        return [i for i in self.items() if isinstance(i, (TextItem, ImageItem))]

    def content_right(self) -> float:
        items = self.content_items()
        return max((i.sceneBoundingRect().right() for i in items), default=0.0)

    def label_width_px(self) -> int:
        if self.fixed_length_mm:
            return round(mm_to_px(self.fixed_length_mm))
        width = self.content_right() + self.margin_px
        return round(max(width, mm_to_px(MIN_LENGTH_MM)))

    def label_rect(self) -> QRectF:
        return QRectF(0, 0, self.label_width_px(), self.tape_px)

    def set_tape(self, tape: str) -> None:
        self.tape = tape
        self._refresh()

    def set_margin(self, mm: float) -> None:
        self.margin_mm = mm
        self._refresh()

    def set_fixed_length(self, mm: float | None) -> None:
        self.fixed_length_mm = mm
        self._refresh()

    def set_tape_color(self, color: str) -> None:
        self.tape_color = color
        self._refresh()

    def _refresh(self) -> None:
        self._update_scene_rect()
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)
        self.geometryChanged.emit()

    def _on_changed(self, _regions=None) -> None:
        width = self.label_width_px()
        if width != self._last_width:
            self._last_width = width
            self._refresh()

    def _update_scene_rect(self) -> None:
        pad = 60
        width = max(self.label_width_px(), self.content_right()) + 400
        self.setSceneRect(QRectF(-pad, -pad, width + pad, self.tape_px + 2 * pad))

    def next_free_x(self) -> float:
        items = self.content_items()
        if not items:
            return self.margin_px
        return self.content_right() + mm_to_px(2)

    # --- Objekte -------------------------------------------------------------------------
    def add_text(self, text: str = "Text", point_size: float | None = None,
                 family: str | None = None) -> TextItem:
        item = TextItem()
        item.setPlainText(text)
        fmt = QTextCharFormat()
        fmt.setFontFamilies([family or default_family()])
        fmt.setFontPointSize(point_size or fitting_point_size(self.tape_px))
        cursor = QTextCursor(item.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeCharFormat(fmt)
        item.setZValue(len(self.content_items()))
        item.setPos(self.next_free_x(), (self.tape_px - item.boundingRect().height()) / 2)
        self.addItem(item)
        return item

    def add_image(self, image: QImage) -> ImageItem:
        item = ImageItem(prepare_image(image))
        item.set_height_px(self.tape_px - 2 * min(self.margin_px, self.tape_px * 0.05))
        item.setZValue(len(self.content_items()))
        item.setPos(self.next_free_x(), (self.tape_px - item.height_px()) / 2)
        self.addItem(item)
        return item

    # --- Hintergrund ---------------------------------------------------------------------
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        if self._rendering:
            painter.fillRect(rect, self._render_background)
            return
        painter.fillRect(rect, QColor("#e6e8ec"))
        label = self.label_rect()
        tape = QRectF(rect.left(), 0, rect.width(), self.tape_px)
        painter.fillRect(tape, QColor("#f7f7f7"))
        painter.fillRect(label, QColor(self.tape_color))
        painter.setPen(QPen(QColor("#9aa3b0"), 0))
        painter.drawRect(label)
        if self.margin_px > 0:
            pen = QPen(QColor("#7aa7e0"), 0, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(self.margin_px, 0), QPointF(self.margin_px, self.tape_px))
            right = label.right() - self.margin_px
            painter.drawLine(QPointF(right, 0), QPointF(right, self.tape_px))

    # --- Rendern -------------------------------------------------------------------------
    def render_image(self, for_print: bool = True) -> QImage:
        """Rendert das Etikett in Druckerpixeln.

        Für den Druck wird Text hart auf Schwarz/Weiß gesetzt (scharfe Kanten) und
        Bilder werden gerastert (Graustufen bleiben erkennbar).
        """
        copy = LabelScene.from_dict(self.to_dict())
        rect = copy.label_rect()
        if not for_print:
            return copy._render(rect, QColor(self.tape_color), antialias=True)

        texts = [i for i in copy.content_items() if isinstance(i, TextItem)]
        images = [i for i in copy.content_items() if isinstance(i, ImageItem)]
        for item in images:
            item.setVisible(False)
        text_layer = copy._render(rect, QColor("white"), antialias=True)
        text_layer = text_layer.convertToFormat(
            QImage.Format.Format_Mono,
            Qt.ImageConversionFlag.MonoOnly | Qt.ImageConversionFlag.ThresholdDither,
        ).convertToFormat(QImage.Format.Format_RGB32)
        if not images:
            return text_layer
        for item in texts:
            item.setVisible(False)
        for item in images:
            item.setVisible(True)
        image_layer = copy._render(rect, QColor("white"), antialias=True).convertToFormat(
            QImage.Format.Format_Mono, Qt.ImageConversionFlag.MonoOnly
            | Qt.ImageConversionFlag.DiffuseDither,
        )
        painter = QPainter(text_layer)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Darken)
        painter.drawImage(0, 0, image_layer)
        painter.end()
        return text_layer

    def _render(self, rect: QRectF, background: QColor, antialias: bool) -> QImage:
        image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_RGB32)
        image.fill(background)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, antialias)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, antialias)
        self._rendering = True
        self._render_background = background
        try:
            self.render(painter, QRectF(image.rect()), rect)
        finally:
            self._rendering = False
            painter.end()
        return image

    # --- Speichern / Laden ---------------------------------------------------------------
    def to_dict(self) -> dict:
        items = sorted(self.content_items(), key=lambda i: i.zValue())
        return {
            "format": FORMAT_VERSION,
            "tape": self.tape,
            "tape_color": self.tape_color,
            "margin_mm": self.margin_mm,
            "fixed_length_mm": self.fixed_length_mm,
            "items": [i.to_dict() for i in items],
        }

    @classmethod
    def from_dict(cls, data: dict) -> LabelScene:
        scene = cls(data.get("tape", "12 mm"))
        scene.margin_mm = float(data.get("margin_mm", DEFAULT_MARGIN_MM))
        scene.fixed_length_mm = data.get("fixed_length_mm") or None
        scene.tape_color = data.get("tape_color", "#ffffff")
        for entry in data.get("items", []):
            if entry.get("type") == "text":
                item = TextItem(entry.get("html", ""))
            elif entry.get("type") == "image":
                item = ImageItem(image_from_base64(entry.get("png", "")))
                item.setScale(float(entry.get("scale", 1.0)))
            else:
                continue
            item.setZValue(float(entry.get("z", 0)))
            item.setPos(float(entry.get("x", 0)), float(entry.get("y", 0)))
            scene.addItem(item)
        scene._refresh()
        return scene

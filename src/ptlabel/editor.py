"""Editor für ein Etikett: Druckereinstellungen links, Etikett in der Mitte, Format rechts."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QFont,
    QImage,
    QImageReader,
    QKeySequence,
    QPainter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from ptlabel import icons, printer, storage
from ptlabel.document import (
    ImageItem,
    LabelScene,
    TextItem,
    mm_to_px,
    px_to_mm,
)
from ptlabel.symbols import SymbolDialog

log = logging.getLogger(__name__)

ZOOM_STEPS = [50, 75, 100, 150, 200, 300, 400, 500, 600, 800, 1000]
SIZE_STEPS = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 42, 48, 56, 64, 72]


@contextmanager
def blocked(*widgets):
    old = [w.blockSignals(True) for w in widgets]
    try:
        yield
    finally:
        for widget, state in zip(widgets, old):
            widget.blockSignals(state)


def section(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    return box, layout


class LabelView(QGraphicsView):
    """Zeichenfläche mit Zoom; Entf löscht, Pfeiltasten verschieben, Enter bearbeitet."""

    deleteRequested = Signal()
    zoomChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.zoom = 300

    def set_zoom(self, percent: int) -> None:
        self.zoom = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], percent))
        # 100 % = Originalgröße auf dem Bildschirm
        scale = self.zoom / 100 * self.logicalDpiX() / printer.DPI
        self.resetTransform()
        self.scale(scale, scale)
        self.zoomChanged.emit(self.zoom)

    def zoom_step(self, direction: int) -> None:
        if direction > 0:
            steps = [z for z in ZOOM_STEPS if z > self.zoom]
            self.set_zoom(steps[0] if steps else self.zoom)
        else:
            steps = [z for z in ZOOM_STEPS if z < self.zoom]
            self.set_zoom(steps[-1] if steps else self.zoom)

    def zoom_to_fit(self, tape_px: int, label_width_px: float) -> None:
        """Größte Zoomstufe bis 400 %, bei der das ganze Etikett sichtbar ist und das Band
        höchstens ein Drittel der Höhe einnimmt; danach steht der linke Etikettenrand im Bild."""
        best = ZOOM_STEPS[0]
        height_limit = self.viewport().height() / 3
        width_limit = self.viewport().width() - 80  # etwas Luft links und rechts
        for step in (z for z in ZOOM_STEPS if z <= 400):
            scale = step / 100 * self.logicalDpiX() / printer.DPI
            if tape_px * scale <= height_limit and label_width_px * scale <= width_limit:
                best = step
        self.set_zoom(best)
        self.show_label_start()

    def show_label_start(self) -> None:
        """Scrollt so, dass das Etikett am linken Rand der Ansicht beginnt."""
        bar = self.horizontalScrollBar()
        bar.setValue(bar.minimum())

    def mousePressEvent(self, event) -> None:
        # Ein Klick ins Etikett holt die Tastatur zurück, z. B. nach dem Größenfeld rechts
        log.debug("Ansicht: Mausklick bei %s, Fokus vorher: %s, Objekt dort: %s",
                  event.position(), self.hasFocus(),
                  type(self.itemAt(event.position().toPoint())).__name__)
        if not self.hasFocus():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_step(1 if event.angleDelta().y() > 0 else -1)
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        scene = self.scene()
        focus = scene.focusItem() if scene else None
        if isinstance(focus, TextItem) and focus.editing:
            if event.key() == Qt.Key.Key_Escape:
                focus.stop_editing()
                focus.setSelected(True)
                return
            super().keyPressEvent(event)
            return
        selected = scene.selectedItems() if scene else []
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and selected:
            self.deleteRequested.emit()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2) and len(selected) == 1 \
                and isinstance(selected[0], TextItem):
            selected[0].start_editing()
            return
        moves = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                 Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if key in moves and selected:
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx, dy = moves[key]
            for item in selected:
                item.moveBy(dx * step, dy * step)
            return
        super().keyPressEvent(event)


class EditorPage(QWidget):
    homeRequested = Signal()
    titleChanged = Signal(str)
    message = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.path: Path | None = None
        self.name = ""
        self.saved_state: dict = {}
        self.scene: LabelScene | None = None  # wird unten mit _set_scene gesetzt

        self.view = LabelView()
        self.view.deleteRequested.connect(self.delete_selected)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())

        splitter = QSplitter()
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 800, 290])
        layout.addWidget(splitter, 1)

        self._set_scene(LabelScene())

    # --- Aufbau --------------------------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        bar = QToolBar()
        bar.setIconSize(QSize(32, 32))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        bar.setMovable(False)

        def action(icon, text, slot, shortcut=None, tip=None) -> QAction:
            act = QAction(icon, text, self)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(shortcut)
                act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            act.setToolTip(tip or text)
            bar.addAction(act)
            return act

        action(icons.home(), "Startseite", self.homeRequested.emit)
        action(icons.save(), "Speichern", self.save, QKeySequence.StandardKey.Save)
        self.save_as_action = QAction("Speichern unter…", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_as)
        self.addAction(self.save_as_action)
        action(icons.printer(), "Drucken", self.print_label, QKeySequence.StandardKey.Print)
        self.delete_action = action(icons.delete(), "Löschen", self.delete_selected)

        # deutlicher Abstand zwischen Aktionen und den Objekten zum Einfügen
        gap = QWidget()
        gap.setFixedWidth(64)
        bar.addWidget(gap)
        bar.addSeparator()
        gap = QWidget()
        gap.setFixedWidth(16)
        bar.addWidget(gap)

        action(icons.text(), "Text", self.insert_text, "Ctrl+T", "Text einfügen (Strg+T)")
        action(icons.glyph("☺"), "Symbol", self.insert_symbol, None, "Symbol einfügen")
        action(icons.image(), "Bild", self.insert_image, None, "Bild einfügen")
        return bar

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        box, inner = section("Drucker")
        inner.addWidget(QLabel(f"<b>{printer.PRINTER_NAME}</b>"))
        connection = printer.load_connection()
        self.connection_combo = QComboBox()
        self.connection_combo.addItem("WLAN", "wlan")
        self.connection_combo.addItem("USB", "usb")
        self.connection_combo.setCurrentIndex(0 if connection.kind == "wlan" else 1)
        self.host_edit = QLineEdit(connection.host)
        self.host_edit.setPlaceholderText("IP-Adresse oder Name")
        self.host_edit.setToolTip("Adresse des Druckers im WLAN")
        self.host_edit.setEnabled(connection.kind == "wlan")
        self.connection_combo.currentIndexChanged.connect(self._connection_changed)
        self.host_edit.editingFinished.connect(self._connection_changed)
        inner.addWidget(self.connection_combo)
        inner.addWidget(self.host_edit)
        layout.addWidget(box)

        box, inner = section("Druckmedium")
        self.tape_combo = QComboBox()
        self.tape_combo.addItems(printer.TAPE_HEIGHT_PX.keys())
        self.tape_combo.currentTextChanged.connect(self._tape_changed)
        inner.addWidget(self.tape_combo)
        check = QPushButton("Medium prüfen")
        check.clicked.connect(lambda: self.check_media())
        inner.addWidget(check)
        self.media_label = QLabel("Noch nicht geprüft")
        self.media_label.setWordWrap(True)
        self.media_label.setStyleSheet("color:#555;")
        inner.addWidget(self.media_label)
        layout.addWidget(box)

        box, inner = section("Länge")
        self.length_spin = QDoubleSpinBox(suffix=" mm", decimals=1, minimum=5, maximum=1000)
        self.length_spin.valueChanged.connect(self._length_changed)
        self.fixed_check = QCheckBox("Feste Länge")
        self.fixed_check.toggled.connect(self._fixed_toggled)
        inner.addWidget(self.length_spin)
        inner.addWidget(self.fixed_check)
        layout.addWidget(box)

        box, inner = section("Ränder")
        self.margin_spin = QDoubleSpinBox(suffix=" mm", decimals=1, minimum=0, maximum=30,
                                          singleStep=0.5)
        self.margin_spin.valueChanged.connect(lambda v: self.scene.set_margin(v))
        inner.addWidget(self.margin_spin)
        layout.addWidget(box)

        box, inner = section("Kopien")
        self.copies_spin = QSpinBox(minimum=1, maximum=99)
        inner.addWidget(self.copies_spin)
        layout.addWidget(box)

        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(220)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        return scroll

    def _build_center(self) -> QWidget:
        center = QWidget()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(8, 4, 8, 4)
        hint = QLabel("Klick in einen Text zum Bearbeiten · Ziehen oder Pfeiltasten verschieben · "
                      "Esc beendet · Strg+Mausrad zoomt")
        hint.setStyleSheet("color:#777;")
        bottom.addWidget(hint, 1)
        minus = QToolButton(text="−")
        plus = QToolButton(text="+")
        self.zoom_label = QLabel("300 %")
        self.zoom_label.setMinimumWidth(56)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        minus.clicked.connect(lambda: self.view.zoom_step(-1))
        plus.clicked.connect(lambda: self.view.zoom_step(1))
        self.view.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{z} %"))
        for widget in (minus, self.zoom_label, plus):
            bottom.addWidget(widget)
        layout.addLayout(bottom)
        return center

    def _build_right_panel(self) -> QWidget:
        self.right_stack = QStackedWidget()
        self.right_stack.setMinimumWidth(260)

        empty = QLabel("<p style='font-size:15px'>Kein Objekt ausgewählt</p>"
                       "<p>Texte, Symbole oder Bilder hinzufügen</p>")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("color:#555;")
        self.right_stack.addWidget(empty)

        self.format_tabs = QTabWidget()
        self.format_tabs.addTab(self._build_text_tab(), "Text")
        self.format_tabs.addTab(self._build_layout_tab(), "Layout")
        self.right_stack.addWidget(self.format_tabs)
        return self.right_stack

    def _build_text_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        box, inner = section("Schriftart")
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self._family_changed)
        inner.addWidget(self.font_combo)

        row = QHBoxLayout()
        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.addItems([str(s) for s in SIZE_STEPS])
        self.size_combo.setToolTip("Schriftgröße in pt (Originalgröße auf dem Band)")
        self.size_combo.activated.connect(lambda _i: self._size_entered())
        self.size_combo.lineEdit().editingFinished.connect(self._size_entered)
        grow = QToolButton(text="A+", toolTip="Schrift vergrößern")
        shrink = QToolButton(text="A−", toolTip="Schrift verkleinern")
        grow.clicked.connect(lambda: self._size_step(1))
        shrink.clicked.connect(lambda: self._size_step(-1))
        row.addWidget(self.size_combo, 1)
        row.addWidget(QLabel("pt"))
        row.addWidget(grow)
        row.addWidget(shrink)
        inner.addLayout(row)

        row = QHBoxLayout()
        self.bold_btn = self._style_button("F", "Fett (Strg+B)", "bold")
        self.italic_btn = self._style_button("K", "Kursiv (Strg+I)", "italic")
        self.underline_btn = self._style_button("U", "Unterstrichen (Strg+U)", "underline")
        self.bold_btn.setShortcut("Ctrl+B")
        self.italic_btn.setShortcut("Ctrl+I")
        self.underline_btn.setShortcut("Ctrl+U")
        for btn in (self.bold_btn, self.italic_btn, self.underline_btn):
            row.addWidget(btn)
        row.addStretch()
        inner.addLayout(row)
        layout.addWidget(box)

        box, inner = section("Textausrichtung")
        row = QHBoxLayout()
        self.align_group = QButtonGroup(self)
        aligns = [("left", Qt.AlignmentFlag.AlignLeft, "Linksbündig"),
                  ("center", Qt.AlignmentFlag.AlignHCenter, "Zentriert"),
                  ("right", Qt.AlignmentFlag.AlignRight, "Rechtsbündig"),
                  ("justify", Qt.AlignmentFlag.AlignJustify, "Blocksatz")]
        for kind, flag, tip in aligns:
            btn = QToolButton(icon=icons.align(kind), toolTip=tip, checkable=True)
            btn.setIconSize(QSize(24, 24))
            self.align_group.addButton(btn, int(flag.value))
            row.addWidget(btn)
        row.addStretch()
        self.align_group.idClicked.connect(self._align_clicked)
        inner.addLayout(row)
        layout.addWidget(box)

        layout.addWidget(self._band_position_box())
        layout.addStretch()
        return tab

    def _band_position_box(self) -> QGroupBox:
        box, inner = section("Lage auf dem Band")
        row = QHBoxLayout()
        for kind, tip in (("top", "Oben"), ("middle", "Mittig"), ("bottom", "Unten")):
            btn = QToolButton(icon=icons.band_position(kind), toolTip=tip)
            btn.setIconSize(QSize(24, 24))
            btn.clicked.connect(lambda _=False, k=kind: self._place_vertically(k))
            row.addWidget(btn)
        row.addStretch()
        inner.addLayout(row)
        return box

    def _build_layout_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        box = QGroupBox("Position und Größe")
        form = QFormLayout(box)
        self.x_spin = QDoubleSpinBox(suffix=" mm", decimals=1, minimum=-100, maximum=1000)
        self.y_spin = QDoubleSpinBox(suffix=" mm", decimals=1, minimum=-50, maximum=50)
        self.h_spin = QDoubleSpinBox(suffix=" mm", decimals=1, minimum=0.5, maximum=50,
                                     singleStep=0.5)
        self.h_spin.setToolTip("Höhe (bei Texten über die Schriftgröße einstellen)")
        self.x_spin.valueChanged.connect(lambda v: self._move_selected(x=mm_to_px(v)))
        self.y_spin.valueChanged.connect(lambda v: self._move_selected(y=mm_to_px(v)))
        self.h_spin.valueChanged.connect(self._height_changed)
        form.addRow("Links:", self.x_spin)
        form.addRow("Oben:", self.y_spin)
        form.addRow("Höhe:", self.h_spin)
        layout.addWidget(box)

        layout.addWidget(self._band_position_box())

        box, inner = section("Anordnung")
        center_h = QPushButton("Auf dem Etikett zentrieren")
        center_h.clicked.connect(self._center_horizontally)
        front = QPushButton("In den Vordergrund")
        back = QPushButton("In den Hintergrund")
        front.clicked.connect(lambda: self._restack(1))
        back.clicked.connect(lambda: self._restack(-1))
        for btn in (center_h, front, back):
            inner.addWidget(btn)
        layout.addWidget(box)
        layout.addStretch()
        return tab

    def _style_button(self, text: str, tip: str, kind: str) -> QToolButton:
        btn = QToolButton(text=text, toolTip=tip, checkable=True)
        font = QFont(btn.font())
        font.setPointSize(font.pointSize() + 3)
        font.setBold(kind == "bold")
        font.setItalic(kind == "italic")
        font.setUnderline(kind == "underline")
        btn.setFont(font)
        btn.setMinimumSize(QSize(34, 34))
        btn.clicked.connect(lambda checked: self._style_clicked(kind, checked))
        return btn

    # --- Szene / Dokument ----------------------------------------------------------------
    def _set_scene(self, scene: LabelScene) -> None:
        old = self.scene
        self.scene = scene
        self.view.setScene(scene)
        for signal, slot in self._scene_connections(scene):
            signal.connect(slot)
        if old is not None and old is not scene and isValid(old):
            for signal, slot in self._scene_connections(old):
                signal.disconnect(slot)
            old.deleteLater()
        with blocked(self.tape_combo, self.margin_spin, self.fixed_check, self.length_spin):
            self.tape_combo.setCurrentText(scene.tape)
            self.margin_spin.setValue(scene.margin_mm)
            self.fixed_check.setChecked(bool(scene.fixed_length_mm))
        self._sync_label_settings()
        self._sync_panel()
        QTimer.singleShot(0, self._fit_view)

    def _scene_connections(self, scene: LabelScene) -> list:
        return [(scene.selectionChanged, self._sync_panel),
                (scene.formatChanged, self._sync_panel),
                (scene.changed, self._sync_geometry),
                (scene.geometryChanged, self._sync_label_settings)]

    def _fit_view(self) -> None:
        self.view.zoom_to_fit(self.scene.tape_px, self.scene.label_width_px())

    def new_label(self, tape: str, tape_color: str = "#ffffff") -> None:
        scene = LabelScene(tape)
        scene.set_tape_color(tape_color)
        self.path = None
        self.name = ""
        self.copies_spin.setValue(1)
        self._set_scene(scene)
        self.saved_state = scene.to_dict()
        self._emit_title()
        QTimer.singleShot(0, self.insert_text)

    def open_label(self, path: Path) -> bool:
        try:
            label = storage.load(path)
        except (OSError, ValueError) as err:
            QMessageBox.warning(self, "Öffnen", f"Konnte {path} nicht öffnen:\n{err}")
            return False
        self.path = Path(path)
        self.name = label.name
        self.copies_spin.setValue(1)
        self._set_scene(LabelScene.from_dict(label.label))
        self.saved_state = self.scene.to_dict()
        storage.touch(self.path)
        self._emit_title()
        return True

    def is_dirty(self) -> bool:
        return self.scene.to_dict() != self.saved_state

    def maybe_save(self) -> bool:
        """Fragt bei ungespeicherten Änderungen nach. False = Vorgang abbrechen."""
        if not self.is_dirty():
            return True
        answer = QMessageBox.question(
            self, "Ungespeicherte Änderungen",
            "Das Etikett wurde geändert. Änderungen speichern?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def suggested_name(self) -> str:
        texts = sorted((i for i in self.scene.content_items() if isinstance(i, TextItem)),
                       key=lambda i: (i.x(), i.y()))
        for item in texts:
            for line in item.toPlainText().splitlines():
                if line.strip():
                    return line.strip()
        return "Etikett"

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        self._write(self.path, self.name)
        return True

    def save_as(self) -> bool:
        name, ok = QInputDialog.getText(self, "Etikett speichern", "Name des Etiketts:",
                                        text=self.name or self.suggested_name())
        if not ok or not name.strip():
            return False
        self._write(storage.new_path(name.strip()), name.strip())
        return True

    def _write(self, path: Path, name: str, printed: bool = False) -> None:
        state = self.scene.to_dict()
        try:
            storage.save(path, name, state, printed=printed)
        except OSError as err:
            QMessageBox.warning(self, "Speichern", f"Konnte nicht speichern:\n{err}")
            return
        self.path, self.name, self.saved_state = path, name, state
        self._emit_title()
        self.message.emit(f"Gespeichert: {path}")

    def _emit_title(self) -> None:
        self.titleChanged.emit(self.name or "Neues Etikett")

    # --- Einfügen / Löschen --------------------------------------------------------------
    def insert_text(self) -> None:
        self.scene.clearSelection()
        item = self.scene.add_text("Text")
        self.view.setFocus()
        item.start_editing(select_all=True)
        self.view.ensureVisible(item)

    def insert_symbol(self) -> None:
        editing = self._editing_item()
        dialog = SymbolDialog(self)
        if not dialog.exec() or not dialog.symbol:
            return
        if editing is not None:
            cursor = editing.textCursor()
            fmt = cursor.charFormat()
            fmt.setFontFamilies(["DejaVu Sans"])
            cursor.insertText(dialog.symbol, fmt)
            self.view.setFocus()
            editing.setFocus()
            return
        self.scene.clearSelection()
        item = self.scene.add_text(dialog.symbol, family="DejaVu Sans")
        item.setSelected(True)
        self.view.ensureVisible(item)

    def insert_image(self) -> None:
        formats = " ".join(f"*.{bytes(f).decode()}" for f in QImageReader.supportedImageFormats())
        path, _ = QFileDialog.getOpenFileName(self, "Bild einfügen", str(Path.home()),
                                              f"Bilder ({formats})")
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, "Bild einfügen", "Das Bild konnte nicht geladen werden.")
            return
        self.scene.clearSelection()
        item = self.scene.add_image(image)
        item.setSelected(True)
        self.view.ensureVisible(item)

    def delete_selected(self) -> None:
        editing = self._editing_item()
        if editing is not None:
            return  # beim Tippen löscht Entf Zeichen, nicht das Objekt
        for item in self.scene.selectedItems():
            self.scene.removeItem(item)

    # --- Drucken -------------------------------------------------------------------------
    def check_media(self, switch_tape: bool = True) -> printer.MediaInfo | None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            info = printer.media()
        except printer.PrinterError as err:
            QApplication.restoreOverrideCursor()
            self.media_label.setText("Drucker nicht erreichbar")
            QMessageBox.warning(self, "Medium prüfen", str(err))
            return None
        QApplication.restoreOverrideCursor()
        self.media_label.setText(f"Eingelegt: {info.describe()}")
        if switch_tape and info.tape and info.tape != self.scene.tape:
            self.tape_combo.setCurrentText(info.tape)
        self.scene.set_tape_color(info.tape_color_hex)
        return info

    def print_label(self) -> None:
        editing = self._editing_item()
        if editing is not None:
            editing.stop_editing()
        if not self.scene.content_items():
            QMessageBox.information(self, "Drucken", "Das Etikett ist leer.")
            return
        info = self.check_media(switch_tape=False)
        if info is None:
            return
        if info.problem:
            QMessageBox.warning(self, "Drucken", info.problem)
            return
        if info.tape and info.tape != self.scene.tape:
            QMessageBox.warning(self, "Drucken",
                                f"Eingelegt ist {info.tape}, das Etikett ist für "
                                f"{self.scene.tape} angelegt.\n\nBitte das Band wechseln oder links "
                                f"unter „Druckmedium“ {info.tape} wählen.")
            return
        image = self.scene.render_image()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            printer.print_image(image, self.copies_spin.value(), tape=self.scene.tape,
                                margin_px=round(self.scene.margin_px),
                                margin_mm=self.scene.margin_mm)
        except printer.PrinterError as err:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Druckfehler", str(err))
            return
        QApplication.restoreOverrideCursor()
        # Gedruckte Etiketten landen immer in der Ablage, damit sie unter „Gedruckt“ auftauchen
        if self.path is None:
            name = self.suggested_name()
            self._write(storage.new_path(name), name, printed=True)
        else:
            self._write(self.path, self.name, printed=True)
        self.message.emit(f"Gedruckt ({self.copies_spin.value()}×) und gespeichert: {self.path}")

    # --- Etiketteneinstellungen ----------------------------------------------------------
    def _connection_changed(self, *_args) -> None:
        kind = self.connection_combo.currentData()
        self.host_edit.setEnabled(kind == "wlan")
        printer.save_connection(printer.Connection(kind, self.host_edit.text().strip()
                                                   or printer.DEFAULT_HOST))
        self.media_label.setText("Noch nicht geprüft")

    def _tape_changed(self, tape: str) -> None:
        self.scene.set_tape(tape)
        self._fit_view()

    def _fixed_toggled(self, fixed: bool) -> None:
        self.scene.set_fixed_length(self.length_spin.value() if fixed else None)
        self.length_spin.setEnabled(fixed)

    def _length_changed(self, value: float) -> None:
        if self.fixed_check.isChecked():
            self.scene.set_fixed_length(value)

    def _sync_label_settings(self) -> None:
        if not isValid(self.scene):
            return  # Szene wird gerade beim Beenden abgebaut
        with blocked(self.length_spin):
            self.length_spin.setValue(px_to_mm(self.scene.label_width_px()))
        self.length_spin.setEnabled(self.fixed_check.isChecked())

    # --- Formatieren ---------------------------------------------------------------------
    def _selected_texts(self) -> list[TextItem]:
        return [i for i in self.scene.selectedItems() if isinstance(i, TextItem)]

    def _editing_item(self) -> TextItem | None:
        focus = self.scene.focusItem()
        return focus if isinstance(focus, TextItem) and focus.editing else None

    def _target_cursors(self, item: TextItem) -> QTextCursor:
        """Markierter Text beim Bearbeiten, sonst der ganze Text des Objekts."""
        cursor = item.textCursor()
        if item.editing and cursor.hasSelection():
            return cursor
        whole = QTextCursor(item.document())
        whole.select(QTextCursor.SelectionType.Document)
        return whole

    def _apply_char_format(self, fmt: QTextCharFormat) -> None:
        for item in self._selected_texts():
            center = item.sceneBoundingRect().center().y()
            cursor = self._target_cursors(item)
            cursor.mergeCharFormat(fmt)
            item.setY(item.y() + center - item.sceneBoundingRect().center().y())
        self._sync_panel()

    def _family_changed(self, font: QFont) -> None:
        fmt = QTextCharFormat()
        fmt.setFontFamilies([font.family()])
        self._apply_char_format(fmt)

    def _size_entered(self) -> None:
        try:
            size = float(self.size_combo.currentText().replace(",", "."))
        except ValueError:
            return
        if 2 <= size <= 400:
            fmt = QTextCharFormat()
            fmt.setFontPointSize(size)
            self._apply_char_format(fmt)

    def _size_step(self, direction: int) -> None:
        try:
            current = float(self.size_combo.currentText().replace(",", "."))
        except ValueError:
            current = 12
        if direction > 0:
            size = next((s for s in SIZE_STEPS if s > current), current + 8)
        else:
            size = next((s for s in reversed(SIZE_STEPS) if s < current), max(2, current - 1))
        with blocked(self.size_combo):
            self.size_combo.setCurrentText(f"{size:g}")
        self._size_entered()

    def _style_clicked(self, kind: str, checked: bool) -> None:
        fmt = QTextCharFormat()
        if kind == "bold":
            fmt.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal)
        elif kind == "italic":
            fmt.setFontItalic(checked)
        else:
            fmt.setFontUnderline(checked)
        self._apply_char_format(fmt)

    def _align_clicked(self, flag: int) -> None:
        fmt = QTextBlockFormat()
        fmt.setAlignment(Qt.AlignmentFlag(flag))
        for item in self._selected_texts():
            cursor = item.textCursor() if item.editing else self._target_cursors(item)
            cursor.mergeBlockFormat(fmt)

    def _place_vertically(self, kind: str) -> None:
        tape = self.scene.tape_px
        for item in self.scene.selectedItems():
            height = item.sceneBoundingRect().height()
            item.setY({"top": 0, "middle": (tape - height) / 2, "bottom": tape - height}[kind])

    def _center_horizontally(self) -> None:
        width = self.scene.label_width_px()
        for item in self.scene.selectedItems():
            item.setX((width - item.sceneBoundingRect().width()) / 2)

    def _restack(self, direction: int) -> None:
        items = self.scene.content_items()
        if not items:
            return
        z_values = [i.zValue() for i in items]
        for item in self.scene.selectedItems():
            item.setZValue(max(z_values) + 1 if direction > 0 else min(z_values) - 1)

    def _move_selected(self, x: float | None = None, y: float | None = None) -> None:
        for item in self.scene.selectedItems()[:1]:
            item.setPos(item.x() if x is None else x, item.y() if y is None else y)

    def _height_changed(self, mm: float) -> None:
        for item in self.scene.selectedItems():
            if isinstance(item, ImageItem):
                item.set_height_px(mm_to_px(mm))

    # --- Seitenleiste aktualisieren ------------------------------------------------------
    def _sync_panel(self) -> None:
        if not isValid(self.scene):
            return  # Szene wird gerade beim Beenden abgebaut
        selected = self.scene.selectedItems()
        self.delete_action.setEnabled(bool(selected))
        if not selected:
            self.right_stack.setCurrentIndex(0)
            return
        self.right_stack.setCurrentIndex(1)
        texts = self._selected_texts()
        self.format_tabs.setTabEnabled(0, bool(texts))
        if not texts and self.format_tabs.currentIndex() == 0:
            self.format_tabs.setCurrentIndex(1)
        if texts:
            self._sync_text(texts[0])
        self._sync_geometry()

    def _sync_text(self, item: TextItem) -> None:
        if item.editing:
            fmt = item.textCursor().charFormat()
            block = item.textCursor().blockFormat()
        else:
            cursor = QTextCursor(item.document())
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
            fmt = cursor.charFormat()
            block = cursor.blockFormat()
        default = item.document().defaultFont()
        families = fmt.fontFamilies() or [default.family()]
        size = fmt.fontPointSize() or default.pointSizeF()
        widgets = (self.font_combo, self.size_combo, self.bold_btn, self.italic_btn,
                   self.underline_btn, self.align_group)
        with blocked(*widgets):
            self.font_combo.setCurrentFont(QFont(families[0]))
            self.size_combo.setCurrentText(f"{size:g}".replace(".", ","))
            self.bold_btn.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
            self.italic_btn.setChecked(fmt.fontItalic())
            self.underline_btn.setChecked(fmt.fontUnderline())
            alignment = block.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
            if alignment == Qt.AlignmentFlag.AlignJustify:
                flag = Qt.AlignmentFlag.AlignJustify
            elif alignment & (Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignCenter):
                flag = Qt.AlignmentFlag.AlignHCenter
            elif alignment & Qt.AlignmentFlag.AlignRight:
                flag = Qt.AlignmentFlag.AlignRight
            else:
                flag = Qt.AlignmentFlag.AlignLeft
            button = self.align_group.button(int(flag.value))
            if button:
                button.setChecked(True)

    def _sync_geometry(self, *_args) -> None:
        if not isValid(self.scene):
            return  # Szene wird gerade beim Beenden abgebaut
        selected = self.scene.selectedItems()
        if not selected:
            return
        item = selected[0]
        is_image = isinstance(item, ImageItem)
        with blocked(self.x_spin, self.y_spin, self.h_spin):
            self.x_spin.setValue(px_to_mm(item.x()))
            self.y_spin.setValue(px_to_mm(item.y()))
            self.h_spin.setValue(px_to_mm(item.sceneBoundingRect().height()))
        self.h_spin.setEnabled(is_image)

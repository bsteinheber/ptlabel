"""Startseite: neues Etikett anlegen oder ein gespeichertes Etikett öffnen."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ptlabel import printer, storage
from ptlabel.document import LabelScene

THUMB_SIZE = QSize(420, 80)


def thumbnail(label: dict) -> QPixmap:
    """Vorschau in Originalpixeln, links ausgerichtet auf einheitlicher Fläche."""
    image = LabelScene.from_dict(label).render_image(for_print=False)
    if image.height() > THUMB_SIZE.height() - 4:
        image = image.scaledToHeight(THUMB_SIZE.height() - 4,
                                     Qt.TransformationMode.SmoothTransformation)
    if image.width() > THUMB_SIZE.width() - 4:
        image = image.copy(0, 0, THUMB_SIZE.width() - 4, image.height())
    canvas = QPixmap(THUMB_SIZE)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    y = (THUMB_SIZE.height() - image.height()) // 2
    painter.drawImage(1, y, image)
    painter.setPen(QColor("#6b7280"))
    painter.drawRect(0, y - 1, image.width() + 1, image.height() + 1)
    painter.end()
    return canvas


def tape_sample(tape: str) -> QPixmap:
    """Kleines Bild eines Bandabschnitts in relativer Höhe."""
    height = printer.TAPE_HEIGHT_PX[tape] // 2 + 4
    pixmap = QPixmap(90, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QColor("#6b7280"))
    painter.setBrush(QColor("white"))
    painter.drawRect(4, (72 - height) // 2, 80, height)
    painter.end()
    return pixmap


class StartPage(QWidget):
    newRequested = Signal(str, str)  # Bandbreite, Bandfarbe
    openRequested = Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.tape_color = "#ffffff"
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_new_tab(), "Neues Etikett")
        self.tabs.addTab(self._build_list_tab(), "Erstellte Etiketten")
        self.tabs.setStyleSheet("QTabBar::tab { padding: 10px 28px; font-size: 15px; }")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

    # --- Neues Etikett -------------------------------------------------------------------
    def _build_new_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 16)
        heading = QLabel("Bandbreite wählen")
        heading.setStyleSheet("font-size:20px; font-weight:600;")
        layout.addWidget(heading)

        row = QHBoxLayout()
        self.tape_group = QButtonGroup(self)
        for tape in printer.TAPE_HEIGHT_PX:
            btn = QToolButton(text=tape, checkable=True)
            btn.setIcon(tape_sample(tape))
            btn.setIconSize(QSize(90, 72))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setMinimumSize(QSize(120, 120))
            btn.setStyleSheet("QToolButton:checked { background:#cfdcf5; border:2px solid #1a56c8;"
                              " border-radius:6px; }")
            self.tape_group.addButton(btn)
            row.addWidget(btn)
            if tape == "12 mm":
                btn.setChecked(True)
        row.addStretch()
        layout.addLayout(row)

        check_row = QHBoxLayout()
        check = QPushButton("Medium prüfen")
        check.clicked.connect(self.check_media)
        self.media_label = QLabel("Fragt das eingelegte Band am Drucker ab.")
        self.media_label.setStyleSheet("color:#555;")
        check_row.addWidget(check)
        check_row.addWidget(self.media_label, 1)
        layout.addSpacing(12)
        layout.addLayout(check_row)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        create = QPushButton("Erstellen")
        create.setDefault(True)
        create.clicked.connect(self._create)
        buttons.addWidget(create)
        layout.addLayout(buttons)
        return tab

    def selected_tape(self) -> str:
        button = self.tape_group.checkedButton()
        return button.text() if button else "12 mm"

    def select_tape(self, tape: str) -> None:
        for button in self.tape_group.buttons():
            button.setChecked(button.text() == tape)

    def check_media(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            info = printer.media()
        except printer.PrinterError as err:
            QApplication.restoreOverrideCursor()
            self.media_label.setText("Drucker nicht erreichbar.")
            QMessageBox.warning(self, "Medium prüfen", str(err))
            return
        QApplication.restoreOverrideCursor()
        self.media_label.setText(
            f"Eingelegt: {info.describe()}  ({printer.load_connection().describe()})")
        self.tape_color = info.tape_color_hex
        if info.tape:
            self.select_tape(info.tape)

    def _create(self) -> None:
        self.newRequested.emit(self.selected_tape(), self.tape_color)

    # --- Erstellte Etiketten -------------------------------------------------------------
    def _build_list_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)

        body = QHBoxLayout()
        self.filter_list = QListWidget()
        self.filter_list.addItems(["Zuletzt verwendet", "Gedruckt"])
        self.filter_list.setFixedWidth(200)
        self.filter_list.setStyleSheet(
            "QListWidget { border:none; font-size:15px; }"
            "QListWidget::item { padding:8px; }"
            "QListWidget::item:selected { color:#1a56c8; background:#e8eefb; }")
        self.filter_list.setCurrentRow(0)
        self.filter_list.currentRowChanged.connect(lambda _r: self.refresh())
        body.addWidget(self.filter_list)

        self.label_list = QListWidget()
        self.label_list.setIconSize(THUMB_SIZE)
        self.label_list.setSpacing(4)
        self.label_list.setStyleSheet("QListWidget::item { padding:10px; }")
        self.label_list.itemDoubleClicked.connect(self._open_item)
        self.label_list.currentItemChanged.connect(self._update_buttons)
        body.addWidget(self.label_list, 1)
        outer.addLayout(body, 1)

        self.folder_label = QLabel()
        self.folder_label.setStyleSheet("color:#777;")

        buttons = QHBoxLayout()
        browse = QPushButton("Öffnen…")
        browse.clicked.connect(self._browse)
        folder = QPushButton("Ordner anzeigen")
        folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(storage.labels_dir()))))
        self.delete_button = QPushButton("Löschen")
        self.delete_button.clicked.connect(self._delete)
        self.open_button = QPushButton("Bearbeiten / Drucken")
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(lambda: self._open_item(self.label_list.currentItem()))
        buttons.addWidget(browse)
        buttons.addWidget(folder)
        buttons.addWidget(self.folder_label, 1)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.open_button)
        outer.addLayout(buttons)
        return tab

    def refresh(self) -> None:
        folder = storage.labels_dir()
        self.folder_label.setText(f"  Ablage: {folder}")
        printed_only = self.filter_list.currentRow() == 1
        labels = storage.list_labels(folder)
        if printed_only:
            labels = [f for f in labels if f.last_printed]
            labels.sort(key=lambda f: f.last_printed, reverse=True)

        self.label_list.clear()
        for entry in labels:
            when = entry.last_printed if printed_only else entry.sort_time
            text = f"{entry.name}\n{when:%d.%m.%Y %H:%M} – {entry.tape}"
            if entry.last_printed and not printed_only:
                text += f"  ·  gedruckt {entry.last_printed:%d.%m.%Y}"
            try:
                icon = thumbnail(entry.label)
            except (ValueError, TypeError, KeyError):  # defekte Datei überspringen
                icon = QPixmap()
            item = QListWidgetItem(icon, text)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            item.setToolTip(str(entry.path))
            self.label_list.addItem(item)
        if not labels:
            empty = QListWidgetItem("Noch keine Etiketten gespeichert." if not printed_only
                                    else "Noch nichts gedruckt.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.label_list.addItem(empty)
        else:
            self.label_list.setCurrentRow(0)
        self._update_buttons()

    def show_list(self) -> None:
        self.tabs.setCurrentIndex(1)

    def _current_path(self) -> Path | None:
        item = self.label_list.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return Path(value) if value else None

    def _update_buttons(self, *_args) -> None:
        has = self._current_path() is not None
        self.open_button.setEnabled(has)
        self.delete_button.setEnabled(has)

    def _open_item(self, item: QListWidgetItem | None) -> None:
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        if value:
            self.openRequested.emit(Path(value))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Etikett öffnen", str(storage.labels_dir()),
                                              f"Etiketten (*{storage.SUFFIX})")
        if path:
            self.openRequested.emit(Path(path))

    def _delete(self) -> None:
        path = self._current_path()
        if path is None:
            return
        answer = QMessageBox.question(self, "Löschen", f"„{path.stem}“ wirklich löschen?")
        if answer == QMessageBox.StandardButton.Yes:
            path.unlink(missing_ok=True)
            self.refresh()

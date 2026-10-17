"""Einstiegspunkt: Hauptfenster mit Startseite und Editor (nach Vorbild des P-touch Editors)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from ptlabel import APP_ID, APP_NAME, storage
from ptlabel.editor import EditorPage
from ptlabel.start import StartPage


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.start = StartPage()
        self.editor = EditorPage()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.start)
        self.stack.addWidget(self.editor)
        self.setCentralWidget(self.stack)

        self.start.newRequested.connect(self.new_label)
        self.start.openRequested.connect(self.open_label)
        self.editor.homeRequested.connect(self.go_home)
        self.editor.titleChanged.connect(lambda t: self.setWindowTitle(f"{t} – {APP_NAME}"))
        self.editor.message.connect(lambda m: self.statusBar().showMessage(m, 8000))

        self.go_home(ask=False)
        if storage.list_labels():
            self.start.show_list()
        self.resize(1400, 820)

    def new_label(self, tape: str, tape_color: str) -> None:
        self.editor.new_label(tape, tape_color)
        self.stack.setCurrentWidget(self.editor)

    def open_label(self, path: Path) -> None:
        if self.editor.open_label(path):
            self.stack.setCurrentWidget(self.editor)

    def go_home(self, ask: bool = True) -> None:
        if ask and not self.editor.maybe_save():
            return
        self.start.refresh()
        self.stack.setCurrentWidget(self.start)
        self.setWindowTitle(f"Startseite – {APP_NAME}")

    def closeEvent(self, event) -> None:
        if self.stack.currentWidget() is self.editor and not self.editor.maybe_save():
            event.ignore()
            return
        event.accept()


def main() -> None:
    if os.environ.get("PTLABEL_DEBUG"):
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("ptlabel")
    app.setApplicationDisplayName(APP_NAME)
    # Ordnet das Fenster unter Wayland dem Menüeintrag ptouch-editor.desktop zu
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme(
        APP_ID, QIcon(str(Path(__file__).with_name("resources") / f"{APP_ID}.svg"))))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""Anbindung an den Drucker über das Kommandozeilen-Tool ptouch-print."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtGui import QImage

# Druckbare Höhe in Pixeln (180 dpi) je Bandbreite beim PT-P750W
TAPE_HEIGHT_PX = {
    "3,5 mm": 24,
    "6 mm": 32,
    "9 mm": 50,
    "12 mm": 70,
    "18 mm": 112,
    "24 mm": 128,
}


class PrinterError(RuntimeError):
    pass


def _binary() -> str:
    path = shutil.which("ptouch-print")
    if not path:
        raise PrinterError("ptouch-print wurde nicht gefunden.")
    return path


def info() -> str:
    """Gibt die Druckerinfo zurück (u. a. eingelegte Bandbreite)."""
    result = subprocess.run([_binary(), "--info"], capture_output=True, text=True)
    if result.returncode != 0:
        raise PrinterError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def print_image(image: QImage) -> None:
    """Druckt ein Etikettenbild (wird in Schwarz-Weiß umgewandelt)."""
    mono = image.convertToFormat(QImage.Format.Format_Mono)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "label.png"
        if not mono.save(str(png), "PNG"):
            raise PrinterError("Konnte das Etikettenbild nicht speichern.")
        result = subprocess.run([_binary(), "--image", str(png)], capture_output=True, text=True)
        if result.returncode != 0:
            raise PrinterError(result.stderr.strip() or result.stdout.strip())

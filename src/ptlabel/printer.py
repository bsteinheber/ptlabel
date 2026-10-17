"""Anbindung an den Drucker: per WLAN (Bibliothek ptouch) oder per USB (ptouch-print)."""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSettings
from PySide6.QtGui import QImage

from ptlabel import snmp, storage

DPI = 180
PRINTER_NAME = "Brother PT-P750W"
DEFAULT_HOST = "192.168.20.14"

# Bedruckbare Höhe in Pixeln (180 dpi) je Bandbreite, laut Brother-Spezifikation
# (Raster Command Reference PT-E550W/P750W/P710BT, Abschnitt 2.3 „Print Area“)
TAPE_HEIGHT_PX = {
    "3,5 mm": 24,
    "6 mm": 32,
    "9 mm": 50,
    "12 mm": 70,
    "18 mm": 112,
    "24 mm": 128,
}

# Bandbreite in mm, wie sie der Drucker meldet → Name in TAPE_HEIGHT_PX
_TAPE_BY_MM = {3.5: "3,5 mm", 4: "3,5 mm", 6: "6 mm", 9: "9 mm", 12: "12 mm", 18: "18 mm",
               24: "24 mm"}

# Farbnamen aus libptouch → Anzeige
_COLOR_DE = {
    "White": ("Weiß", "#ffffff"),
    "Clear": ("Transparent", "#f4f4f0"),
    "Red": ("Rot", "#e8473f"),
    "Blue": ("Blau", "#3d7fd9"),
    "Yellow": ("Gelb", "#ffe23d"),
    "Green": ("Grün", "#4caf50"),
    "Black": ("Schwarz", "#222222"),
    "Gold": ("Gold", "#c9a227"),
    "Matte White": ("Weiß (matt)", "#fafafa"),
    "Matte Clear": ("Transparent (matt)", "#f0f0ec"),
    "Matte Silver": ("Silber (matt)", "#c0c0c0"),
    "Fluorescent Orange": ("Neonorange", "#ff8a3d"),
    "Fluorescent Yellow": ("Neongelb", "#eaff3d"),
}

# Drucker-MIB (RFC 3805) und Host-MIB: Bandname, Modell, Status, Fehlerbits
_OID_MEDIA = "1.3.6.1.2.1.43.8.2.1.12.1.1"
_OID_MODEL = "1.3.6.1.2.1.25.3.2.1.3.1"
_OID_ERRORS = "1.3.6.1.2.1.25.3.5.1.2.1"
_ERROR_BITS = [  # hrPrinterDetectedErrorState, höchstwertiges Bit zuerst
    (0x40, "Kein Band eingelegt"),
    (0x08, "Abdeckung offen"),
    (0x04, "Bandstau"),
    (0x02, "Drucker ist offline"),
]


class PrinterError(RuntimeError):
    pass


@dataclass
class Connection:
    """Wie der Drucker erreicht wird: ``kind`` ist "wlan" oder "usb"."""

    kind: str = "wlan"
    host: str = DEFAULT_HOST

    def describe(self) -> str:
        return f"WLAN {self.host}" if self.kind == "wlan" else "USB"


def _settings() -> QSettings:
    return QSettings(str(storage.labels_dir() / "ptlabel.ini"), QSettings.Format.IniFormat)


def load_connection() -> Connection:
    settings = _settings()
    kind = str(settings.value("printer/connection", "wlan"))
    host = str(settings.value("printer/host", DEFAULT_HOST))
    return Connection("usb" if kind == "usb" else "wlan", host.strip() or DEFAULT_HOST)


def save_connection(connection: Connection) -> None:
    settings = _settings()
    settings.setValue("printer/connection", connection.kind)
    settings.setValue("printer/host", connection.host)
    settings.sync()


@dataclass
class MediaInfo:
    """Eingelegtes Band, über USB (``ptouch-print --info``) oder WLAN (SNMP) ermittelt."""

    width_mm: float | None
    tape_px: int | None
    media_type: str
    tape_color: str
    text_color: str
    raw: str
    problem: str = ""

    @property
    def tape(self) -> str | None:
        """Name der Bandbreite wie in TAPE_HEIGHT_PX, falls bekannt."""
        return _TAPE_BY_MM.get(self.width_mm or 0)

    @property
    def tape_color_hex(self) -> str:
        return _COLOR_DE.get(self.tape_color, ("", "#ffffff"))[1]

    def describe(self) -> str:
        if self.problem:
            return self.problem
        if self.width_mm is None:
            return "Kein Band erkannt"
        tape = self.tape or f"{self.width_mm:g} mm"
        if not self.tape_color:
            return tape  # über WLAN meldet der Drucker keine Farben
        return f"{tape}, {color_name_de(self.text_color)} auf {color_name_de(self.tape_color)}"


def color_name_de(name: str) -> str:
    return _COLOR_DE.get(name, (name or "?", ""))[0]


# --- USB über ptouch-print ---------------------------------------------------------------
def _binary() -> str:
    path = shutil.which("ptouch-print")
    if not path:
        raise PrinterError("ptouch-print wurde nicht gefunden.")
    return path


def info() -> str:
    """Gibt die Druckerinfo per USB zurück (u. a. eingelegte Bandbreite)."""
    result = subprocess.run([_binary(), "--info"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise PrinterError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def parse_info(text: str) -> MediaInfo:
    def find(pattern: str) -> str | None:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else None

    width = find(r"^media width\s*=\s*(\d+)\s*mm")
    px = find(r"for this tape is\s*(\d+)\s*px")
    return MediaInfo(
        width_mm=int(width) if width else None,
        tape_px=int(px) if px else None,
        media_type=find(r"^media type\s*=.*\((.*)\)") or "",
        tape_color=find(r"^tape color\s*=.*\((.*)\)") or "",
        text_color=find(r"^text color\s*=.*\((.*)\)") or "",
        raw=text,
    )


def _print_usb(image: QImage, copies: int) -> None:
    mono = image.convertToFormat(QImage.Format.Format_Mono)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "label.png"
        if not mono.save(str(png), "PNG"):
            raise PrinterError("Konnte das Etikettenbild nicht speichern.")
        args = [_binary(), "--copies", str(max(1, copies)), "--image", str(png)]
        result = subprocess.run(args, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise PrinterError(result.stderr.strip() or result.stdout.strip())


# --- WLAN über die Bibliothek ptouch und SNMP --------------------------------------------
def parse_snmp(values: dict) -> MediaInfo:
    media = values.get(_OID_MEDIA)
    media = media.decode("latin-1").strip() if isinstance(media, bytes) else ""
    match = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*mm", media)
    errors = values.get(_OID_ERRORS)
    first = errors[0] if isinstance(errors, bytes) and errors else 0
    problem = next((text for bit, text in _ERROR_BITS if first & bit), "")
    return MediaInfo(
        width_mm=float(match.group(1).replace(",", ".")) if match else None,
        tape_px=None, media_type="", tape_color="", text_color="",
        raw=media, problem=problem,
    )


def _media_wlan(host: str) -> MediaInfo:
    try:
        values = snmp.get(host, [_OID_MEDIA, _OID_MODEL, _OID_ERRORS])
    except OSError as err:
        raise PrinterError(f"Drucker unter {host} antwortet nicht ({err}).\n"
                           "Ist er eingeschaltet und im WLAN?") from err
    return parse_snmp(values)


def _print_wlan(image: QImage, copies: int, host: str, tape: str, margin_px: int,
                margin_mm: float) -> None:
    from PIL import Image
    from ptouch import PTP750W, ConnectionNetwork, Label, PrinterConnectionError
    from ptouch import tape as tapes

    tape_class = {
        "3,5 mm": tapes.Tape3_5mm, "6 mm": tapes.Tape6mm, "9 mm": tapes.Tape9mm,
        "12 mm": tapes.Tape12mm, "18 mm": tapes.Tape18mm, "24 mm": tapes.Tape24mm,
    }[tape]
    # Den Rand schiebt der Drucker selbst vor (mindestens 2 mm), daher aus dem Bild nehmen
    width = image.width() - 2 * margin_px
    if width > 0:
        image = image.copy(margin_px, 0, width, image.height())
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    pil_image = Image.open(io.BytesIO(bytes(data))).convert("RGB")

    connection = ConnectionNetwork(host, timeout=10)
    try:
        printer = PTP750W(connection)
        for _ in range(max(1, copies)):
            printer.print(Label(pil_image, tape_class), margin_mm=max(2.0, margin_mm))
    except PrinterConnectionError as err:
        raise PrinterError(f"Druck über WLAN ({host}) fehlgeschlagen:\n{err}") from err
    finally:
        connection.close()


# --- Öffentliche Schnittstelle -----------------------------------------------------------
def media(connection: Connection | None = None) -> MediaInfo:
    """Fragt das eingelegte Band ab."""
    connection = connection or load_connection()
    if connection.kind == "wlan":
        return _media_wlan(connection.host)
    return parse_info(info())


def print_image(image: QImage, copies: int = 1, *, tape: str, margin_px: int = 0,
                margin_mm: float = 2.0, connection: Connection | None = None) -> None:
    """Druckt ein Etikettenbild (Schwarz/Weiß, Höhe = TAPE_HEIGHT_PX[tape]).

    ``margin_px`` ist der im Bild links und rechts enthaltene Rand.
    """
    connection = connection or load_connection()
    if connection.kind == "wlan":
        _print_wlan(image, copies, connection.host, tape, margin_px, margin_mm)
    else:
        _print_usb(image, copies)

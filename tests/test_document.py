from PySide6.QtGui import QColor, QImage

from ptlabel import printer, storage
from ptlabel.document import ImageItem, LabelScene, TextItem, mm_to_px

INFO = """printer has 180 dpi, maximum printing width is 128 px
maximum printing width for this tape is 76px
media type = 0x01 (Laminated tape)
media width = 12 mm
tape color = 0x06 (Yellow)
text color = 0x08 (Black)
error = 0x0000"""


def test_parse_info():
    info = printer.parse_info(INFO)
    assert info.width_mm == 12
    assert info.tape == "12 mm"
    assert info.tape_px == 76
    assert info.tape_color == "Yellow"
    assert info.describe() == "12 mm, Schwarz auf Gelb"


def test_parse_snmp():
    info = printer.parse_snmp({"1.3.6.1.2.1.43.8.2.1.12.1.1": b'9mm(0.35")',
                               "1.3.6.1.2.1.25.3.5.1.2.1": b"\x00"})
    assert info.tape == "9 mm"
    assert info.describe() == "9 mm"
    assert printer.parse_snmp({"1.3.6.1.2.1.43.8.2.1.12.1.1": b'3.5mm(0.14")'}).tape == "3,5 mm"
    empty = printer.parse_snmp({"1.3.6.1.2.1.25.3.5.1.2.1": b"\x40"})
    assert empty.describe() == "Kein Band eingelegt"


def test_parse_info_without_tape():
    assert printer.parse_info("irgendwas").describe() == "Kein Band erkannt"


def test_text_fits_tape_and_renders_black():
    scene = LabelScene("9 mm")
    item = scene.add_text("abcd123")
    assert 0 < item.boundingRect().height() <= scene.tape_px
    image = scene.render_image()
    assert image.height() == scene.tape_px
    assert image.width() >= item.sceneBoundingRect().right()
    colors = {QColor(image.pixel(x, y)).name() for x in range(image.width())
              for y in range(image.height())}
    assert colors == {"#000000", "#ffffff"}


def test_auto_and_fixed_length():
    scene = LabelScene("12 mm")
    scene.add_text("Hallo")
    auto = scene.label_width_px()
    scene.set_fixed_length(80)
    assert scene.label_width_px() == round(mm_to_px(80)) != auto


def test_round_trip_keeps_items():
    scene = LabelScene("12 mm")
    text = scene.add_text("Zeile 1\nZeile 2", point_size=10)
    image = QImage(40, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    scene.add_image(image)
    scene.set_margin(3)
    data = scene.to_dict()

    copy = LabelScene.from_dict(data)
    assert copy.to_dict() == data
    texts = [i for i in copy.content_items() if isinstance(i, TextItem)]
    images = [i for i in copy.content_items() if isinstance(i, ImageItem)]
    assert texts[0].toPlainText() == text.toPlainText()
    assert images[0].height_px() == scene.content_items()[0].height_px() or images


def test_storage_save_list_and_printed(tmp_path):
    scene = LabelScene("9 mm")
    scene.add_text("Kabel")
    path = storage.new_path("Kabel/Netz", tmp_path)
    assert path.name == "Kabel Netz.ptl"
    storage.save(path, "Kabel/Netz", scene.to_dict())
    storage.save(storage.new_path("Kabel/Netz", tmp_path), "Kopie", scene.to_dict(), printed=True)

    labels = storage.list_labels(tmp_path)
    assert len(labels) == 2
    assert [f.name for f in labels if f.last_printed] == ["Kopie"]
    assert labels[0].tape == "9 mm"


def test_new_line_shrinks_text_to_tape():
    scene = LabelScene("9 mm")
    item = scene.add_text("Hallo Welt", point_size=16.5)
    cursor = item.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText("\nZweite Zeile")
    assert item.document().blockCount() == 2
    assert item.boundingRect().height() <= scene.tape_px
    assert 0 <= item.y() and item.sceneBoundingRect().bottom() <= scene.tape_px

#!/bin/sh
# Baut das Installationspaket dist/ptouch-editor_<Version>_all.deb.
# Aufruf im Projektordner (z. B. im Dev Container):  sh packaging/build-deb.sh
set -eu

cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
ROOT="$BUILD/ptouch-editor"
ICONS="$ROOT/usr/share/icons/hicolor"

mkdir -p "$ROOT/DEBIAN" "$ROOT/opt/ptouch-editor/wheels" "$ROOT/usr/bin" \
         "$ROOT/usr/share/applications" "$ICONS/scalable/apps" "$ICONS/256x256/apps" \
         "$ICONS/48x48/apps" dist

# Programm als Wheel; die Abhängigkeiten lädt postinst bei der Installation
python3 -m pip wheel --quiet --no-deps --wheel-dir "$ROOT/opt/ptouch-editor/wheels" .

install -m 0755 packaging/ptouch-editor "$ROOT/usr/bin/ptouch-editor"
install -m 0644 packaging/ptouch-editor.desktop "$ROOT/usr/share/applications/"
install -m 0644 src/ptlabel/resources/ptouch-editor.svg "$ICONS/scalable/apps/"

# PNG-Varianten für Menüs, die kein SVG anzeigen
QT_QPA_PLATFORM=offscreen python3 - "$ICONS" <<'EOF'
import sys
from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, Qt
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
renderer = QSvgRenderer("src/ptlabel/resources/ptouch-editor.svg")
for size in (256, 48):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    image.save(f"{sys.argv[1]}/{size}x{size}/apps/ptouch-editor.png")
EOF

install -m 0755 packaging/debian/postinst packaging/debian/postrm "$ROOT/DEBIAN/"
SIZE=$(du -sk "$ROOT" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" packaging/debian/control \
    > "$ROOT/DEBIAN/control"

OUT="dist/ptouch-editor_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT" >/dev/null
echo "Fertig: $OUT"

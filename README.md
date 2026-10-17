# ptlabel

Etikettenprogramm für den Brother PT-P750W unter Linux (Ersatz für den P-touch Editor).
Oberfläche in Python/Qt (PySide6), Druck über [ptouch-print](https://dominic.familie-radermacher.ch/projekte/ptouch-print/) per USB.

## Voraussetzungen auf dem Host

- Docker und VS Code mit der Erweiterung „Dev Containers“
- Drucker per USB angeschlossen und im **P-Lite-Modus aus** (Editor-Lite-LED aus)
- Damit das Fenster aus dem Container angezeigt werden darf, einmal pro Sitzung:

  ```bash
  xhost +local:docker
  ```

  (Unter Wayland läuft das über XWayland, das ist bei GNOME/KDE meist automatisch aktiv.)

## Loslegen

```bash
git init
git add .
git commit -m "Projektgerüst mit Dev Container"
code .
```

In VS Code: **„Reopen in Container“**. Danach im Terminal des Containers:

```bash
ptouch-print --info     # prüft, ob der Drucker erkannt wird
python -m ptlabel       # startet das Programm
```

## Struktur

```
.devcontainer/   Dockerfile + devcontainer.json (ptouch-print, Qt-Bibliotheken, USB, X11)
src/ptlabel/
  __main__.py    Oberfläche (aktuell minimal: Text, Schrift, Band, Vorschau, Drucken)
  printer.py     Anbindung an ptouch-print, Bandhöhen in Pixeln
```

## Ohne Container nutzen

```bash
pip install --user .
ptlabel
```

(ptouch-print muss dann auf dem System installiert sein, z. B. `sudo snap install ptouch-print`.)

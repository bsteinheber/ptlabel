# Ptouch Editor (ptlabel)

Etikettenprogramm für den Brother PT-P750W unter Linux – Ersatz für den P-touch Editor.
Oberfläche in Python/Qt (PySide6). Druck per **WLAN** (Bibliothek
[ptouch](https://github.com/nbuchwitz/ptouch), Bandabfrage per SNMP) oder per **USB**
([ptouch-print](https://dominic.familie-radermacher.ch/projekte/ptouch-print/)).

**Einrichtung:** siehe [docs/Einrichtung.md](docs/Einrichtung.md).

Kurzfassung mit Dev Container: Repository in VS Code öffnen → „Reopen in Container“ → im Terminal

```bash
python -m ptlabel
```

## Bedienung

- **Startseite → Neues Etikett:** Bandbreite wählen (oder „Medium prüfen“ fragt das eingelegte
  Band ab) und „Erstellen“.
- **Startseite → Erstellte Etiketten:** alle gespeicherten Etiketten mit Vorschau, sortiert nach
  letzter Verwendung; „Gedruckt“ zeigt nur gedruckte. Doppelklick öffnet im Editor.
- **Editor:** Text, Symbol, Bild einfügen. Ein Klick in einen Text setzt den Cursor an diese
  Stelle; markierter Text lässt sich rechts formatieren (Schrift, Größe in pt, fett/kursiv/
  unterstrichen, Ausrichtung). Ohne Markierung gilt das Format für den ganzen Text. Kommt eine
  Zeile hinzu und passt der Text nicht mehr aufs Band, wird die Schrift verkleinert.
  Ziehen oder Pfeiltasten verschieben, Esc beendet die Bearbeitung, Entf löscht,
  Strg+Mausrad zoomt.
- **Drucken** prüft vorher das eingelegte Band und speichert das Etikett in der Ablage.
- **Verbindung** (links unter „Drucker“): **WLAN** druckt über TCP-Port 9100 mit der Bibliothek
  [ptouch](https://github.com/nbuchwitz/ptouch) und fragt das Band per SNMP ab (ohne Bandfarbe);
  **USB** nutzt ptouch-print. Verbindung und Adresse stehen in `~/Etiketten/ptlabel.ini`.

Etiketten liegen als `*.ptl` (JSON) in `~/Etiketten` – im Dev Container ist das der Ordner
`~/Etiketten` des Hosts. Ein anderes Verzeichnis lässt sich mit `PTLABEL_DIR` setzen.

## Struktur

```
.devcontainer/   Dockerfile, devcontainer.json, host-init.sh (ptouch-print, Qt, USB, X11)
docs/            Einrichtung.md (Anleitung zur Einrichtung)
src/ptlabel/
  __init__.py    Version, Programmname
  __main__.py    Hauptfenster (Startseite ↔ Editor)
  start.py       Startseite: neues Etikett, Liste der erstellten Etiketten
  editor.py      Editor: Druckereinstellungen, Etikett, Text-/Layout-Einstellungen
  document.py    Etikettenmodell (Szene, Text/Bild, Rendern in Druckerpixeln, JSON)
  storage.py     Ablage der Etiketten im Verzeichnis
  symbols.py     Symbolauswahl
  icons.py       selbst gezeichnete Werkzeugleisten-Symbole
  printer.py     Druck und Medium abfragen per WLAN (ptouch, SNMP) oder USB (ptouch-print)
  snmp.py        minimale SNMP-Abfrage für den Bandstatus im WLAN
tests/           pytest (läuft ohne Bildschirm mit QT_QPA_PLATFORM=offscreen)
```

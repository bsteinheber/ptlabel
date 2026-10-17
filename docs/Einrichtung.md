# Einrichtung des Ptouch Editors

Diese Anleitung beschreibt, wie der Ptouch Editor (Paketname `ptlabel`) auf einem Linux-Rechner
eingerichtet wird, um Etiketten auf einem **Brother PT-P750W** zu gestalten und zu drucken –
per **WLAN** oder **USB**.

Es gibt zwei Wege:

| Weg | Wofür | Aufwand |
|---|---|---|
| **A – Dev Container** (empfohlen) | Entwicklung und Nutzung; alles Nötige (Qt-Bibliotheken, ptouch-print, Python-Pakete) steckt im Container | Docker + VS Code |
| **B – Direkt installieren** | Nutzung ohne Container | Pakete von Hand installieren |

---

## 1. Drucker vorbereiten (für beide Wege)

1. **Editor-Lite-Modus ausschalten:** Die Editor-Lite-LED am Drucker muss **aus** sein. Ist sie
   an, die Editor-Lite-Taste gedrückt halten, bis sie erlischt. Im Editor-Lite-Modus meldet sich der
   Drucker als USB-Laufwerk und lässt sich nicht ansteuern.
2. **Für WLAN:**
   - Den Drucker mit dem WLAN-Router verbinden (Infrastruktur-Modus), z. B. per WPS oder mit dem
     Brother „Printer Setting Tool“.
   - Im Router (z. B. Fritz!Box) dem Drucker eine **feste IP-Adresse** geben. Der Drucker meldet
     sich dort mit einem Namen wie `BRW30C9AB58DCBB`.
   - Der Rechner muss die IP-Adresse erreichen – auch wenn der Drucker in einem anderen Netz liegt
     (z. B. `192.168.20.x` statt `192.168.1.x`). Prüfen:
     ```bash
     nc -zv 192.168.20.14 9100      # Druckerport, erwartet: „succeeded“ / „open“
     ```
   - Benutzt werden **TCP-Port 9100** (Druckdaten) und **UDP-Port 161** (SNMP, Abfrage des
     eingelegten Bandes, Community `public` – Werkseinstellung).
3. **Für USB:** Drucker per USB-Kabel anschließen und einschalten.

---

## 2. Weg A – Dev Container (empfohlen)

### Voraussetzungen auf dem Rechner

- Linux mit grafischer Oberfläche (X11 oder Wayland mit XWayland, z. B. KDE oder GNOME)
- **Docker** (oder Podman) – der eigene Benutzer muss Container starten dürfen
- **VS Code** mit der Erweiterung **„Dev Containers“**
- `xauth` (meist vorinstalliert; Paket `xauth` bzw. `xorg-x11-xauth`), optional `xhost`
- Git

### Einrichten

```bash
git clone <Repository-URL> ptlabel
code ptlabel
```

In VS Code erscheint der Hinweis **„Reopen in Container“** (sonst: F1 → *Dev Containers: Reopen in
Container*). Beim ersten Mal wird das Image gebaut (einige Minuten), dabei wird ptouch-print aus
den Quellen übersetzt und das Programm mit allen Python-Paketen installiert.

Vor jedem Start des Containers führt VS Code auf dem Rechner `.devcontainer/host-init.sh` aus:

- legt `~/Etiketten` an – dort liegen die Etiketten und die Einstellungen; der Ordner wird in den
  Container eingebunden und übersteht so jeden Neubau des Containers,
- legt einen X11-Zugangsschlüssel für den Container in `~/.cache/ptlabel-x11/` ab, damit das
  Programmfenster auf dem Bildschirm erscheinen darf,
- erlaubt zusätzlich lokale X11-Verbindungen (`xhost +local:`), falls `xhost` installiert ist.

### Starten

Im Terminal von VS Code (läuft im Container):

```bash
python -m ptlabel
```

### Änderungen an der Container-Konfiguration

Nach Änderungen an `.devcontainer/` oder an den Abhängigkeiten in `pyproject.toml`:
F1 → **Dev Containers: Rebuild Container**. Die Etiketten in `~/Etiketten` bleiben erhalten.

---

## 3. Weg B – Direkt installieren (ohne Container)

### Voraussetzungen

- Python **3.10** oder neuer mit `pip`
- Qt-Laufzeitbibliotheken für X11; unter Debian/Ubuntu z. B.:
  ```bash
  sudo apt install libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
       libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \
       libxcb-xfixes0 libegl1 libgl1 fonts-dejavu fonts-liberation2
  ```
- **Nur für USB:** [ptouch-print](https://dominic.familie-radermacher.ch/projekte/ptouch-print/),
  z. B. `sudo snap install ptouch-print` oder aus den Quellen (siehe `.devcontainer/Dockerfile`)

### Installieren und starten

```bash
git clone <Repository-URL> ptlabel
cd ptlabel
pip install --user .
ptlabel                      # oder: python -m ptlabel
```

### USB-Zugriff ohne root

Meldet ptouch-print bei USB „permission denied“, eine udev-Regel anlegen und den Drucker neu
einstecken:

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="04f9", MODE="0664", GROUP="plugdev"' \
  | sudo tee /etc/udev/rules.d/60-brother-ptouch.rules
sudo udevadm control --reload-rules
sudo usermod -aG plugdev "$USER"     # danach ab- und wieder anmelden
```

---

## 4. Im Programm einrichten

1. Programm starten, auf der Startseite **„Neues Etikett“** → **„Erstellen“**.
2. Im Editor links unter **„Drucker“**:
   - **WLAN** oder **USB** wählen,
   - bei WLAN die **IP-Adresse** des Druckers eintragen (vorbelegt: `192.168.20.14`).
3. **„Medium prüfen“** klicken. Erscheint „Eingelegt: 9 mm“ (bzw. die eingelegte Breite), ist die
   Verbindung in Ordnung und die Bandbreite wird übernommen.

Die Einstellungen werden in `~/Etiketten/ptlabel.ini` gespeichert.

### Wo liegen die Daten?

| Was | Ort |
|---|---|
| Etiketten (`*.ptl`, JSON) | `~/Etiketten/` |
| Einstellungen (Verbindung, IP) | `~/Etiketten/ptlabel.ini` |

Ein anderes Verzeichnis lässt sich mit der Umgebungsvariablen `PTLABEL_DIR` festlegen:

```bash
PTLABEL_DIR=~/Dokumente/Etiketten python -m ptlabel
```

---

## 5. Fehlerbehebung

| Meldung / Verhalten | Ursache und Abhilfe |
|---|---|
| `Authorization required, but no authorization protocol specified` / `could not connect to display` | Das Fenster darf nicht angezeigt werden. Im Dev Container: **Rebuild Container** (richtet den X11-Zugang ein). Sofortlösung: in einem Terminal **auf dem Rechner** (nicht im Container) `xhost +local:` ausführen. |
| „Drucker unter … antwortet nicht“ bei WLAN | Drucker aus oder nicht im WLAN, falsche IP oder Netz nicht erreichbar. Mit `nc -zv <IP> 9100` prüfen; IP in der Fritz!Box nachsehen. |
| „Medium prüfen“ zeigt über WLAN keine Bandfarbe | Normal – per Netzwerk meldet der Drucker nur die Breite. Über USB wird auch die Farbe angezeigt. |
| „Eingelegt ist 12 mm, das Etikett ist für 9 mm angelegt“ | Band wechseln oder links unter „Druckmedium“ die eingelegte Breite wählen. |
| USB: `No P-Touch printer found on USB` | Editor-Lite-LED muss aus sein; Kabel prüfen. Im Container muss der Drucker nicht vor dem Start eingesteckt sein. |
| USB: `permission denied` | udev-Regel anlegen, siehe Abschnitt 3. |
| Sonstiges unerwartetes Verhalten bei Maus/Tastatur | Mit Protokoll starten und die Zeilen `ptlabel.…` auswerten: `PTLABEL_DEBUG=1 python -m ptlabel` |

---

## 6. Für Entwickler

```bash
pip install --user -e '.[dev]'                  # im Container bereits erledigt
QT_QPA_PLATFORM=offscreen python -m pytest      # Tests ohne Bildschirm
ruff check src tests                            # Stilprüfung
```

Aufbau des Quelltextes: siehe [README](../README.md#struktur).

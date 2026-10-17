#!/bin/sh
# Läuft auf dem Host, bevor der Container startet (initializeCommand).

mkdir -p "$HOME/Etiketten" "$HOME/.cache/ptlabel-x11"
cookie="$HOME/.cache/ptlabel-x11/xauth"
touch "$cookie"

# X11-Zugangsschlüssel für den Container ablegen. "ffff" macht ihn unabhängig vom
# Hostnamen, damit er auch im Container (anderer Hostname) gilt.
if [ -n "$DISPLAY" ] && command -v xauth >/dev/null 2>&1; then
  xauth nlist "$DISPLAY" 2>/dev/null | sed -e 's/^..../ffff/' | xauth -f "$cookie" nmerge - 2>/dev/null
fi

# Zusätzlich lokale Verbindungen erlauben, falls xhost vorhanden ist
if command -v xhost >/dev/null 2>&1; then
  xhost +local: >/dev/null 2>&1
fi

exit 0

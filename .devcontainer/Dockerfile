FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

# Build-Abhängigkeiten für ptouch-print + Laufzeit-Bibliotheken für Qt (PySide6, X11/xcb)
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
        cmake gettext libgd-dev libusb-1.0-0-dev pkg-config usbutils \
        libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
        libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
        libxcb-shape0 libxcb-xinerama0 libxcb-xfixes0 libfontconfig1 libdbus-1-3 \
        fonts-dejavu fonts-liberation2 \
    && rm -rf /var/lib/apt/lists/*

# ptouch-print aus den Quellen bauen (spricht den Drucker direkt per libusb an)
RUN git clone --depth 1 https://git.familie-radermacher.ch/linux/ptouch-print.git /tmp/ptouch-print \
    && cmake -S /tmp/ptouch-print -B /tmp/ptouch-print/build \
    && cmake --build /tmp/ptouch-print/build -j"$(nproc)" \
    && install -m 0755 /tmp/ptouch-print/build/ptouch-print /usr/local/bin/ptouch-print \
    && rm -rf /tmp/ptouch-print

# Benutzer darf auf USB-Geräte zugreifen
RUN groupadd -f plugdev && usermod -aG plugdev vscode

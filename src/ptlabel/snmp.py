"""Minimale SNMPv1-Abfrage (GET) über UDP, ohne zusätzliche Bibliotheken.

Reicht, um bei einem Netzwerkdrucker das eingelegte Band und den Status zu lesen.
"""

from __future__ import annotations

import socket


def _length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _length(len(value)) + value


def _int(value: int) -> bytes:
    return _tlv(0x02, value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big", signed=True))


def _oid(oid: str) -> bytes:
    parts = [int(p) for p in oid.split(".")]
    out = bytearray([40 * parts[0] + parts[1]])
    for part in parts[2:]:
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.insert(0, 0x80 | (part & 0x7F))
            part >>= 7
        out += bytes(chunk)
    return _tlv(0x06, bytes(out))


def _read(data: bytes, pos: int) -> tuple[int, bytes, int]:
    """Liest ein TLV-Element ab ``pos``: (Typ, Inhalt, nächste Position)."""
    tag, length = data[pos], data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    return tag, data[pos:pos + length], pos + length


def _decode_oid(raw: bytes) -> str:
    parts = [raw[0] // 40, raw[0] % 40]
    value = 0
    for byte in raw[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(value)
            value = 0
    return ".".join(map(str, parts))


def get(host: str, oids: list[str], community: str = "public",
        timeouts: tuple[float, ...] = (2.0, 3.0, 4.0)) -> dict[str, bytes | int | None]:
    """Fragt mehrere OIDs ab. Texte kommen als bytes, Zahlen als int zurück.

    UDP-Pakete gehen verloren, z. B. während ein Drucker im WLAN aus dem Stromsparmodus
    aufwacht; deshalb wird die Anfrage mit wachsender Wartezeit wiederholt.
    """
    bindings = b"".join(_tlv(0x30, _oid(o) + b"\x05\x00") for o in oids)
    pdu = _tlv(0xA0, _int(1) + _int(0) + _int(0) + _tlv(0x30, bindings))
    message = _tlv(0x30, _int(0) + _tlv(0x04, community.encode()) + pdu)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for attempt, timeout in enumerate(timeouts, start=1):
            sock.settimeout(timeout)
            sock.sendto(message, (host, 161))
            try:
                data = sock.recv(8192)
                break
            except TimeoutError:
                if attempt == len(timeouts):
                    raise

    _, body, _ = _read(data, 0)
    pos = 0
    for _ in range(2):  # Version, Community
        _, _, pos = _read(body, pos)
    _, pdu, _ = _read(body, pos)
    pos = 0
    for _ in range(3):  # Request-ID, Fehlerstatus, Fehlerindex
        _, _, pos = _read(pdu, pos)
    _, bindings, _ = _read(pdu, pos)

    result: dict[str, bytes | int | None] = {}
    pos = 0
    while pos < len(bindings):
        _, binding, pos = _read(bindings, pos)
        _, raw_oid, inner = _read(binding, 0)
        tag, value, _ = _read(binding, inner)
        if tag == 0x04:
            result[_decode_oid(raw_oid)] = value
        elif tag in (0x02, 0x41, 0x42, 0x43):
            result[_decode_oid(raw_oid)] = int.from_bytes(value, "big") if value else 0
        else:
            result[_decode_oid(raw_oid)] = None
    return result

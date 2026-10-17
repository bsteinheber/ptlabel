"""Ablage der Etiketten als JSON-Dateien (*.ptl) in einem Verzeichnis.

Standard ist ``~/Etiketten``; mit der Umgebungsvariable ``PTLABEL_DIR`` lässt sich
ein anderes Verzeichnis wählen.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SUFFIX = ".ptl"


def labels_dir() -> Path:
    path = Path(os.environ.get("PTLABEL_DIR") or Path.home() / "Etiketten").expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


@dataclass
class LabelFile:
    path: Path
    name: str
    label: dict
    created: datetime | None
    modified: datetime | None
    last_used: datetime | None
    last_printed: datetime | None

    @property
    def tape(self) -> str:
        return self.label.get("tape", "?")

    @property
    def sort_time(self) -> datetime:
        return self.last_used or self.modified or datetime.fromtimestamp(self.path.stat().st_mtime)


def load(path: Path) -> LabelFile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return LabelFile(
        path=Path(path),
        name=data.get("name") or Path(path).stem,
        label=data.get("label", {}),
        created=_parse_time(data.get("created")),
        modified=_parse_time(data.get("modified")),
        last_used=_parse_time(data.get("last_used")),
        last_printed=_parse_time(data.get("last_printed")),
    )


def save(path: Path, name: str, label: dict, *, printed: bool = False,
         content_changed: bool = True) -> LabelFile:
    """Schreibt das Etikett; vorhandene Zeitstempel bleiben erhalten."""
    path = Path(path)
    old: dict = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
    now = _now()
    data = {
        "ptlabel": 1,
        "name": name,
        "created": old.get("created", now),
        "modified": now if content_changed or "modified" not in old else old["modified"],
        "last_used": now,
        "last_printed": now if printed else old.get("last_printed"),
        "label": label,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return load(path)


def touch(path: Path) -> None:
    """Merkt sich, dass das Etikett gerade geöffnet wurde (für „Zuletzt verwendet“)."""
    try:
        item = load(path)
        save(path, item.name, item.label, content_changed=False)
    except (OSError, ValueError):
        pass


def list_labels(folder: Path | None = None) -> list[LabelFile]:
    folder = folder or labels_dir()
    result = []
    for path in folder.glob(f"*{SUFFIX}"):
        try:
            result.append(load(path))
        except (OSError, ValueError):
            continue
    result.sort(key=lambda f: f.sort_time, reverse=True)
    return result


def safe_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", name).strip(" .")
    return name[:60] or "Etikett"


def new_path(name: str, folder: Path | None = None) -> Path:
    folder = folder or labels_dir()
    base = safe_filename(name)
    path = folder / f"{base}{SUFFIX}"
    counter = 2
    while path.exists():
        path = folder / f"{base} ({counter}){SUFFIX}"
        counter += 1
    return path

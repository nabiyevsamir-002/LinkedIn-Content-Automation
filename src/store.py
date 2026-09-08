"""Təhlükəsiz fayl yazısı.

Adi `write_text()` faylı əvvəlcə boşaldır, sonra doldurur. Proses həmin
an dayansa (Ctrl+C, kill, elektrik) fayl YARIMÇIQ qalır — JSON pozulur
və bütün vəziyyət itir.

Burada yazı əvvəlcə müvəqqəti fayla gedir, sonra `os.replace` ilə
atomik şəkildə yerinə qoyulur. `os.replace` POSIX-də atomikdir: ya
köhnə fayl, ya yeni fayl olur — yarımçıq heç vaxt.

Əlavə olaraq son sağlam nüsxə `.bak` kimi saxlanılır.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any


def write_text(path: pathlib.Path, text: str, *, backup: bool = True) -> None:
    """Mətni atomik yazır."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if backup and path.exists():
        try:
            path.replace(path.with_suffix(path.suffix + ".bak"))
        except OSError:
            pass

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent),
                                    prefix=f".{path.name}.", suffix=".tmp")
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())      # disk yazısını təsdiqlə
        os.replace(tmp, path)              # atomik dəyişdirmə
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_json(path: pathlib.Path, payload: Any, *, indent: int | None = 2) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=indent))


def read_json(path: pathlib.Path, default: Any = None) -> Any:
    """JSON oxuyur; fayl pozulubsa `.bak` nüsxəsinə qayıdır."""
    path = pathlib.Path(path)
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return default

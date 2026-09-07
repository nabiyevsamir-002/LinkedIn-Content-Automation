"""Pexels stok fotoları — pulsuz API, şaquli format.

Axtarış sorğusunu Visual Director yazır (ingiliscə konkret isimlər),
başlıqdan yox — bu, uyğunluğu kəskin artırır.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.parse
from dataclasses import dataclass

from .. import config, net
from . import render

API = "https://api.pexels.com/v1/search"


@dataclass
class Photo:
    url: str
    photographer: str
    photographer_url: str
    page_url: str
    width: int
    height: int

    @property
    def credit(self) -> str:
        return f"Foto: {self.photographer} / Pexels — {self.page_url}"


def available() -> bool:
    return bool(os.environ.get("PEXELS_API_KEY"))


def search(query: str, limit: int = 6) -> list[Photo]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({
        "query": query, "orientation": "portrait",
        "per_page": limit, "size": "large",
    })
    raw = net.fetch(f"{API}?{params}", headers={"Authorization": key})
    data = json.loads(raw.decode("utf-8"))
    out = []
    for item in data.get("photos", []):
        src = item.get("src", {})
        url = src.get("large2x") or src.get("original") or src.get("large")
        if not url:
            continue
        out.append(Photo(
            url=url,
            photographer=item.get("photographer", "?"),
            photographer_url=item.get("photographer_url", ""),
            page_url=item.get("url", ""),
            width=item.get("width", 0), height=item.get("height", 0),
        ))
    return out


def download(photo: Photo, dst: pathlib.Path) -> pathlib.Path:
    """Fotonu yükləyir və 1200×1500 formatına kəsir."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".src")
    tmp.write_bytes(net.fetch(photo.url, timeout=45))
    try:
        render.fit_photo(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst

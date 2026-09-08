"""Stok şəkil axtarışı — bir neçə mənbədən paralel.

Bir mənbə həmişə yaxşı nəticə vermir. Burada dörd provayder var və
nəticələr növbələşdirilir: birinci sırada hər mənbənin ən yaxşısı,
sonra ikincilər. Beləliklə seçim həm keyfiyyətli, həm müxtəlif olur.

  Openverse — AÇAR TƏLƏB ETMİR, dərhal işləyir (CC lisenziyalı, 800M+ şəkil)
  Pexels    — pulsuz açar, yüksək keyfiyyət
  Unsplash  — pulsuz açar, redaksiya üslubu
  Pixabay   — pulsuz açar, geniş bazа
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import urllib.parse
from dataclasses import dataclass

from .. import net
from . import render


@dataclass
class Photo:
    url: str
    provider: str
    photographer: str
    page_url: str
    width: int = 0
    height: int = 0
    license: str = ""

    @property
    def credit(self) -> str:
        parts = [f"Foto: {self.photographer or '?'}"]
        parts.append(self.provider)
        if self.license:
            parts.append(self.license.upper())
        line = " / ".join(parts)
        return f"{line} — {self.page_url}" if self.page_url else line

    @property
    def key(self) -> str:
        return (self.page_url or self.url).split("?")[0]


# --- provayderlər -----------------------------------------------------

def _openverse(query: str, limit: int) -> list[Photo]:
    """Açar tələb etmir — sistem qutudan çıxan kimi işləyir."""
    params = urllib.parse.urlencode({
        "q": query, "page_size": limit, "license_type": "commercial",
        "aspect_ratio": "tall", "mature": "false",
    })
    raw = net.fetch(f"https://api.openverse.org/v1/images/?{params}", timeout=25)
    data = json.loads(raw.decode("utf-8"))
    out = []
    for item in data.get("results", []):
        url = item.get("url")
        if not url:
            continue
        out.append(Photo(
            url=url, provider="Openverse",
            photographer=item.get("creator") or "?",
            page_url=item.get("foreign_landing_url") or "",
            width=item.get("width") or 0, height=item.get("height") or 0,
            license=item.get("license") or "",
        ))
    return out


def _pexels(query: str, limit: int) -> list[Photo]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({
        "query": query, "orientation": "portrait", "per_page": limit, "size": "large",
    })
    raw = net.fetch(f"https://api.pexels.com/v1/search?{params}",
                    headers={"Authorization": key}, timeout=25)
    data = json.loads(raw.decode("utf-8"))
    out = []
    for item in data.get("photos", []):
        src = item.get("src", {})
        url = src.get("large2x") or src.get("original") or src.get("large")
        if not url:
            continue
        out.append(Photo(
            url=url, provider="Pexels", photographer=item.get("photographer", "?"),
            page_url=item.get("url", ""), width=item.get("width", 0),
            height=item.get("height", 0),
        ))
    return out


def _unsplash(query: str, limit: int) -> list[Photo]:
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({
        "query": query, "per_page": limit, "orientation": "portrait",
    })
    raw = net.fetch(f"https://api.unsplash.com/search/photos?{params}",
                    headers={"Authorization": f"Client-ID {key}"}, timeout=25)
    data = json.loads(raw.decode("utf-8"))
    out = []
    for item in data.get("results", []):
        url = (item.get("urls") or {}).get("regular")
        if not url:
            continue
        out.append(Photo(
            url=url, provider="Unsplash",
            photographer=(item.get("user") or {}).get("name", "?"),
            page_url=(item.get("links") or {}).get("html", ""),
            width=item.get("width", 0), height=item.get("height", 0),
        ))
    return out


def _pixabay(query: str, limit: int) -> list[Photo]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({
        "key": key, "q": query, "orientation": "vertical",
        "per_page": max(3, limit), "image_type": "photo", "safesearch": "true",
    })
    raw = net.fetch(f"https://pixabay.com/api/?{params}", timeout=25)
    data = json.loads(raw.decode("utf-8"))
    out = []
    for item in data.get("hits", []):
        url = item.get("largeImageURL") or item.get("webformatURL")
        if not url:
            continue
        out.append(Photo(
            url=url, provider="Pixabay", photographer=item.get("user", "?"),
            page_url=item.get("pageURL", ""),
            width=item.get("imageWidth", 0), height=item.get("imageHeight", 0),
        ))
    return out


# 1200×1500-ə böyüdüləndə bulanıq görünməsin deyə minimum ölçü.
# Ölçüsü bildirilməyən şəkillərə şübhə xeyrinə icazə verilir.
MIN_WIDTH, MIN_HEIGHT = 900, 1100


def _big_enough(photo: Photo) -> bool:
    if not photo.width or not photo.height:
        return True
    if photo.width >= MIN_WIDTH and photo.height >= MIN_HEIGHT:
        return True
    # Yatıq şəkil də olar, əsas odur ki kəsdikdən sonra kifayət qədər piksel qalsın
    return photo.width >= 1400 and photo.height >= 900


PROVIDERS = {
    "Openverse": _openverse,   # açarsız — həmişə mövcuddur
    "Pexels": _pexels,
    "Unsplash": _unsplash,
    "Pixabay": _pixabay,
}

KEY_ENV = {
    "Openverse": None,
    "Pexels": "PEXELS_API_KEY",
    "Unsplash": "UNSPLASH_ACCESS_KEY",
    "Pixabay": "PIXABAY_API_KEY",
}


def active_providers() -> list[str]:
    return [name for name, env in KEY_ENV.items()
            if env is None or os.environ.get(env)]


def available() -> bool:
    return bool(active_providers())


def search(query: str, limit: int = 8) -> list[Photo]:
    """Bütün aktiv mənbələrdə paralel axtarır və nəticələri növbələşdirir."""
    names = active_providers()
    if not names:
        return []
    per_provider = max(3, limit // max(1, len(names)) + 2)

    results: dict[str, list[Photo]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = {pool.submit(PROVIDERS[n], query, per_provider): n for n in names}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = [p for p in future.result() if _big_enough(p)]
            except Exception:  # noqa: BLE001 — bir mənbə axtarışı dayandırmır
                results[name] = []

    # Növbələşdirmə: hər mənbənin 1-cisi, sonra 2-ciləri…
    merged: list[Photo] = []
    seen: set[str] = set()
    for index in range(per_provider):
        for name in names:
            bucket = results.get(name) or []
            if index < len(bucket):
                photo = bucket[index]
                if photo.key not in seen:
                    seen.add(photo.key)
                    merged.append(photo)
    return merged[:limit]


def download(photo: Photo, dst: pathlib.Path) -> pathlib.Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".src")
    tmp.write_bytes(net.fetch(photo.url, timeout=60))
    try:
        render.fit_photo(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst

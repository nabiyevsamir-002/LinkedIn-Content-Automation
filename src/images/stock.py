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
    caption: str = ""      # alt / description / tags — uyğunluq balı üçün
    score: float = 0.0

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
    raw = net.fetch(f"https://api.openverse.org/v1/images/?{params}", timeout=10)
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
            caption=" ".join(filter(None, [
                item.get("title") or "",
                ", ".join(t.get("name", "") for t in (item.get("tags") or [])[:12]),
            ])),
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
            caption=item.get("alt") or "",
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
            caption=" ".join(filter(None, [
                item.get("alt_description") or "",
                item.get("description") or "",
                " ".join(t.get("title", "") for t in (item.get("tags") or [])[:10]),
            ])),
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
            caption=item.get("tags") or "",
        ))
    return out


# Ümumi axtarış vaxtı. Openverse pulsuz ictimai API-dir və bəzən
# 50+ saniyə çəkir — istifadəçi «Real foto» basandan sonra bu qədər
# gözləməməlidir. Bu həddi keçən mənbə sadəcə nəticəsiz sayılır.
SEARCH_DEADLINE = float(os.environ.get("PHOTO_SEARCH_DEADLINE", "6"))

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


# Sıra əhəmiyyətlidir: nəticələr növbələşdirilərkən bu ardıcıllıqla
# götürülür, ona görə keyfiyyətli və sürətli mənbələr öndədir.
PROVIDERS = {
    "Pexels": _pexels,
    "Unsplash": _unsplash,
    "Pixabay": _pixabay,
    "Openverse": _openverse,   # açarsız ehtiyat — yavaş, çox vaxt kiçik şəkillər
}

KEY_ENV = {
    "Pexels": "PEXELS_API_KEY",
    "Unsplash": "UNSPLASH_ACCESS_KEY",
    "Pixabay": "PIXABAY_API_KEY",
    "Openverse": None,
}


def active_providers() -> list[str]:
    return [name for name, env in KEY_ENV.items()
            if env is None or os.environ.get(env)]


def available() -> bool:
    return bool(active_providers())


_STOP = {"the", "a", "an", "of", "in", "on", "at", "with", "and", "or",
         "for", "to", "photo", "image", "picture", "stock"}


def _terms(text: str) -> set[str]:
    import re

    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower())
            if w not in _STOP}


def _relevance(photo: Photo, query: str, query_rank: int) -> float:
    """Şəkil sorğuya nə qədər uyğundur.

    Provayderlər öz sıralamasını verir, amma o, çox vaxt ümumidir:
    «laptop login screen» sorğusuna adi noutbuk şəkli qaytarır. Burada
    şəklin öz təsvir mətni ilə sorğu sözlərinin üst-üstə düşməsinə
    baxırıq — bu, mövzuya uyğunluğu xeyli artırır.
    """
    wanted = _terms(query)
    if not wanted:
        return 0.0
    have = _terms(photo.caption)
    matched = len(wanted & have)
    # Uzun sorğuda hər sözün uyğun gəlmə ehtimalı azdır — 3 sözdən
    # sonrakılar üçün tələbi yumşaldırıq.
    overlap = matched / min(len(wanted), 3) if wanted else 0.0
    overlap = min(overlap, 1.0)
    # Birinci sorğu «səhnə»dir və insanlı səhnələr əşya klişelərindən
    # daha maraqlıdır. Fotoqraflar isə əşyaları daha hərfi etiketlədiyi
    # üçün metafora sorğusu təbii olaraq yüksək bal alır — çəki ilə
    # tarazlaşdırırıq.
    rank_bonus = (0.35, 0.15, 0.0)[min(query_rank, 2)]
    # Təsviri olmayan şəkil cəzalandırılmır, amma önə də keçmir
    blind = 0.15 if not have else 0.0
    return overlap + rank_bonus + blind


def _search_one(query: str, per_provider: int, names: list) -> dict:
    results: dict[str, list[Photo]] = {}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(names))
    futures = {pool.submit(PROVIDERS[n], query, per_provider): n for n in names}
    try:
        for future in concurrent.futures.as_completed(futures,
                                                      timeout=SEARCH_DEADLINE):
            name = futures[future]
            try:
                results[name] = [p for p in future.result() if _big_enough(p)]
            except Exception:  # noqa: BLE001 — bir mənbə axtarışı dayandırmır
                results[name] = []
    except concurrent.futures.TimeoutError:
        pass          # gecikən mənbələr sadəcə nəticəsiz sayılır
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def search(query, limit: int = 8) -> list[Photo]:
    """Bir və ya bir neçə sorğu ilə axtarır, nəticələri uyğunluğa görə sıralayır.

    `query` sətir və ya sətirlər siyahısı ola bilər. Siyahı veriləndə
    birinci sorğu ən konkret sayılır və nəticələri üstün tutulur.
    """
    queries = [query] if isinstance(query, str) else [q for q in query if q]
    queries = [q.strip() for q in queries if q and q.strip()][:3]
    names = active_providers()
    if not names or not queries:
        return []

    per_provider = max(3, limit // max(1, len(names)) + 2)
    scored: dict[str, Photo] = {}

    for rank, q in enumerate(queries):
        for bucket in _search_one(q, per_provider, names).values():
            for photo in bucket:
                value = _relevance(photo, q, rank)
                existing = scored.get(photo.key)
                if existing is None or value > existing.score:
                    photo.score = value
                    scored[photo.key] = photo
        # Birinci sorğu kifayət qədər yaxşı nəticə veribsə dayanırıq
        strong = [p for p in scored.values() if p.score >= 0.5]
        if len(strong) >= limit:
            break

    ordered = sorted(scored.values(), key=lambda p: -p.score)

    # Mənbə müxtəlifliyi: eyni provayderdən ardıcıl 3 şəkil olmasın
    out: list[Photo] = []
    pending = list(ordered)
    while pending and len(out) < limit:
        for index, photo in enumerate(pending):
            recent = [p.provider for p in out[-2:]]
            if len(recent) < 2 or recent.count(photo.provider) < 2:
                out.append(pending.pop(index))
                break
        else:
            out.append(pending.pop(0))
    return out[:limit]


def download(photo: Photo, dst: pathlib.Path) -> pathlib.Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".src")
    tmp.write_bytes(net.fetch(photo.url, timeout=60))
    try:
        render.fit_photo(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst

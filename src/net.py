"""Şəbəkə qatı — SSL kontekstini özü düzəldir.

macOS-da python.org quraşdırması kök sertifikatları qurmadan gəlir və
bütün HTTPS sorğuları CERTIFICATE_VERIFY_FAILED verir. Burada `certifi`
varsa ondan istifadə edirik, yoxdursa sistem defaultuna qayıdırıq —
istifadəçidən heç nə tələb olunmur.
"""
from __future__ import annotations

import gzip
import io
import ssl
import time
from dataclasses import dataclass
import urllib.error
import urllib.request
import zlib

from . import config

_CTX: ssl.SSLContext | None = None


def ssl_context() -> ssl.SSLContext:
    global _CTX
    if _CTX is not None:
        return _CTX
    try:
        import certifi

        _CTX = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        _CTX = ssl.create_default_context()
    return _CTX


def _decode(raw: bytes, encoding: str) -> bytes:
    if encoding == "gzip":
        try:
            return gzip.decompress(raw)
        except OSError:
            return raw
    if encoding in ("deflate", "zlib"):
        try:
            return zlib.decompress(raw)
        except zlib.error:
            try:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
            except zlib.error:
                return raw
    return raw


def fetch(url: str, *, timeout: int | None = None, headers: dict | None = None) -> bytes:
    """HTTPS GET — sertifikat və gzip məsələləri həll edilmiş."""
    hdrs = {
        "User-Agent": config.USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "*/*",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    last: Exception | None = None
    # RSS serverləri (xüsusən hnrss) vaxtaşırı bağlantını kəsir —
    # bir keçici xəta bütün mənbəni itirməməlidir.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                req, timeout=timeout or config.HTTP_TIMEOUT, context=ssl_context()
            ) as resp:
                return _decode(
                    resp.read(), (resp.headers.get("Content-Encoding") or "").lower()
                )
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError(f"fetch uğursuz: {url}")


def fetch_text(url: str, *, timeout: int | None = None) -> str:
    return fetch(url, timeout=timeout).decode("utf-8", errors="replace")


def post(url: str, body: bytes, *, headers: dict | None = None,
         timeout: int | None = None) -> bytes:
    """HTTPS POST — AI şəkil provayderləri üçün."""
    hdrs = {"User-Agent": config.USER_AGENT, "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    with urllib.request.urlopen(
        req, timeout=timeout or config.HTTP_TIMEOUT, context=ssl_context()
    ) as resp:
        return _decode(resp.read(), (resp.headers.get("Content-Encoding") or "").lower())


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict

    def json(self):
        import json as _json

        return _json.loads(self.body.decode("utf-8")) if self.body else {}


def request(method: str, url: str, *, body: bytes | None = None,
            headers: dict | None = None, timeout: int | None = None) -> Response:
    """Ümumi HTTPS sorğusu — başlıqlara da giriş verir.

    LinkedIn yaradılan postun URN-ini cavab gövdəsində yox, `x-restli-id`
    başlığında qaytarır, ona görə başlıqlar lazımdır.
    """
    hdrs = {"User-Agent": config.USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(
            req, timeout=timeout or config.HTTP_TIMEOUT, context=ssl_context()
        ) as resp:
            raw = _decode(resp.read(),
                          (resp.headers.get("Content-Encoding") or "").lower())
            return Response(resp.status, raw, {k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return Response(exc.code, raw, {k.lower(): v for k, v in (exc.headers or {}).items()})

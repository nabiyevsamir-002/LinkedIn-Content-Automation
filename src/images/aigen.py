"""AI şəkil generasiyası — zəncirin son, ödənişli pilləsi.

Yalnız bütün pulsuz variantlar rədd edildikdə işə düşür. Provayder
əvəzlənə biləndir; açar yoxdursa pillə səssizcə atlanır.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib

from .. import net
from . import render

PROVIDER = os.environ.get("IMAGE_PROVIDER", "openai")


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY")) and PROVIDER == "openai"


# Xəbər kartının foto pəncərəsi YATIQDIR (1200×860). Portret (1024×1536)
# yaradanda kart yalnız yuxarı ~57%-i göstərirdi və «geniş plan» kadrında
# subyekt altda qalıb, pəncərə boş səma olurdu (17.09.2026 — «$0.03-a boş
# şəkil»). İndi yatıq yaradılır və birbaşa pəncərəyə kəsilir: kart bütün
# kompozisiyanı göstərir.
SIZE = os.environ.get("IMAGE_SIZE", "1536x1024")
WINDOW = (1200, 860)


def generate(prompt: str, dst: pathlib.Path) -> pathlib.Path:
    """Foto-realistik şəkil yaradır (təxmini $0.02-0.04) — kart pəncərəsi ölçüsündə."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY təyin edilməyib — bu pillə əlçatmazdır.")

    payload = json.dumps({
        "model": "gpt-image-1", "prompt": prompt,
        "size": SIZE, "quality": "medium", "n": 1,
    }).encode()
    raw = net.post(
        "https://api.openai.com/v1/images/generations", payload,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        timeout=180,
    )
    data = json.loads(raw.decode("utf-8"))
    b64 = data["data"][0]["b64_json"]

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".src")
    tmp.write_bytes(base64.b64decode(b64))
    try:
        render.fit_photo(tmp, dst, size=WINDOW)
    finally:
        tmp.unlink(missing_ok=True)
    return dst

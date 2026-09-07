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


def generate(prompt: str, dst: pathlib.Path) -> pathlib.Path:
    """Foto-realistik şəkil yaradır (təxmini $0.02-0.04)."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY təyin edilməyib — bu pillə əlçatmazdır.")

    payload = json.dumps({
        "model": "gpt-image-1", "prompt": prompt,
        "size": "1024x1536", "quality": "medium", "n": 1,
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
        render.fit_photo(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst

"""Üslub kalibrləməsinin vəziyyəti.

İki fayl doldurulmayana qədər `voice` və `local_relevance` balları
aşağı qalır. Sistem bunu özü aşkarlayır və xatırladır — istifadəçi
söhbətdə olmasa da.
"""
from __future__ import annotations

import re

from . import config

POSITIONING = config.PROMPTS_DIR / "positioning.md"
VOICE_GUIDE = config.PROMPTS_DIR / "voice_guide.md"


def positioning_filled() -> tuple[bool, int, int]:
    """(doldurulub?, dolu cavab sayı, ümumi sual sayı)"""
    if not POSITIONING.exists():
        return False, 0, 0
    text = POSITIONING.read_text(encoding="utf-8")
    # Şərh bloklarını (nümunələri) çıxarırıq — onlar cavab sayılmır
    text = re.sub(r"(?s)<!--.*?-->", "", text)
    blocks = text.split("CAVAB:")[1:]
    total = len(blocks)
    filled = 0
    for block in blocks:
        body = re.split(r"\n##|\n---", block)[0]
        body = re.sub(r"^[\s\-]+$", "", body, flags=re.M).strip()
        if len(body) >= 15:
            filled += 1
    return (filled >= max(3, total - 1)), filled, total


def voice_examples() -> int:
    """voice_guide.md-dəki nümunə postların təxmini sayı."""
    if not VOICE_GUIDE.exists():
        return 0
    text = VOICE_GUIDE.read_text(encoding="utf-8")
    match = re.search(
        r"NÜMUNƏLƏR BAŞLAYIR\s*-->(.*?)<!--\s*NÜMUNƏLƏR BİTİR", text, re.S
    )
    if not match:
        return 0
    body = match.group(1).strip()
    if len(body) < 80:
        return 0
    # Boş sətirlə ayrılmış bloklar ≈ ayrı postlar
    return len([b for b in re.split(r"\n\s*\n\s*\n", body) if len(b.strip()) > 80]) or 1


def status() -> dict:
    ok_pos, filled, total = positioning_filled()
    examples = voice_examples()
    return {
        "positioning_ok": ok_pos,
        "positioning_filled": filled,
        "positioning_total": total,
        "voice_examples": examples,
        "voice_ok": examples >= 2,
        "complete": ok_pos and examples >= 2,
    }


def reminder_lines(colored: bool = False) -> list[str]:
    """Doldurulmamış hissələr üçün xatırlatma sətirləri."""
    st = status()
    if st["complete"]:
        return []
    lines = []
    if not st["positioning_ok"]:
        lines.append(
            f"prompts/positioning.md — {st['positioning_filled']}/{st['positioning_total']} "
            "sual cavablandırılıb (yerli kontekst üçün lazımdır)"
        )
    if not st["voice_ok"]:
        lines.append(
            f"prompts/voice_guide.md — {st['voice_examples']} nümunə post "
            "(səs balı üçün 3-5 ədəd lazımdır)"
        )
    return lines

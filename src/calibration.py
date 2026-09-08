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


# Doldurulmamış şablonun izləri
_PLACEHOLDERS = ("(doldurun)", "CAVAB:\n\n\n", "NÜMUNƏ (silin")


def positioning_filled() -> tuple[bool, int, int]:
    """(doldurulub?, doldurulmuş bölmə sayı, ümumi bölmə sayı)

    Format sərbəstdir — şablon sualları da, sərbəst mətn də qəbul edilir.
    Yoxlanılan: hər bölmədə real məzmun varmı və şablon izləri qalıbmı.
    """
    if not POSITIONING.exists():
        return False, 0, 0
    raw = POSITIONING.read_text(encoding="utf-8")
    text = re.sub(r"(?s)<!--.*?-->", "", raw)      # şərhlər sayılmır

    sections = [b for b in re.split(r"^##\s+", text, flags=re.M)[1:]]
    total = len(sections)
    if not total:
        return False, 0, 0

    filled = 0
    for section in sections:
        body = section.split("\n", 1)[1] if "\n" in section else ""
        body = re.sub(r"^[\s\-*>]+$", "", body, flags=re.M).strip()
        if len(body) >= 40 and not any(ph in body for ph in _PLACEHOLDERS):
            filled += 1

    ok = filled >= max(3, total - 2) and not any(ph in text for ph in _PLACEHOLDERS)
    return ok, filled, total


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
    # Nümunələr «**Nümunə N**» başlığı, «---» ayırıcısı və ya iki boş
    # sətirlə ayrıla bilər — üçünü də tanıyırıq.
    labelled = re.findall(r"\*\*\s*N[üu]mun[əe]\s*\d", body)
    if labelled:
        return len(labelled)
    blocks = [b for b in re.split(r"\n\s*---\s*\n|\n\s*\n\s*\n", body)
              if len(b.strip()) > 80]
    return len(blocks) or 1


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

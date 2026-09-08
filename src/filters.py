"""Klişe filtri — LinkedIn-in ölü ifadələri və AZ kalkaları.

Deterministikdir: LLM çağırışı yoxdur, xərci sıfırdır, heç vaxt sınmır.
Bir neçə bayraq qalxarsa, mətn yenidən yazılmağa göndərilir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EN_CLICHES = [
    r"game[\s-]?chang(er|ing)", r"revolutioniz", r"let that sink in",
    r"the future is (here|now)", r"buckle up", r"mind[\s-]?blow",
    r"this changes everything", r"in today'?s rapidly", r"needle[\s-]?mover",
    r"paradigm shift", r"unlock(ing)? the power", r"dive deep",
    r"it'?s not just .*, it'?s", r"here'?s the kicker", r"read that again",
]

AZ_CLICHES = [
    r"sür[əe]tl[əe] d[əe]yi[şs][əe]n d[üu]nya", r"g[əe]l[əe]c[əe]k art[ıi]q burada",
    r"oyunun qaydalar[ıi]n[ıi] d[əe]yi[şs]", r"[əe]sl inqilab",
    r"t[əe]s[əe]vv[üu]r edin ki", r"bir daha s[üu]but etdi",
    r"[şs][üu]bh[əe]siz ki", r"he[çc] [şs][üu]bh[əe]siz",
    r"bu, h[əe]r [şs]eyi d[əe]yi[şs]", r"diqq[əe]t yeti", r"qeyd etm[əe]k laz[ıi]md[ıi]r ki",
]

# Süni "tərcümə iyi" verən quruluşlar
AZ_CALQUES = [
    r"\bhəyata keçirilir\b", r"\bnəzərdə tutulur ki\b", r"\bmövcuddur ki\b",
    r"\btəşkil edir ki\b", r"\bhesab olunur ki\b.*\bhesab olunur ki\b",
]

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)


@dataclass
class Flag:
    kind: str
    detail: str


def check(text: str) -> list[Flag]:
    flags: list[Flag] = []
    low = text.lower()

    for pattern in EN_CLICHES:
        m = re.search(pattern, low)
        if m:
            flags.append(Flag("cliche_en", m.group(0)[:60]))
    for pattern in AZ_CLICHES:
        m = re.search(pattern, low)
        if m:
            flags.append(Flag("cliche_az", m.group(0)[:60]))
    for pattern in AZ_CALQUES:
        m = re.search(pattern, low)
        if m:
            flags.append(Flag("calque_az", m.group(0)[:60]))

    emoji_count = len(EMOJI.findall(text))
    if emoji_count > 4:
        flags.append(Flag("emoji", f"{emoji_count} emoji (maksimum 4)"))

    hashtags = re.findall(r"(?<!\w)#\w+", text)
    if len(hashtags) > 6:
        flags.append(Flag("hashtags", f"{len(hashtags)} hashtag (maksimum 6)"))

    if re.search(r"^\s*[\U0001F680✨]", text):
        flags.append(Flag("opener", "post emoji ilə başlayır"))

    if text.count("—") > 2:
        flags.append(Flag("em_dash", f"{text.count('—')} uzun tire (maksimum 2) — AI izidir"))

    length = len(text)
    if length > 1300:
        flags.append(Flag("too_long", f"{length} simvol (maksimum 1300)"))
    elif length < 650:
        flags.append(Flag("too_short", f"{length} simvol (minimum 650)"))

    # Divar abzas: telefonda oxunmur
    for para in text.split("\n\n"):
        para = para.strip()
        if len(para) > 320 and not para.startswith(("•", "-", "→")):
            flags.append(Flag("wall_of_text",
                              f"{len(para)} simvollu abzas — 2 sətirdən çox"))
            break

    if re.search(r"(mənim təxminimcə|təxmin edirəm ki|yəqin ki)\s*[—,-]?\s*\S*\s*(saat|gün|faiz|%|dəfə)", low):
        flags.append(Flag("invented_number", "hedcinq ilə uydurulmuş kəmiyyət"))

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and sum(1 for ln in lines if ln.strip().startswith(("•", "-", "→"))) > 6:
        flags.append(Flag("bullets", "həddindən çox bənd — post siyahıya çevrilib"))

    return flags


def summary(flags: list[Flag]) -> str:
    if not flags:
        return "təmiz"
    return "; ".join(f"{f.kind}: {f.detail}" for f in flags)

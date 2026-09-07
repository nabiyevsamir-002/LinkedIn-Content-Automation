"""LinkedIn önizləməsi — "…daha çox" kəsilmə xəttini göstərir.

Postun ilk 2-3 sətri bütün çatımı müəyyən edir. Hook o xəttdən əvvəl
bitməlidir — bunu gözlə görmək lazımdır, təxmin etmək yox.
"""
from __future__ import annotations

from . import config

FOLD = "─" * 46 + " …daha çox " + "─" * 12


def fold_index(text: str) -> int:
    """Kəssilmə nöqtəsi: simvol həddi və ya sətir həddi — hansı əvvəl gəlirsə."""
    limit = config.LINKEDIN_FOLD_CHARS
    lines, count, used = text.splitlines(keepends=True), 0, 0
    for line in lines:
        used += 1
        if count + len(line) > limit:
            return count + max(0, limit - count)
        count += len(line)
        if used >= config.LINKEDIN_FOLD_LINES and count >= 90:
            return count
    return len(text)


def render(text: str) -> str:
    cut = fold_index(text)
    head, tail = text[:cut].rstrip(), text[cut:].lstrip()
    out = [head, FOLD]
    if tail:
        out.append(tail)
    return "\n".join(out)


def stats(text: str) -> dict:
    hook = text[: fold_index(text)]
    return {
        "chars": len(text),
        "words": len(text.split()),
        "hook_chars": len(hook),
        "hook": hook.replace("\n", " ")[:200],
    }

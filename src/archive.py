"""Yayımlanmış postların arxivi.

Növbə (`queue.json`) iş alətidir — bitmiş postların ağır sahələri
təmizlənir, tarixçə kəsilir. Arxiv isə **daimidir**: hər yayımlanan
post ayrıca markdown faylı kimi qalır.

Nə üçün lazımdır:
  • Sabah bloq, newsletter və ya e-kitab hazırlamaq istəsəniz mənbə hazırdır
  • Hansı mövzuların işlədiyini geriyə baxıb təhlil etmək
  • LinkedIn hesabınıza nəsə olsa, məzmun sizdə qalır
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from . import config, queue, timefmt

ARCHIVE_DIR = config.ROOT / "archive"
INDEX = ARCHIVE_DIR / "INDEX.md"

_TRANSLIT = str.maketrans({
    "ə": "e", "Ə": "E", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I",
    "ö": "o", "Ö": "O", "ş": "s", "Ş": "S", "ü": "u", "Ü": "U", "ç": "c", "Ç": "C",
})


def slug(text: str, limit: int = 48) -> str:
    text = (text or "post").translate(_TRANSLIT)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text or "post")[:limit].strip("-")


def path_for(item: queue.Item) -> "config.pathlib.Path":
    when = timefmt.local(item.published_at or item.created_at) or timefmt.now()
    folder = ARCHIVE_DIR / f"{when:%Y}" / f"{when:%m}"
    return folder / f"{when:%Y-%m-%d}-{slug(item.chosen.get('title', item.id))}.md"


def write(item: queue.Item) -> "config.pathlib.Path":
    """Bir postu arxivə yazır (təkrar çağırışda üzərinə yazır)."""
    path = path_for(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    when = timefmt.local(item.published_at or item.created_at)
    scores = item.scores or {}
    research = item.research or {}

    lines = [
        "---",
        f'title: "{(item.chosen.get("title") or "").replace(chr(34), chr(39))}"',
        f"date: {when.isoformat() if when else ''}",
        f"pillar: {item.chosen.get('pillar', '')}",
        f"linkedin: {item.linkedin_url or ''}",
        f"source: {item.chosen.get('link', '')}",
        f"scores: {scores}",
        f"queue_id: {item.id}",
        "---",
        "",
        f"# {item.chosen.get('title', item.id)}",
        "",
        f"*{timefmt.fmt(item.published_at or item.created_at)} · "
        f"{timefmt.label()}*",
        "",
        "## Post",
        "",
        item.post,
        "",
    ]
    if item.first_comment:
        lines += ["## Birinci şərh", "", item.first_comment, ""]
    if item.image_path:
        lines += ["## Şəkil", "", f"`{item.image_path}`", ""]
        if item.alt_text:
            lines += [f"> {item.alt_text}", ""]

    facts = research.get("facts") or []
    numbers = research.get("numbers") or []
    if facts or numbers:
        lines += ["## Faktlar", ""]
        for fact in facts[:12]:
            lines.append(f"- [{fact.get('confidence', '?')}] {fact.get('claim', '')}")
        for num in numbers[:12]:
            lines.append(f"- **{num.get('label')}**: {num.get('value')}")
        lines.append("")
    if research.get("primary_source_url"):
        lines += [f"İlkin mənbə: {research['primary_source_url']}", ""]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def remove(item: queue.Item) -> bool:
    """Arxiv qeydini silir — post LinkedIn-dən götürüləndə.

    Arxiv «yayımlanmış postlar» siyahısıdır. Silinmiş post orada
    qalarsa, sonrakı təhlil (hansı mövzu işlədi) mövcud olmayan
    postu sayar. MÜTLƏQ `published_at` təmizlənməzdən ƏVVƏL çağırın:
    fayl yolu həmin tarixdən qurulur.
    """
    path = path_for(item)
    if not path.exists():
        return False
    path.unlink()
    rebuild_index()
    return True


def rebuild_index() -> "config.pathlib.Path":
    """Xronoloji indeks — arxivə baxmaq üçün giriş nöqtəsi."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for path in sorted(ARCHIVE_DIR.rglob("*.md"), reverse=True):
        if path.name == "INDEX.md":
            continue
        head = path.read_text(encoding="utf-8")[:900]
        title = re.search(r'^title:\s*"(.*)"', head, re.M)
        date = re.search(r"^date:\s*(\S+)", head, re.M)
        url = re.search(r"^linkedin:\s*(\S+)", head, re.M)
        rel = path.relative_to(ARCHIVE_DIR).as_posix()
        label = title.group(1) if title else path.stem
        day = (date.group(1)[:10] if date else "")
        link = f" · [LinkedIn]({url.group(1)})" if url and url.group(1) else ""
        entries.append(f"- `{day}` [{label}]({rel}){link}")

    INDEX.write_text(
        "# Post arxivi\n\n"
        f"Cəmi: **{len(entries)}** post\n\n" + "\n".join(entries) + "\n",
        encoding="utf-8",
    )
    return INDEX


def prune() -> list:
    """Artıq yayımda olmayan postların arxiv faylını silir.

    10.09.2026: istifadəçi bir postu LinkedIn-dən sildi, növbədə status
    `skipped` oldu, ARXİVDƏ isə qaldı — indeks 3 post göstərdi, reallıqda
    2 idi. `sync_all` yalnız əlavə edirdi, `rebuild_index` isə diskdəki
    bütün faylları sayırdı, ona görə silinmiş post arxivdə əbədi qalırdı.

    Yalnız növbədə MÖVCUD olan, amma artıq `published` olmayan postlara
    toxunuruq — növbədən tamamilə çıxarılmış köhnə arxivlər qorunur.
    """
    # DİQQƏT: `path_for()` yalnız tarix+başlıqdan qurulur, unikal DEYİL.
    # İki item (məsələn yenidən yazılmış post) eyni fayla düşə bilər.
    # Ona görə əvvəlcə saxlanacaq yolları toplayırıq — yayımdakı bir
    # postun faylını başqa item-in statusuna görə silmək olmaz.
    keep = {path_for(i) for i in queue.by_status(queue.PUBLISHED)}
    removed = []
    for item in queue.all_items():
        if item.status == queue.PUBLISHED:
            continue
        path = path_for(item)
        if path in keep or not path.exists():
            continue
        path.unlink()
        removed.append(path.name)
    return removed


def sync_all() -> int:
    """Növbəni arxivlə uyğunlaşdırır: yayımlananları yazır, qalanları silir."""
    count = 0
    for item in queue.by_status(queue.PUBLISHED):
        write(item)
        count += 1
    prune()
    rebuild_index()
    return count

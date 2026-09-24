"""Postun həyat dövrü: qaralama → təsdiq gözləyir → bank → cədvəl → yayımlandı.

Bank layihənin əsas fikridir: təsdiqlədiyiniz postlar yığılır və zəif
xəbər günü oradan yayımlanır. LinkedIn ardıcıllığı mükafatlandırır —
"bu gün yaxşı xəbər yoxdur" heç vaxt "bu gün post yoxdur" olmamalıdır.
"""
from __future__ import annotations

import json
import pathlib
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Iterable

from . import config, store

QUEUE = config.STATE_DIR / "queue.json"

PENDING = "pending"        # Telegram-a göndərilib, cavab gözlənilir
EDITING = "editing"        # istifadəçi mətn düzəlişi yazır
APPROVED = "approved"      # bankda, cədvələ salınmayıb
SCHEDULED = "scheduled"    # yayım vaxtı təyin olunub
PUBLISHING = "publishing"   # API çağırışı gedir — təkrar cəhd TƏHLÜKƏLİDİR
PUBLISHED = "published"
SKIPPED = "skipped"

OPEN_STATES = (PENDING, EDITING)
BANK_STATES = (APPROVED, SCHEDULED)
TERMINAL_STATES = (PUBLISHED, SKIPPED)


@dataclass
class Item:
    id: str
    status: str = PENDING
    post: str = ""
    first_comment: str = ""
    hashtags: list = field(default_factory=list)
    image_path: str = ""
    image_rung: int = 0
    # Göstərilən kartın NÖMRƏSİ — pillədən ayrıdır və heç vaxt təkrarlanmır.
    # Pillə kifayət etmirdi: zəncirin sonundakı AI pilləsi təkrar-təkrar
    # icra olunur, yəni iki FƏRQLİ kartın pilləsi eyni olur (24.09.2026).
    image_card: int = 0
    image_label: str = ""
    # Foto mənbəyinin atribusiyası. Openverse/Wikimedia şəkilləri
    # BY-SA lisenziyalıdır — atribusiya MƏCBURİDİR, yoxsa lisenziya
    # pozulur. İlk şərhə əlavə olunur (11.09.2026).
    image_credit: str = ""
    alt_text: str = ""
    chosen: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    scheduled_for: str | None = None
    telegram_message_id: int | None = None
    linkedin_url: str = ""
    linkedin_urn: str = ""
    published_at: str | None = None
    reminders_sent: list = field(default_factory=list)
    # Nəticə göstəriciləri — LinkedIn API vermir, istifadəçi özü yazır
    metrics: dict = field(default_factory=dict)
    metrics_requested_at: str | None = None
    # Aşağıdakılar növbəni özü-özünə yetərli edir: GitHub Actions-da
    # `respond` və `publish` işləri `prepare`-in müvəqqəti fayllarını
    # görmür, ona görə lazım olan hər şey elementin içində saxlanılır.
    research: dict = field(default_factory=dict)
    angles: list = field(default_factory=list)
    chosen_angle_id: int | None = None
    director: dict = field(default_factory=dict)
    history: list = field(default_factory=list)

    def note(self, action: str, detail: str = "") -> None:
        self.updated_at = _now().isoformat()
        self.history.append({"at": self.updated_at, "action": action, "detail": detail[:200]})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _read() -> list[dict]:
    return (store.read_json(QUEUE, {}) or {}).get("items", [])


def _write(items: Iterable[dict]) -> None:
    store.write_json(QUEUE, {"items": list(items)})


_FIELDS = {f.name for f in __import__("dataclasses").fields(Item)}


def _to_item(row: dict) -> Item:
    """Naməlum sahələri atır.

    Sxem dəyişəndə (sahə əlavə/silinəndə) köhnə `queue.json` sistemi
    sındırmamalıdır — vəziyyət faylı koddan uzun yaşayır.
    """
    return Item(**{k: v for k, v in row.items() if k in _FIELDS})


def all_items() -> list[Item]:
    return [_to_item(row) for row in _read()]


def get(item_id: str) -> Item | None:
    for item in all_items():
        if item.id == item_id:
            return item
    return None


def save(item: Item) -> Item:
    rows = _read()
    payload = asdict(item)
    for index, row in enumerate(rows):
        if row.get("id") == item.id:
            rows[index] = payload
            break
    else:
        rows.append(payload)
    _write(rows)
    return item


IMAGES_DIR = config.STATE_DIR / "images"


def _persist_image(item_id: str, source: str, suffix: str = "") -> str:
    """Şəkli `state/images/` altına köçürür (repo-ya commit olunur).

    `out/` qovluğu git-ə düşmür; yayım işi başqa qaçışda olduğu üçün
    şəkil davamlı yerdə saxlanılmalıdır.

    `suffix` verilsə ayrıca nüsxə yaranır (`<id>-c2.png`). Bu, göstərilən
    hər kartı toxunulmaz saxlamaq üçündür: `out/` altındakı fayl adı
    pilləyə görədir, ona görə eyni pillə təkrar icra olunanda əvvəlki
    kartın faylı ÜSTÜNDƏN yazılırdı.
    """
    import shutil

    src = pathlib.Path(source)
    if not src.exists():
        return ""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    dst = IMAGES_DIR / f"{item_id}{suffix}.png"
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    return str(dst)


# Bu sahələr yalnız post AKTİV olarkən lazımdır (yenidən yazma, şəkil
# zənciri). Bitmiş postda saxlanılsa fayl 100 postda 1.2 MB-a çatır.
_HEAVY_FIELDS = ("research", "angles", "director")


def compact(keep_days: int = 7) -> int:
    """Bitmiş postların ağır sahələrini təmizləyir.

    Post mətni, ballar, LinkedIn linki və tarixçə qalır — hesabat və
    arxiv üçün lazımdır. Silinən yalnız aktiv iş üçün lazım olan
    aralıq məlumatdır.
    """
    cutoff = _now() - timedelta(days=keep_days)
    rows, cleaned = _read(), 0
    for row in rows:
        if row.get("status") not in TERMINAL_STATES:
            continue
        when = _parse(row.get("updated_at") or row.get("created_at"))
        if when and when > cutoff:
            continue
        if any(row.get(f) for f in _HEAVY_FIELDS):
            for field_name in _HEAVY_FIELDS:
                row[field_name] = {} if field_name != "angles" else []
            cleaned += 1
    if cleaned:
        _write(rows)
    return cleaned


def prune_workdir(keep_days: int = 14) -> int:
    """`out/` qovluğunu təmizləyir — orada işçi fayllar yığılır.

    Arxiv və `state/` toxunulmur: onlar daimidir. Silinən yalnız
    aralıq render fayllarıdır.
    """
    import shutil

    cutoff = _now() - timedelta(days=keep_days)
    removed = 0
    for path in list(config.OUT_DIR.rglob("*")):
        if not path.exists() or path.name == ".gitkeep":
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        if mtime >= cutoff:
            continue
        try:
            if path.is_dir():
                if not any(path.iterdir()):
                    path.rmdir()
                    removed += 1
            else:
                path.unlink()
                removed += 1
        except OSError:
            continue
    # boşalmış qovluqları yığışdır
    for path in sorted(config.OUT_DIR.rglob("*"), key=lambda p: -len(p.parts)):
        if path.is_dir() and not any(path.iterdir()):
            try:
                path.rmdir()
            except OSError:
                pass
    return removed


def prune_runs(keep: int = 20) -> int:
    """Yalnız son N qaçış faylını saxlayır (replay üçün kifayətdir)."""
    files = sorted(config.RUNS_DIR.glob("*.json"))
    removed = 0
    for path in files[:-keep] if len(files) > keep else []:
        path.unlink(missing_ok=True)
        removed += 1
    return removed


# `<id>-c3.png` — təsdiq zamanı göstərilən kartın nüsxəsi.
_CARD_FILE = re.compile(r"^(?P<item>.+)-c\d+$")


def prune_images(keep_days: int = 30) -> int:
    """Köhnə şəkilləri silir ki, repo şişməsin.

    İki fərqli fayl növü var:

    * `<id>.png` — yayımlanan şəkil. Arxiv və hesabat üçün lazımdır,
      ona görə `keep_days` qədər saxlanılır.
    * `<id>-cN.png` — təsdiq gedişində göstərilmiş kartlar. Bunlar İŞÇİ
      fayllardır: yalnız «kart #N-ə qayıt» düyməsi üçün lazımdır, yəni
      post aktiv olduğu müddətdə. Post bitəndə dərhal silinirlər —
      yoxsa hər postdan 4-6 ədəd (~1 MB) repoda yığılardı.
    """
    if not IMAGES_DIR.exists():
        return 0
    cutoff = _now() - timedelta(days=keep_days)
    live = {i.id for i in all_items() if i.status not in TERMINAL_STATES}
    removed = 0
    for path in IMAGES_DIR.glob("*.png"):
        card = _CARD_FILE.match(path.stem)
        if card:
            if card.group("item") not in live:
                path.unlink(missing_ok=True)
                removed += 1
            continue
        if path.stem in live:
            continue
        if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def enqueue(*, item_id: str, post: str, first_comment: str, hashtags: list,
            chosen: dict, scores: dict, image_path: str = "",
            image_rung: int = 0, image_card: int = 0, image_label: str = "",
            alt_text: str = "", image_credit: str = "",
            research: dict | None = None, angles: list | None = None,
            chosen_angle_id: int | None = None, director: dict | None = None) -> Item:
    existing = get(item_id)
    if existing:
        return existing
    item = Item(
        id=item_id, status=PENDING, post=post, first_comment=first_comment,
        hashtags=hashtags, chosen=chosen, scores=scores,
        image_path=_persist_image(item_id, image_path) if image_path else "",
        image_rung=image_rung, image_label=image_label, alt_text=alt_text,
        image_card=image_card,
        image_credit=image_credit,
        research=research or {}, angles=angles or [],
        chosen_angle_id=chosen_angle_id, director=director or {},
        created_at=_now().isoformat(),
    )
    item.note("created", chosen.get("title", "")[:80])
    return save(item)


def by_status(*states: str) -> list[Item]:
    return [i for i in all_items() if i.status in states]


def open_items() -> list[Item]:
    return by_status(*OPEN_STATES)


def bank() -> list[Item]:
    """Təsdiqlənmiş, hələ yayımlanmamış postlar — köhnədən yeniyə."""
    return sorted(by_status(*BANK_STATES), key=lambda i: i.created_at)


def set_status(item: Item, status: str, detail: str = "") -> Item:
    item.status = status
    item.note(status, detail)
    return save(item)


# --- yayım vaxtı ------------------------------------------------------

def next_slot(now: datetime | None = None, *, jitter: bool = True) -> datetime:
    """Növbəti yayım pəncərəsi.

    Saat YERLİ vaxtla hesablanır (PUBLISH_HOUR), nəticə isə UTC-də
    saxlanılır. Hazırlıq və yayım vaxtı ayrıdır: siz səhər
    təsdiqləyirsiniz, sistem auditoriyanın aktiv olduğu saatda
    yayımlayır. ±20 dəqiqəlik təsadüfi sapma robot izini silir.
    """
    from . import timefmt

    now = now or _now()
    tz = timezone.utc if config.PUBLISH_HOUR_IS_UTC else timefmt._tz()
    local_now = now.astimezone(tz)
    slot = datetime.combine(
        local_now.date(), time(hour=config.PUBLISH_HOUR), tzinfo=tz
    )
    if slot <= local_now + timedelta(minutes=10):
        slot += timedelta(days=1)
    while slot.weekday() >= 5 and not config.PUBLISH_WEEKENDS:
        slot += timedelta(days=1)
    if jitter:
        slot += timedelta(minutes=random.randint(-20, 20))
    return slot.astimezone(timezone.utc)


def schedule(item: Item, when: datetime | None = None) -> Item:
    when = when or next_slot()
    item.scheduled_for = when.isoformat()
    item.status = SCHEDULED
    item.note("scheduled", when.isoformat())
    return save(item)


def due(now: datetime | None = None) -> list[Item]:
    """Yayım vaxtı çatmış postlar."""
    now = now or _now()
    out = []
    for item in by_status(SCHEDULED):
        if not item.scheduled_for:
            continue
        try:
            when = datetime.fromisoformat(item.scheduled_for)
        except ValueError:
            continue
        if when <= now:
            out.append(item)
    return sorted(out, key=lambda i: i.scheduled_for or "")


def stats() -> dict:
    items = all_items()
    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "total": len(items),
        "by_status": counts,
        "bank_size": len(bank()),
        "open": len(open_items()),
    }

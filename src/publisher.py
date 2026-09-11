"""LinkedIn-ə yayım — kilid, ikiqat post qoruması, birinci şərh, geri-al.

İki təhlükəsizlik mexanizmi:

1. **Kilid** — eyni anda iki proses yayım etmir (cron + əl ilə işə salma).
2. **`publishing` statusu** — API çağırışından ƏVVƏL yazılır. Proses həmin
   anda ölsə, post LinkedIn-də yaranmış ola bilər; sistem avtomatik təkrar
   cəhd ETMİR, sizə xəbər verir. İkiqat post geri qaytarıla bilməz.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from datetime import datetime, timezone

from . import config, linkedin, queue

LOCK = config.STATE_DIR / "publish.lock"
LOCK_STALE_SECONDS = 900
UNDO_WINDOW_MINUTES = 10


class PublishError(RuntimeError):
    pass


class Lock:
    """Sadə fayl kilidi — köhnəlmiş kilid avtomatik təmizlənir."""

    def __enter__(self):
        if LOCK.exists():
            try:
                data = json.loads(LOCK.read_text(encoding="utf-8"))
                age = time.time() - float(data.get("at", 0))
            except (json.JSONDecodeError, OSError, ValueError):
                age = LOCK_STALE_SECONDS + 1
            if age < LOCK_STALE_SECONDS:
                raise PublishError(
                    f"Başqa yayım prosesi işləyir ({age:.0f}s əvvəl başlayıb). "
                    "Gözləyin və ya kilidi silin: state/publish.lock"
                )
            LOCK.unlink(missing_ok=True)
        LOCK.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}),
                        encoding="utf-8")
        return self

    def __exit__(self, *exc):
        LOCK.unlink(missing_ok=True)
        return False


def stuck_items() -> list[queue.Item]:
    """`publishing` vəziyyətində ilişib qalmış postlar — əl ilə yoxlanmalıdır."""
    return queue.by_status(queue.PUBLISHING)


def score_block(item: queue.Item) -> str:
    """Aşağı ballı postun təsadüfən yayımlanmasının qarşısını alır.

    Reviewer öz çıxışına aşağı bal veribsə, adətən real problem var
    (faktsız mətn, zəif hook). Belə postu yayımlamaq üçün açıq
    --force lazımdır.
    """
    overall = (item.scores or {}).get("overall")
    if overall is None:
        return ""
    if overall < config.MIN_PUBLISH_SCORE:
        return (f"«{item.chosen.get('title', item.id)[:40]}» balı {overall}/10 "
                f"(minimum {config.MIN_PUBLISH_SCORE}). Yayım üçün --force lazımdır.")
    return ""


def with_photo_credit(item: queue.Item) -> str:
    """İlk şərh + foto atribusiyası.

    Openverse/Wikimedia şəkilləri çox vaxt BY-SA lisenziyalıdır və
    atribusiya MƏCBURİDİR. 11.09.2026-a qədər `credit` sahəsi doldurulur,
    amma heç yerdə göstərilmirdi — yəni lisenziya pozula bilərdi.
    """
    parts = [item.first_comment.strip()] if item.first_comment else []
    credit = (getattr(item, "image_credit", "") or "").strip()
    if credit:
        parts.append(f"Foto: {credit}")
    return "\n\n".join(p for p in parts if p)


def publish_item(item: queue.Item, token: linkedin.Token, *,
                 dry_run: bool = False, draft: bool = False,
                 force: bool = False) -> dict:
    """Bir postu yayımlayır. Qaytarır: {urn, url, comment_ok, warnings}.

    `draft=True` — bütün API zənciri işləyir, amma post LinkedIn-də
    qaralama kimi qalır. Növbədəki status DƏYİŞMİR, ona görə sonra
    real yayım normal şəkildə edilə bilər.
    """
    if not draft and (item.status == queue.PUBLISHED or item.linkedin_urn):
        raise PublishError(f"«{item.id}» artıq yayımlanıb: {item.linkedin_url}")
    if item.status == queue.PUBLISHING:
        raise PublishError(
            f"«{item.id}» yarımçıq yayım vəziyyətindədir. LinkedIn profilinizi "
            "yoxlayın: post yaranıbsa `make li-mark` ilə qeyd edin, "
            "yaranmayıbsa statusu `approved`-a qaytarın."
        )

    blocked = score_block(item)
    if blocked and not force and not draft:
        raise PublishError(blocked)

    # Son qoruyucu: pick_due atlansa belə sürət həddi tətbiq olunur
    if not draft and not force:
        limited = rate_limit_block()
        if limited:
            raise PublishError(f"Sürət həddi: {limited}")

    warnings: list[str] = []
    if dry_run:
        return {"urn": "dry-run", "url": "", "comment_ok": True,
                "warnings": ["quru rejim — LinkedIn-ə heç nə göndərilmədi"]}

    image_urn = ""
    if item.image_path and pathlib.Path(item.image_path).exists():
        try:
            image_urn = linkedin.upload_image(token, pathlib.Path(item.image_path))
        except linkedin.LinkedInError as exc:
            warnings.append(f"şəkil yüklənmədi, mətn kimi yayımlanır: {exc}")
    elif item.image_path:
        warnings.append("şəkil faylı tapılmadı")

    if draft:
        urn = linkedin.create_post(
            token, item.post, image_urn=image_urn,
            alt_text=item.alt_text, draft=True,
        )
        item.note("linkedin_draft", urn)
        queue.save(item)
        return {
            "urn": urn, "url": "", "comment_ok": True, "draft": True,
            "warnings": warnings + [
                "QARALAMA rejimi — post ictimai deyil, status dəyişmədi"
            ],
        }

    # KRİTİK: API çağırışından əvvəl vəziyyəti diskə yazırıq.
    queue.set_status(item, queue.PUBLISHING, "LinkedIn API çağırışı başlayır")

    urn = linkedin.create_post(
        token, item.post, image_urn=image_urn, alt_text=item.alt_text
    )
    # URN dərhal saxlanılır — bundan sonra təkrar post mümkün deyil.
    item.linkedin_urn = urn
    item.linkedin_url = linkedin.post_url(urn)
    item.published_at = datetime.now(timezone.utc).isoformat()
    queue.save(item)

    comment_ok = True
    body = with_photo_credit(item)
    if body:
        try:
            linkedin.add_comment(token, urn, body)
        except linkedin.LinkedInError as exc:
            comment_ok = False
            warnings.append(f"birinci şərh əlavə edilmədi: {exc}")

    queue.set_status(item, queue.PUBLISHED, urn)

    # Arxiv: post daimi saxlanılır (növbə sonra təmizlənir)
    try:
        from . import archive

        archive.write(queue.get(item.id) or item)
        archive.rebuild_index()
    except Exception as exc:  # noqa: BLE001 — arxiv yayımı bloklamamalıdır
        warnings.append(f"arxivə yazıla bilmədi: {exc}")

    return {"urn": urn, "url": item.linkedin_url,
            "comment_ok": comment_ok, "warnings": warnings}


def published_today(now: datetime | None = None) -> list[queue.Item]:
    """Bu gün (YERLİ vaxtla) yayımlanmış postlar."""
    from . import timefmt

    today = (timefmt.local(now) or timefmt.now()).date()
    out = []
    for item in queue.by_status(queue.PUBLISHED):
        when = timefmt.local(item.published_at)
        if when and when.date() == today:
            out.append(item)
    return out


def last_published_at(now: datetime | None = None) -> datetime | None:
    times = [
        datetime.fromisoformat(i.published_at)
        for i in queue.by_status(queue.PUBLISHED) if i.published_at
    ]
    times = [t if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in times]
    return max(times) if times else None


def rate_limit_block(now: datetime | None = None) -> str:
    """Sürət həddi pozulursa səbəbi qaytarır, əks halda boş sətir.

    İKİ QORUYUCU:
      1. Gündəlik say — MAX_POSTS_PER_DAY
      2. Postlar arası minimum fasilə — MIN_HOURS_BETWEEN_POSTS

    Bunlar olmasa bank hər tick-də bir post yayımlayır və gün ərzində
    onlarla post çıxa bilər.
    """
    from . import timefmt

    now = now or datetime.now(timezone.utc)
    today = published_today(now)
    if len(today) >= config.MAX_POSTS_PER_DAY:
        return (f"bu gün artıq {len(today)} post yayımlanıb "
                f"(gündəlik hədd: {config.MAX_POSTS_PER_DAY})")

    last = last_published_at(now)
    if last:
        hours = (now - last).total_seconds() / 3600
        if hours < config.MIN_HOURS_BETWEEN_POSTS:
            return (f"son post {hours:.1f} saat əvvəl çıxıb "
                    f"(minimum fasilə: {config.MIN_HOURS_BETWEEN_POSTS:.0f} saat)")
    return ""


def pick_due(*, from_bank: bool = False, now: datetime | None = None,
             ignore_rate_limit: bool = False) -> list[queue.Item]:
    """Yayımlanacaq postlar: vaxtı çatanlar, yoxdursa bankdan ən köhnəsi.

    Sürət həddi pozulursa BOŞ siyahı qaytarır — post növbədə qalır və
    sabah çıxır, itmir.
    """
    if not ignore_rate_limit and rate_limit_block(now):
        return []
    due = queue.due(now)
    if due or not from_bank:
        return due[:1]          # bir qaçışda bir post
    bank = [i for i in queue.bank() if i.status == queue.APPROVED]
    return bank[:1]


def undo(item: queue.Item, token: linkedin.Token) -> None:
    """Geri-al pəncərəsi ərzində postu silir."""
    if not item.linkedin_urn:
        raise PublishError("Bu postun LinkedIn URN-i yoxdur.")
    if item.published_at:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(item.published_at)).total_seconds() / 60
        if age > UNDO_WINDOW_MINUTES * 6:
            raise PublishError(
                f"Post {age:.0f} dəqiqə əvvəl yayımlanıb — avtomatik silmə "
                "pəncərəsi bağlanıb. LinkedIn-dən əl ilə silin."
            )
    linkedin.delete_post(token, item.linkedin_urn)
    item.status = queue.SKIPPED
    item.note("deleted_from_linkedin", item.linkedin_urn)
    item.linkedin_urn, item.linkedin_url = "", ""
    queue.save(item)


def due_reminders(now: datetime | None = None) -> list[tuple[queue.Item, str]]:
    """İlk saatlar çatımı müəyyən edir — şərhlərə baxmaq üçün xatırlatma."""
    now = now or datetime.now(timezone.utc)
    out = []
    for item in queue.by_status(queue.PUBLISHED):
        if not item.published_at:
            continue
        age = (now - datetime.fromisoformat(item.published_at)).total_seconds() / 60
        for label, minutes in (("30dq", 30), ("2saat", 120), ("24saat", 1440)):
            if age >= minutes and label not in item.reminders_sent:
                out.append((item, label))
    return out


def mark_reminded(item: queue.Item, label: str) -> None:
    item.reminders_sent.append(label)
    if label == "24saat":
        item.metrics_requested_at = datetime.now(timezone.utc).isoformat()
    item.note("reminder", label)
    queue.save(item)


def awaiting_metrics() -> queue.Item | None:
    """Nəticəsi soruşulub, amma hələ cavab gəlməmiş ən son post."""
    pending = [i for i in queue.by_status(queue.PUBLISHED)
               if i.metrics_requested_at and not i.metrics]
    pending.sort(key=lambda i: i.metrics_requested_at or "", reverse=True)
    return pending[0] if pending else None


def performance_report(limit: int = 40) -> dict:
    """Hansı rakurs və sütunlar daha çox baxış alır."""
    from collections import defaultdict

    by_angle: dict = defaultdict(list)
    by_pillar: dict = defaultdict(list)
    rows = [i for i in queue.by_status(queue.PUBLISHED) if i.metrics.get("views")]
    for item in rows[-limit:]:
        views = item.metrics["views"]
        angle = ""
        for a in item.angles or []:
            if a.get("id") == item.chosen_angle_id:
                angle = a.get("type", "")
        if angle:
            by_angle[angle].append(views)
        pillar = item.chosen.get("pillar")
        if pillar:
            by_pillar[pillar].append(views)

    def summarise(bucket):
        return sorted(
            ({"key": k, "n": len(v), "avg": round(sum(v) / len(v))}
             for k, v in bucket.items()),
            key=lambda x: -x["avg"])

    return {"samples": len(rows), "by_angle": summarise(by_angle),
            "by_pillar": summarise(by_pillar)}

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
from datetime import datetime, timedelta, timezone

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
    if item.first_comment:
        try:
            linkedin.add_comment(token, urn, item.first_comment)
        except linkedin.LinkedInError as exc:
            comment_ok = False
            warnings.append(f"birinci şərh əlavə edilmədi: {exc}")

    queue.set_status(item, queue.PUBLISHED, urn)
    return {"urn": urn, "url": item.linkedin_url,
            "comment_ok": comment_ok, "warnings": warnings}


def pick_due(*, from_bank: bool = False, now: datetime | None = None) -> list[queue.Item]:
    """Yayımlanacaq postlar: vaxtı çatanlar, yoxdursa bankdan ən köhnəsi."""
    due = queue.due(now)
    if due or not from_bank:
        return due
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
        for label, minutes in (("30dq", 30), ("2saat", 120)):
            if age >= minutes and label not in item.reminders_sent:
                out.append((item, label))
    return out


def mark_reminded(item: queue.Item, label: str) -> None:
    item.reminders_sent.append(label)
    item.note("reminder", label)
    queue.save(item)

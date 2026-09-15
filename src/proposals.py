"""Mövzu təklifləri — post yazılmazdan ƏVVƏL sizin seçiminiz.

Köhnə axın: Scout seçir → sistem 90k token xərcləyib yazır → siz bəyənmirsiniz.
Yeni axın: Scout 3 namizəd verir → siz birinə basırsınız → yalnız sonra yazılır.

İki qazanc: nəticəni bəyənmə ehtimalı artır, kvota isə azalır.

Cavab verməsəniz sistem `AUTO_PICK_HOURS` sonra özü seçir — post günü
boş keçmir.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from . import config, store

STORE = config.STATE_DIR / "proposals.json"
AUTO_PICK_HOURS = float(os.environ.get("AUTO_PICK_HOURS", "3"))

OPEN = "open"
PICKED = "picked"
EXPIRED = "expired"


@dataclass
class Proposal:
    id: str
    created_at: str
    status: str = OPEN
    candidates: list = field(default_factory=list)   # scout-un 3 namizədi
    items: list = field(default_factory=list)        # xam xəbərlər (replay üçün)
    telegram_message_id: int | None = None
    picked_index: int | None = None
    picked_by: str = ""                              # "user" | "auto"
    warnings: list = field(default_factory=list)     # istifadəçiyə görünən qüsurlar


def _read() -> list[dict]:
    return (store.read_json(STORE, {}) or {}).get("proposals", [])


def _write(rows) -> None:
    store.write_json(STORE, {"proposals": list(rows)[-30:]})


def all_proposals() -> list[Proposal]:
    return [Proposal(**row) for row in _read()]


def get(pid: str) -> Proposal | None:
    for row in _read():
        if row.get("id") == pid:
            return Proposal(**row)
    return None


def save(proposal: Proposal) -> Proposal:
    rows = _read()
    payload = asdict(proposal)
    for index, row in enumerate(rows):
        if row.get("id") == proposal.id:
            rows[index] = payload
            break
    else:
        rows.append(payload)
    _write(rows)
    return proposal


def create(candidates: list, items: list, warnings: list | None = None) -> Proposal:
    proposal = Proposal(
        id=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S"),
        created_at=datetime.now(timezone.utc).isoformat(),
        candidates=candidates[:3], items=items, warnings=list(warnings or []),
    )
    return save(proposal)


def prepared_today(now: datetime | None = None) -> bool:
    """Bu gün post hazırlanıb, yaxud namizəd dəsti göndərilibmi.

    Lokal cron bunu yoxlayır: GitHub Actions artıq işləyibsə, ikinci
    dəfə hazırlamağa ehtiyac yoxdur.

    YALNIZ növbəyə baxmaq KİFAYƏT ETMİR — `propose` növbəyə item yazmır,
    yalnız təklif yaradır. Əvvəllər qoruma yalnız `queue.json`-a baxırdı,
    ona görə CI namizədləri göndərəndən sonra lokal ehtiyat ikinci dəst
    göndərə bilərdi.

    Gün sərhədi YERLİ vaxtla hesablanır — cron da yerli vaxtla işləyir
    (09:30 Bakı). UTC-yə baxsaq, gecə yarısı ətrafında gün sərhədi
    sürüşür. `publisher.published_today` da eyni naxışı işlədir.
    """
    from . import queue, timefmt

    day = (timefmt.local(now) or timefmt.now()).date()

    def same_day(stamp: str) -> bool:
        when = timefmt.local(stamp)
        return bool(when and when.date() == day)

    if any(same_day(i.created_at) for i in queue.all_items()):
        return True
    return any(same_day(p.created_at) for p in all_proposals())


def open_proposals() -> list[Proposal]:
    return [p for p in all_proposals() if p.status == OPEN]


def due_for_auto_pick(now: datetime | None = None) -> list[Proposal]:
    """Cavabsız qalmış təkliflər — sistem özü seçməlidir."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=AUTO_PICK_HOURS)
    out = []
    for proposal in open_proposals():
        try:
            created = datetime.fromisoformat(proposal.created_at)
        except ValueError:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created <= cutoff:
            out.append(proposal)
    return out


def mark_picked(proposal: Proposal, index: int, by: str = "user") -> Proposal:
    proposal.status = PICKED
    proposal.picked_index = index
    proposal.picked_by = by
    return save(proposal)


def expire(proposal: Proposal) -> Proposal:
    proposal.status = EXPIRED
    return save(proposal)

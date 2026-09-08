"""Davamlı yaddaş: görülmüş xəbərlər, keçmiş tezislər, sütun balansı, qaçış logları.

Hamısı JSON — repo-ya commit olunur, ayrıca baza lazım deyil.
`theses` mövzu təkrarını yox, ARQUMENT təkrarını tutmaq üçündür:
eyni fikri fərqli xəbərlə üç dəfə desəniz, auditoriya bunu hiss edir.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config, store

SEEN = config.STATE_DIR / "seen.json"
THESES = config.STATE_DIR / "theses.json"


def _read(path, default):
    return store.read_json(path, default)


def _write(path, payload) -> None:
    store.write_json(path, payload)


# --- görülmüş xəbərlər -------------------------------------------------

def seen_urls() -> dict[str, Any]:
    return _read(SEEN, {})


def is_seen(url: str) -> bool:
    return url in seen_urls()


def mark_seen(url: str, title: str = "") -> None:
    data = seen_urls()
    data[url] = {"date": datetime.now(timezone.utc).isoformat(), "title": title[:200]}
    # 120 gündən köhnələri təmizləyirik ki, fayl şişməsin
    cutoff = datetime.now(timezone.utc) - timedelta(days=120)
    data = {
        u: v for u, v in data.items()
        if _parse(v.get("date")) is None or _parse(v.get("date")) > cutoff
    }
    _write(SEEN, data)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# --- tezislər və sütun balansı ----------------------------------------

def theses(limit: int = 30) -> list[dict]:
    return _read(THESES, [])[-limit:]


def add_thesis(*, thesis: str, topic: str, pillar: str, url: str) -> None:
    data = _read(THESES, [])
    data.append({
        "date": datetime.now(timezone.utc).isoformat(),
        "thesis": thesis[:300],
        "topic": topic[:200],
        "pillar": pillar,
        "url": url,
    })
    _write(THESES, data[-200:])


def pillar_balance(days: int | None = None) -> dict[str, int]:
    """Son N gündə hansı sütundan neçə post çıxıb."""
    days = days or config.PILLAR_WINDOW_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    counts = {key: 0 for key in config.PILLARS}
    for row in _read(THESES, []):
        when = _parse(row.get("date"))
        if when and when > cutoff and row.get("pillar") in counts:
            counts[row["pillar"]] += 1
    return counts


# --- qaçış logları (telemetriya) --------------------------------------

def record_run(run_id: str, payload: dict) -> None:
    _write(config.RUNS_DIR / f"{run_id}.json", payload)


def usage_report(days: int = 7) -> dict:
    """Həftəlik hesabat üçün real token/xərc yekunu."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    runs, tokens, cost = 0, 0, 0.0
    for path in sorted(config.RUNS_DIR.glob("*.json")):
        data = _read(path, {})
        when = _parse(data.get("started_at"))
        if not when or when < cutoff:
            continue
        runs += 1
        for agent in data.get("agents", []):
            tokens += agent.get("total_tokens", 0)
            cost += agent.get("cost_usd", 0.0)
    return {"days": days, "runs": runs, "tokens": tokens, "cost_usd": round(cost, 4)}

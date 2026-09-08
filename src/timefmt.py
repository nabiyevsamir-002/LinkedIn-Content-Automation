"""Vaxtın istifadəçi üçün oxunaqlı formatı.

Sistem daxildə həmişə UTC işlədir (bu, düzgündür — cron, müqayisə,
saxlama). Amma istifadəçi UTC oxumamalıdır: bütün mesajlarda
yerli vaxt göstərilir.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

TZ_NAME = os.environ.get("TIMEZONE", "Asia/Baku")

WEEKDAYS = ("bazar ertəsi", "çərşənbə axşamı", "çərşənbə", "cümə axşamı",
            "cümə", "şənbə", "bazar")
MONTHS = ("yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
          "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr")


def _tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(TZ_NAME)
    except Exception:  # noqa: BLE001 — tzdata yoxdursa sabit sürüşmə
        return timezone(timedelta(hours=4))      # Bakı: UTC+4, yay vaxtı yoxdur


def local(value: datetime | str | None) -> datetime | None:
    """UTC vaxtı yerli zonaya çevirir."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_tz())


def now() -> datetime:
    return datetime.now(_tz())


def fmt(value: datetime | str | None, *, with_weekday: bool = True,
        reference: datetime | None = None) -> str:
    """«sabah 12:15» / «çərşənbə, 12:15» kimi format.

    `reference` — «indi» sayılan an. Yalnız testlər üçün verilir;
    normal işdə cari vaxt götürülür.
    """
    dt = local(value)
    if dt is None:
        return "—"
    today = (local(reference) or now()).date()
    delta = (dt.date() - today).days
    clock = dt.strftime("%H:%M")

    if delta == 0:
        return f"bu gün {clock}"
    if delta == 1:
        return f"sabah {clock}"
    if delta == -1:
        return f"dünən {clock}"
    if 0 < delta <= 6 and with_weekday:
        return f"{WEEKDAYS[dt.weekday()]}, {clock}"
    return f"{dt.day} {MONTHS[dt.month - 1]}, {clock}"


def short(value: datetime | str | None) -> str:
    """«09.09 12:15» — cədvəl və siyahılar üçün."""
    dt = local(value)
    return dt.strftime("%d.%m %H:%M") if dt else "—"


def label() -> str:
    """Zonanın qısa adı — «Bakı vaxtı»."""
    city = TZ_NAME.split("/")[-1].replace("_", " ")
    return {"Baku": "Bakı"}.get(city, city) + " vaxtı"

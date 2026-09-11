"""Telegram bildirişləri — xətalar səssiz qalmamalıdır.

Sistemin ən pis davranışı səssiz sınmaqdır: siz gözləyirsiniz, heç nə
gəlmir, səbəbi bilmirsiniz. Burada hər uğursuzluq Telegram-a çatır.
"""
from __future__ import annotations

import html
import os
import traceback

from . import config, store


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


# Eyni xəta imzası bu müddət ərzində yalnız bir dəfə göndərilir.
# Bildiriş sistemi spam edərsə, ondan heç olmaması yaxşıdır.
THROTTLE_SECONDS = int(os.environ.get("NOTIFY_THROTTLE_SECONDS", "1800"))
THROTTLE_FILE = config.STATE_DIR / "notify_throttle.json"


# Bəzi bildirişlər daha nadir olmalıdır (məs. gündəlik token xəbərdarlığı)
LONG_THROTTLE = {"linkedin-expiry": 86400, "ci-down": 21600}


def _throttled(signature: str) -> bool:
    """True qaytarırsa — bu xəta bu yaxınlarda göndərilib, təkrarlamırıq.

    Vəziyyət DİSKDƏ saxlanılır: GitHub Actions hər dəfə yeni proses
    işə salır, yaddaşdakı throttle isə orada heç vaxt işləməzdi —
    hər 15 dəqiqəlik tick eyni xətanı yenidən göndərərdi.
    """
    import json
    import time

    now = time.time()
    data = store.read_json(THROTTLE_FILE, {}) or {}

    window = LONG_THROTTLE.get(signature, THROTTLE_SECONDS)
    last = float(data.get(signature, 0))
    if now - last < window:
        return True

    data[signature] = now
    # Köhnə qeydləri təmizləyirik ki, fayl şişməsin
    data = {k: v for k, v in data.items()
            if now - float(v) < max(THROTTLE_SECONDS * 4, max(LONG_THROTTLE.values(), default=0) * 2)}
    try:
        store.write_json(THROTTLE_FILE, data, indent=None)
    except OSError:
        pass
    return False


def send(text: str) -> bool:
    """Bildiriş göndərir. Özü sınsa səssiz qalır (sonsuz döngə olmasın)."""
    try:
        from . import telegram

        if not telegram.available():
            return False
        telegram.Bot().send_message(text)
        return True
    except Exception:  # noqa: BLE001
        return False


def ci_down(age_seconds: int) -> bool:
    """GitHub Actions uzun müddət siqnal vermirsə xəbər verir.

    11.09.2026: CI iki gün ardıcıl schedule qaçışını atladı, lokal
    ehtiyat işini gördü, amma bunu YALNIZ log bilirdi — istifadəçi
    səhər namizəd gözləyib heç nə almadı və səbəbi görmədi.

    6 saatlıq throttle: hər 15 dəqiqəlik tick-də təkrarlanmır.
    """
    if _throttled("ci-down"):
        return False
    hours = age_seconds / 3600
    return send(
        "⚠️ <b>GitHub Actions cavab vermir</b>\n"
        f"<i>Son siqnal: {hours:.1f} saat əvvəl</i>\n\n"
        "Lokal ehtiyat işini görür — yayım və xatırlatmalar davam edir.\n"
        "Namizədlər də lokal göndərilir, sadəcə bir neçə dəqiqə gec."
    )


def error(title: str, exc: BaseException | None = None, *,
          detail: str = "", command: str = "") -> bool:
    signature = f"{title}|{type(exc).__name__ if exc else ''}|{command}"
    if _throttled(signature):
        return False
    lines = [f"⚠️ <b>{_esc(title)}</b>"]
    if command:
        lines.append(f"<code>{_esc(command)}</code>")
    if exc is not None:
        lines.append("")
        lines.append(f"<b>{type(exc).__name__}</b>: {_esc(str(exc))[:400]}")
        tb = traceback.format_exc(limit=3)
        if tb and "NoneType" not in tb[:30]:
            tail = tb.strip().splitlines()[-3:]
            lines.append("<pre>" + _esc("\n".join(tail))[:500] + "</pre>")
    if detail:
        lines.append("")
        lines.append(_esc(detail)[:600])
    return send("\n".join(lines))


def warn(title: str, detail: str = "") -> bool:
    if _throttled(f"warn|{title}"):
        return False
    text = f"🟡 <b>{_esc(title)}</b>"
    if detail:
        text += f"\n{_esc(detail)[:600]}"
    return send(text)


# --- xarici sağlamlıq monitorinqi -------------------------------------

def healthcheck(state: str = "") -> bool:
    """Healthchecks.io (və ya uyğun) xidmətinə siqnal göndərir.

    `state`: "" (uğur) · "start" · "fail" · "log"

    Xidmət gözlənilən vaxtda siqnal almasa SİZƏ xəbər verir — yəni
    sistem tamamilə dayansa belə (GitHub Actions sınsa, cron işə
    düşməsə) bunu bilirsiniz. Daxili bildirişlər bunu edə bilməz,
    çünki onlar da işləmir.
    """
    url = config.HEALTHCHECK_URL
    if not url:
        return False
    target = url.rstrip("/")
    if state:
        target = f"{target}/{state}"
    try:
        from . import net

        net.request("GET", target, timeout=15)
        return True
    except Exception:  # noqa: BLE001
        return False

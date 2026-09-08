"""Telegram bildirişləri — xətalar səssiz qalmamalıdır.

Sistemin ən pis davranışı səssiz sınmaqdır: siz gözləyirsiniz, heç nə
gəlmir, səbəbi bilmirsiniz. Burada hər uğursuzluq Telegram-a çatır.
"""
from __future__ import annotations

import html
import os
import traceback

from . import config


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


# Eyni xəta imzası bu müddət ərzində yalnız bir dəfə göndərilir.
# Bildiriş sistemi spam edərsə, ondan heç olmaması yaxşıdır.
THROTTLE_SECONDS = int(os.environ.get("NOTIFY_THROTTLE_SECONDS", "1800"))
_LAST_SENT: dict[str, float] = {}


def _throttled(signature: str) -> bool:
    """True qaytarırsa — bu xəta bu yaxınlarda göndərilib, təkrarlamırıq."""
    import time

    now = time.time()
    last = _LAST_SENT.get(signature, 0.0)
    if now - last < THROTTLE_SECONDS:
        return True
    _LAST_SENT[signature] = now
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

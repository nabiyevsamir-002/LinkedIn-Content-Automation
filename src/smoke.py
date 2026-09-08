"""İnteqrasiya sınağı — real API-lar, amma heç nə yayımlanmır.

Oflayn testlər öz kodumuzu yoxlayır. Bu isə **xarici dünyanı** yoxlayır:
LinkedIn API versiyası hələ qüvvədədirmi, Telegram formatı dəyişməyibmi,
RSS mənbələri sağdırmı, şəkil yükləməsi işləyirmi.

Ən dəyərli hissə: LinkedIn-də QARALAMA yaradıb dərhal silir. Bu, yayım
zəncirinin tam yoxlanışıdır — kimlik, şəkil yükləməsi, post yaradılması,
silmə — heç nə ictimai olmadan.
"""
from __future__ import annotations

import pathlib
import time
from dataclasses import dataclass, field

from . import config


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    seconds: float = 0.0


@dataclass
class Result:
    checks: list = field(default_factory=list)

    @property
    def failed(self) -> list:
        return [c for c in self.checks if not c.ok]

    @property
    def ok(self) -> bool:
        return not self.failed


def _timed(name: str, fn) -> Check:
    started = time.time()
    try:
        detail = fn() or ""
        return Check(name, True, str(detail), time.time() - started)
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"{type(exc).__name__}: {exc}"[:200],
                     time.time() - started)


def _sources() -> str:
    from . import sources

    items, errors = sources.fetch_all(max_age_hours=72)
    if len(errors) >= len(sources.FEEDS) / 2:
        raise RuntimeError(f"{len(errors)}/{len(sources.FEEDS)} mənbə əlçatmaz")
    if not items:
        raise RuntimeError("heç bir xəbər alınmadı")
    return f"{len(items)} xəbər, {len(errors)} mənbə problemli"


def _telegram() -> str:
    from . import telegram

    if not telegram.available():
        raise RuntimeError("açarlar yoxdur")
    me = telegram.HttpTransport(config.TELEGRAM_TOKEN).call("getMe", {})
    return f"@{me.get('username')}"


def _photos() -> str:
    from .images import stock

    photos = stock.search("technology office", limit=3)
    if not photos:
        raise RuntimeError("heç bir foto tapılmadı")
    return f"{len(photos)} foto, {len(stock.active_providers())} mənbə"


def _render() -> str:
    from .images import render

    out = config.OUT_DIR / ".smoke" / "render.png"
    render.html_to_png(
        render.wrap('<div style="width:1200px;height:1500px;background:#0b1220;'
                    'color:#fff;padding:88px;font-size:60px">Yoxlama əə ğı öü</div>'),
        out)
    size = out.stat().st_size
    out.unlink(missing_ok=True)
    if size < 5000:
        raise RuntimeError("şəkil çox kiçikdir — render pozulub")
    return f"{size // 1024} KB"


def _claude() -> str:
    from . import llm

    result = llm.call_agent(
        "smoke", "Sən yoxlama agentisən.", "Qısa təsdiq qaytar.",
        model=config.MODEL_SCOUT, retries=0, timeout=120,
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"]})
    if not result.ok:
        raise RuntimeError(result.error or "cavab alınmadı")
    return f"{result.total_tokens} token"


def _linkedin_draft() -> str:
    """Ən vacib yoxlama: qaralama yarat → sil.

    Yayım zəncirinin tam sınağıdır, amma heç nə ictimai olmur.
    """
    from . import linkedin
    from .images import render

    token = linkedin.load_token()
    if not token:
        raise RuntimeError("giriş yoxdur")
    if token.expired:
        raise RuntimeError(f"token bitib ({token.expires_dt:%d.%m.%Y})")

    linkedin.userinfo(token.access_token)          # kimlik

    image_path = config.OUT_DIR / ".smoke" / "li.png"
    render.html_to_png(
        render.wrap('<div style="width:1200px;height:1500px;background:#0b1220;'
                    'color:#fff;padding:88px;font-size:48px">Sistem yoxlaması</div>',
                    brand=False),
        image_path)
    image_urn = linkedin.upload_image(token, image_path)   # şəkil yükləməsi
    image_path.unlink(missing_ok=True)

    urn = linkedin.create_post(                            # post yaradılması
        token, "Sistem yoxlaması — bu qaralama dərhal silinir.",
        image_urn=image_urn, alt_text="yoxlama", draft=True)
    linkedin.delete_post(token, urn)                       # silmə
    return f"qaralama {urn.split(':')[-1]} yaradıldı və silindi"


def _linkedin_version() -> str:
    from . import linkedin

    status = linkedin.version_status()
    if not status["active"]:
        raise RuntimeError("aktiv versiya tapılmadı")
    if not status["current_ok"]:
        raise RuntimeError(
            f"{status['current']} sıradan çıxıb — {status['newest']}-ə keçin")
    if status["upgrade_available"]:
        return f"{status['current']} işləyir · {status['newest']} mövcuddur"
    return f"{status['current']} (ən yenisi)"


CHECKS = [
    ("RSS mənbələri", _sources),
    ("Claude (abunəlik)", _claude),
    ("Şəkil rendering", _render),
    ("Foto mənbələri", _photos),
    ("Telegram", _telegram),
    ("LinkedIn API versiyası", _linkedin_version),
    ("LinkedIn (qaralama→sil)", _linkedin_draft),
]


def run(skip_linkedin: bool = False) -> Result:
    result = Result()
    for name, fn in CHECKS:
        if skip_linkedin and name.startswith("LinkedIn"):
            continue
        result.checks.append(_timed(name, fn))
    return result

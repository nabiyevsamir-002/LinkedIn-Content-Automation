"""LinkedIn API müştərisi — şəxsi profilə post yayımı.

Tələb olunan LinkedIn app məhsulları:
  • Sign In with LinkedIn using OpenID Connect  (kimlik: person URN)
  • Share on LinkedIn                           (w_member_social: yayım)

Diqqət: giriş tokeni **60 gün** yaşayır. Refresh token yalnız təsdiqlənmiş
partnyor app-lərə verilir, ona görə iki ayda bir `make li-auth` işlətmək
lazım gələcək. Sistem 7 gün əvvəldən xəbərdarlıq edir.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import config, net

TOKEN_FILE = config.STATE_DIR / "linkedin.json"

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API_BASE = "https://api.linkedin.com"
USERINFO = f"{API_BASE}/v2/userinfo"

SCOPES = "openid profile w_member_social"
# LinkedIn versiyalı API tələb edir (YYYYMM). Versiyalar müəyyən müddət
# sonra sıradan çıxır — sabit yazılmış versiya bir gün yayımı dayandırar.
# Ona görə aktiv versiya avtomatik aşkarlanır və nəticə keşlənir.
API_VERSION = os.environ.get("LINKEDIN_API_VERSION", "202509")
VERSION_CACHE = config.STATE_DIR / "linkedin_versions.json"
VERSION_TTL_DAYS = 7
REDIRECT_URI = os.environ.get("LINKEDIN_REDIRECT_URI", "http://localhost:8765/callback")

EXPIRY_WARN_DAYS = 7


class LinkedInError(RuntimeError):
    pass


# --- token saxlanması -------------------------------------------------

@dataclass
class Token:
    access_token: str
    person_urn: str
    expires_at: str
    obtained_at: str
    name: str = ""

    @property
    def expires_dt(self) -> datetime:
        return datetime.fromisoformat(self.expires_at)

    @property
    def days_left(self) -> float:
        return (self.expires_dt - datetime.now(timezone.utc)).total_seconds() / 86400

    @property
    def expired(self) -> bool:
        return self.days_left <= 0

    @property
    def expiring_soon(self) -> bool:
        return 0 < self.days_left <= EXPIRY_WARN_DAYS


def save_token(access_token: str, expires_in: int, person_urn: str, name: str = "") -> Token:
    now = datetime.now(timezone.utc)
    token = Token(
        access_token=access_token, person_urn=person_urn,
        expires_at=(now + timedelta(seconds=expires_in)).isoformat(),
        obtained_at=now.isoformat(), name=name,
    )
    TOKEN_FILE.write_text(json.dumps(token.__dict__, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return token


def load_token() -> Token | None:
    """Tokeni fayldan, yoxdursa mühit dəyişənlərindən oxuyur.

    GitHub Actions-da `state/linkedin.json` yoxdur (git-ə düşmür) —
    orada token GitHub Secrets-dən mühit dəyişəni kimi gəlir.
    """
    if TOKEN_FILE.exists():
        try:
            return Token(**json.loads(TOKEN_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    access = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    urn = os.environ.get("LINKEDIN_PERSON_URN", "")
    if access and urn:
        return Token(
            access_token=access, person_urn=urn,
            expires_at=os.environ.get("LINKEDIN_EXPIRES_AT", "")
            or (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
            obtained_at=os.environ.get("LINKEDIN_OBTAINED_AT", ""),
            name=os.environ.get("LINKEDIN_PROFILE_NAME", ""),
        )
    return None


def available() -> bool:
    token = load_token()
    return bool(token and not token.expired)


# --- OAuth ------------------------------------------------------------

def authorize_url(state: str) -> str:
    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
    if not client_id:
        raise LinkedInError("LINKEDIN_CLIENT_ID .env faylında yoxdur.")
    params = urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id,
        "redirect_uri": REDIRECT_URI, "state": state, "scope": SCOPES,
    })
    return f"{AUTH_URL}?{params}"


def exchange_code(code: str) -> Token:
    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        raise LinkedInError("LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET yoxdur.")

    body = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id, "client_secret": client_secret,
    }).encode()
    resp = net.request(
        "POST", TOKEN_URL, body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=60,
    )
    if resp.status != 200:
        raise LinkedInError(f"Token alınmadı ({resp.status}): {resp.body[:300].decode('utf-8', 'replace')}")
    data = resp.json()
    access = data["access_token"]
    profile = userinfo(access)
    urn = f"urn:li:person:{profile['sub']}"
    return save_token(access, int(data.get("expires_in", 5184000)), urn,
                      profile.get("name", ""))


def userinfo(access_token: str) -> dict:
    resp = net.request("GET", USERINFO,
                       headers={"Authorization": f"Bearer {access_token}"}, timeout=45)
    if resp.status != 200:
        raise LinkedInError(f"userinfo uğursuz ({resp.status}): "
                            f"{resp.body[:200].decode('utf-8', 'replace')}")
    return resp.json()


# --- yayım ------------------------------------------------------------

# LinkedIn `commentary` sahəsində bu simvollar tərs-kəsik ilə qorunmalıdır.
# `#` qorunmur — hashtag kimi işləməlidir.
_ESCAPE = r"\|{}@[]()<>*_~"
_ESCAPE_RE = re.compile("([" + re.escape(_ESCAPE) + "])")


def escape_commentary(text: str) -> str:
    return _ESCAPE_RE.sub(r"\\\1", text or "")


def _version_recovery(resp) -> bool:
    """Cavab versiya problemidirsə, yeni versiya aşkarlayıb True qaytarır."""
    if resp.status != 426:
        return False
    body = resp.body[:300].decode("utf-8", "replace")
    if "VERSION" not in body.upper():
        return False
    payload = refresh_versions()
    return bool(payload.get("newest"))


def _headers(token: Token, extra: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token.access_token}",
        "LinkedIn-Version": current_version(),
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def upload_image(token: Token, path: pathlib.Path) -> str:
    """Şəkli yükləyir və `urn:li:image:...` qaytarır."""
    init_body = json.dumps(
        {"initializeUploadRequest": {"owner": token.person_urn}}).encode()
    init = net.request("POST", f"{API_BASE}/rest/images?action=initializeUpload",
                       body=init_body, headers=_headers(token), timeout=90)
    if _version_recovery(init):
        init = net.request("POST", f"{API_BASE}/rest/images?action=initializeUpload",
                           body=init_body, headers=_headers(token), timeout=90)
    if init.status not in (200, 201):
        raise LinkedInError(f"Şəkil yükləməsi başlamadı ({init.status}): "
                            f"{init.body[:300].decode('utf-8', 'replace')}")
    value = init.json().get("value", {})
    upload_url, image_urn = value.get("uploadUrl"), value.get("image")
    if not (upload_url and image_urn):
        raise LinkedInError(f"initializeUpload cavabı natamam: {value}")

    put = net.request(
        "PUT", upload_url, body=pathlib.Path(path).read_bytes(),
        headers={"Authorization": f"Bearer {token.access_token}",
                 "Content-Type": "application/octet-stream"},
        timeout=180,
    )
    if put.status not in (200, 201):
        raise LinkedInError(f"Şəkil yüklənmədi ({put.status})")
    return image_urn


def upload_document(token: Token, path: pathlib.Path) -> str:
    """PDF yükləyir və `urn:li:document:...` qaytarır.

    Karusel postu LinkedIn-də «sənəd postu»dur: PDF yüklənir, lentdə
    sürüşdürülən slaydlar kimi görünür.
    """
    init_body = json.dumps(
        {"initializeUploadRequest": {"owner": token.person_urn}}).encode()
    init = net.request("POST", f"{API_BASE}/rest/documents?action=initializeUpload",
                       body=init_body, headers=_headers(token), timeout=90)
    if _version_recovery(init):
        init = net.request("POST", f"{API_BASE}/rest/documents?action=initializeUpload",
                           body=init_body, headers=_headers(token), timeout=90)
    if init.status not in (200, 201):
        raise LinkedInError(f"Sənəd yükləməsi başlamadı ({init.status}): "
                            f"{init.body[:300].decode('utf-8', 'replace')}")
    value = init.json().get("value", {})
    upload_url, doc_urn = value.get("uploadUrl"), value.get("document")
    if not (upload_url and doc_urn):
        raise LinkedInError(f"initializeUpload cavabı natamam: {value}")

    put = net.request(
        "PUT", upload_url, body=pathlib.Path(path).read_bytes(),
        headers={"Authorization": f"Bearer {token.access_token}",
                 "Content-Type": "application/octet-stream"},
        timeout=300)
    if put.status not in (200, 201):
        raise LinkedInError(f"Sənəd yüklənmədi ({put.status})")
    return doc_urn


def create_post(token: Token, text: str, *, image_urn: str = "",
                alt_text: str = "", draft: bool = False,
                document_urn: str = "", document_title: str = "") -> str:
    """Post yaradır və post URN-ini qaytarır.

    `draft=True` olanda post LinkedIn-də qaralama kimi qalır — lentdə
    görünmür, heç kim görmür. Bütün API zəncirini (kimlik, şəkil
    yükləməsi, post yaradılması) təhlükəsiz yoxlamaq üçündür.
    """
    payload: dict = {
        "author": token.person_urn,
        "commentary": escape_commentary(text),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "DRAFT" if draft else "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if document_urn:
        # Sənəd postu (karusel) — LinkedIn onu sürüşdürülən slaydlar kimi göstərir
        payload["content"] = {"media": {
            "id": document_urn,
            "title": (document_title or "Karusel")[:100],
        }}
    elif image_urn:
        payload["content"] = {"media": {"id": image_urn,
                                        "altText": (alt_text or "")[:300]}}

    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = net.request("POST", f"{API_BASE}/rest/posts", body=body_bytes,
                       headers=_headers(token), timeout=120)
    if _version_recovery(resp):
        # Versiya sıradan çıxıb — yenisi ilə bir dəfə təkrar cəhd
        resp = net.request("POST", f"{API_BASE}/rest/posts", body=body_bytes,
                           headers=_headers(token), timeout=120)
    if resp.status not in (200, 201):
        raise LinkedInError(f"Post yaradılmadı ({resp.status}): "
                            f"{resp.body[:400].decode('utf-8', 'replace')}")
    urn = resp.headers.get("x-restli-id") or resp.headers.get("x-linkedin-id")
    if not urn:
        urn = (resp.json() or {}).get("id", "")
    if not urn:
        raise LinkedInError("Post yarandı, amma URN qaytarılmadı.")
    return urn


def add_comment(token: Token, post_urn: str, text: str) -> str:
    """Birinci şərh — mənbə linki bura gedir (gövdədəki link çatımı boğur)."""
    encoded = urllib.parse.quote(post_urn, safe="")
    resp = net.request(
        "POST", f"{API_BASE}/rest/socialActions/{encoded}/comments",
        body=json.dumps({
            "actor": token.person_urn, "object": post_urn,
            "message": {"text": text},
        }, ensure_ascii=False).encode("utf-8"),
        headers=_headers(token), timeout=90,
    )
    if resp.status not in (200, 201):
        raise LinkedInError(f"Şərh əlavə edilmədi ({resp.status}): "
                            f"{resp.body[:300].decode('utf-8', 'replace')}")
    return resp.headers.get("x-restli-id", "")


def delete_post(token: Token, post_urn: str) -> None:
    encoded = urllib.parse.quote(post_urn, safe="")
    resp = net.request("DELETE", f"{API_BASE}/rest/posts/{encoded}",
                       headers=_headers(token), timeout=90)
    if resp.status not in (200, 204):
        raise LinkedInError(f"Post silinmədi ({resp.status}): "
                            f"{resp.body[:200].decode('utf-8', 'replace')}")


def post_url(post_urn: str) -> str:
    ident = post_urn.split(":")[-1]
    return f"https://www.linkedin.com/feed/update/{post_urn}/" if ident else ""


def expiry_warning() -> str:
    """Token bitməyə yaxındırsa hazır xəbərdarlıq mətni qaytarır."""
    token = load_token()
    if not token:
        return ""
    if token.expired:
        return (
            "🔴 <b>LinkedIn tokeni BİTİB</b>\n\n"
            "Yayım dayanıb. Bərpa etmək üçün terminalda:\n"
            "<code>make li-renew</code>\n\n"
            "<i>Brauzer açılır, təsdiq edirsiniz, GitHub secret-ləri "
            "avtomatik yenilənir.</i>"
        )
    if token.expiring_soon:
        return (
            f"🟡 <b>LinkedIn tokeni {token.days_left:.0f} gün sonra bitir</b>\n"
            f"<i>{token.expires_dt:%d.%m.%Y}</i>\n\n"
            "İndi yeniləsəniz fasilə olmaz:\n"
            "<code>make li-renew</code>"
        )
    return ""


# --- API versiyasının avtomatik aşkarlanması --------------------------

def _probe_version(token: Token, version: str) -> bool:
    """Versiya aktivdirmi?

    LinkedIn cavabları:
      426 NONEXISTENT_VERSION — aktiv deyil
      400 INVALID_VERSION     — format səhvdir
      qalan hər şey (403 daxil) — versiya QƏBUL EDİLDİ
    """
    probe_urn = urllib.parse.quote("urn:li:share:1", safe="")
    resp = net.request(
        "GET", f"{API_BASE}/rest/posts/{probe_urn}",
        headers={
            "Authorization": f"Bearer {token.access_token}",
            "LinkedIn-Version": version,
            "X-Restli-Protocol-Version": "2.0.0",
        }, timeout=30)
    return resp.status not in (426, 400)


def _candidate_versions(months_back: int = 18, months_forward: int = 6) -> list[str]:
    now = datetime.now(timezone.utc)
    out = []
    for offset in range(-months_back, months_forward + 1):
        month = now.month + offset
        year = now.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        out.append(f"{year}{month:02d}")
    return sorted(set(out))


def discover_versions(token: Token | None = None) -> list[str]:
    """Aktiv versiyaları paralel yoxlayır (köhnədən yeniyə sıralı)."""
    import concurrent.futures

    token = token or load_token()
    if not token or token.expired:
        return []
    candidates = _candidate_versions()
    active: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_probe_version, token, v): v for v in candidates}
        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    active.append(futures[future])
            except Exception:  # noqa: BLE001
                continue
    return sorted(active)


def _cached_versions() -> dict:
    from . import store

    return store.read_json(VERSION_CACHE, {}) or {}


def refresh_versions(token: Token | None = None) -> dict:
    """Aktiv versiyaları yenidən aşkarlayıb keşləyir."""
    from . import store

    active = discover_versions(token)
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "active": active,
        "newest": active[-1] if active else "",
    }
    store.write_json(VERSION_CACHE, payload)
    return payload


def version_status(refresh_if_stale: bool = True) -> dict:
    """Hazırkı versiyanın vəziyyəti + tövsiyə.

    Qaytarır: {current, active, newest, current_ok, upgrade_available}
    """
    cache = _cached_versions()
    stale = True
    if cache.get("checked_at"):
        try:
            checked = datetime.fromisoformat(cache["checked_at"])
            stale = (datetime.now(timezone.utc) - checked).days >= VERSION_TTL_DAYS
        except ValueError:
            stale = True
    if stale and refresh_if_stale:
        cache = refresh_versions()

    active = cache.get("active") or []
    current = current_version()
    return {
        "current": current,
        "active": active,
        "newest": cache.get("newest", ""),
        "current_ok": (current in active) if active else True,
        "upgrade_available": bool(active and current != active[-1]),
        "checked_at": cache.get("checked_at", ""),
    }


def current_version() -> str:
    """İşlədiləcək API versiyası.

    `LINKEDIN_API_VERSION` ÜSTÜNLÜKDÜR, amma mütləq deyil: həmin versiya
    sıradan çıxıbsa sistem aktiv olanların ən yenisinə keçir. Əks halda
    sabit yazılmış versiya bir gün yayımı tamamilə dayandırardı.
    """
    preferred = os.environ.get("LINKEDIN_API_VERSION") or API_VERSION
    cached = _cached_versions()
    active = cached.get("active") or []
    if active and preferred not in active:
        return cached.get("newest") or preferred
    return preferred

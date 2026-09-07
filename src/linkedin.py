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
# LinkedIn versiyalı API tələb edir (YYYYMM formatı).
API_VERSION = os.environ.get("LINKEDIN_API_VERSION", "202509")
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


def _headers(token: Token, extra: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token.access_token}",
        "LinkedIn-Version": API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def upload_image(token: Token, path: pathlib.Path) -> str:
    """Şəkli yükləyir və `urn:li:image:...` qaytarır."""
    init = net.request(
        "POST", f"{API_BASE}/rest/images?action=initializeUpload",
        body=json.dumps({"initializeUploadRequest": {"owner": token.person_urn}}).encode(),
        headers=_headers(token), timeout=90,
    )
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


def create_post(token: Token, text: str, *, image_urn: str = "",
                alt_text: str = "") -> str:
    """Post yaradır və post URN-ini qaytarır."""
    payload: dict = {
        "author": token.person_urn,
        "commentary": escape_commentary(text),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if image_urn:
        payload["content"] = {"media": {"id": image_urn,
                                        "altText": (alt_text or "")[:300]}}

    resp = net.request("POST", f"{API_BASE}/rest/posts",
                       body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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

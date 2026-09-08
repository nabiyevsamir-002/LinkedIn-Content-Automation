"""Mərkəzi konfiqurasiya: yollar, modellər, sütunlar, .env yükləyicisi."""
from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
STATE_DIR = ROOT / "state"
RUNS_DIR = STATE_DIR / "runs"
OUT_DIR = ROOT / "out"


def _load_env() -> None:
    """Sadə .env yükləyicisi — xarici asılılıq olmadan."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


_load_env()

# Prompt versiyası — hər postla birlikdə saxlanılır ki, keyfiyyət
# dəyişəndə səbəbini tapa biləsiniz.
PROMPT_VERSION = "m1.0"

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
# `claude setup-token` ilə yaradılan uzunömürlü token. Alt-proses
# ambient keychain girişini görmür, ona görə açıq şəkildə ötürülür.
OAUTH_TOKEN = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
SAFE_MODE = os.environ.get("CLAUDE_SAFE_MODE", "1") == "1"

MODEL_SCOUT = os.environ.get("MODEL_SCOUT", "haiku")
MODEL_MAIN = os.environ.get("MODEL_MAIN", "sonnet")

# --- Agent büdcələri ------------------------------------------------
# Abunəlikdə pul xərci yoxdur, amma kvota var. Researcher web alətləri
# ilə işlədiyi üçün nəzarətsiz böyüyə bilir — ölçülmüş bir qaçışda
# 122k token yedi. Bu hədlər qaçaq halları kəsir, normal işə mane olmur.
AGENT_BUDGET_USD = float(os.environ.get("AGENT_BUDGET_USD", "0.25"))
RESEARCH_BUDGET_USD = float(os.environ.get("RESEARCH_BUDGET_USD", "0.45"))
# 8 tur çox sərt idi: web araşdırması ortasında kəsilirdi və agent
# sxemi doldurmaq üçün «Test claim» kimi doldurucu yazırdı. 14 tur
# araşdırmanı bitirməyə imkan verir, büdcə isə qaçağı yenə saxlayır.
RESEARCH_MAX_TURNS = os.environ.get("RESEARCH_MAX_TURNS", "14")
# Bu baldan aşağı postlar yayımlanmır (--force olmadan)
MIN_PUBLISH_SCORE = int(os.environ.get("MIN_PUBLISH_SCORE", "5"))
# Bundan çox token yeyən agent haqqında xəbərdarlıq göstərilir
TOKEN_WARN_THRESHOLD = int(os.environ.get("TOKEN_WARN_THRESHOLD", "60000"))

MAX_ITEM_AGE_HOURS = int(os.environ.get("MAX_ITEM_AGE_HOURS", "36"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "20"))
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AvtoPost/1.0"

# --- Məzmun sütunları -------------------------------------------------
# Scout bunlara görə həftəlik balans saxlayır: profiliniz təsadüfi lent
# yox, ardıcıl mövqe olsun.
PILLARS = {
    "agents": "AI agentləri praktikada — avtomatlaşdırma, iş axını, real tətbiqlər",
    "tooling": "Alətlər və developer iş axını — yeni modellər, IDE, API-lar",
    "business": "AI və biznes — regional/yerli təsir, iqtisadiyyat, iş bazarı",
    "research": "Model və tədqiqat təhlili — benchmark, təhlükəsizlik, elmi nəticə",
}
PILLAR_WINDOW_DAYS = 14

# --- Yayım cədvəli ----------------------------------------------------
# Hazırlıq və yayım vaxtı ayrıdır: səhər təsdiqləyirsiniz, sistem
# auditoriyanın aktiv olduğu saatda yayımlayır (UTC).
PUBLISH_HOUR_UTC = int(os.environ.get("PUBLISH_HOUR_UTC", "8"))
PUBLISH_WEEKENDS = os.environ.get("PUBLISH_WEEKENDS", "0") == "1"

# --- Xarici sağlamlıq monitorinqi -------------------------------------
# healthchecks.io-da pulsuz «check» yaradın və ping URL-ini bura yazın.
# Sistem gözlənilən vaxtda siqnal göndərməsə xidmət SİZƏ e-poçt/Telegram
# xəbərdarlığı göndərir — yəni sistem tam dayansa belə xəbəriniz olur.
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "")

# --- Brend --------------------------------------------------------------
# Claude-un dizayn etdiyi şəkillərdə görünən imza. Boş buraxsanız
# LinkedIn profilinizin adı istifadə olunur.
BRAND_NAME = os.environ.get("BRAND_NAME", "")
BRAND_HANDLE = os.environ.get("BRAND_HANDLE", "")   # məs. linkedin.com/in/...

# --- LinkedIn ---------------------------------------------------------
LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")

# --- Telegram ---------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# LinkedIn "…daha çox" kəsilmə həddi (təxmini, mobil görünüş).
LINKEDIN_FOLD_CHARS = 210
LINKEDIN_FOLD_LINES = 3

for _d in (STATE_DIR, RUNS_DIR, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

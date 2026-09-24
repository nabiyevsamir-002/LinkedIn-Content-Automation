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
# Foto müfəttişi şəkilləri GÖRÜR (Read aləti) — vizion tələb edir; haiku
# kifayətdir və ucuzdur (ölçülüb 15.09.2026: 1 şəkil ≈ 1.5k token).
MODEL_INSPECT = os.environ.get("MODEL_INSPECT", MODEL_SCOUT)

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
# --- Yayım sürəti (ən vacib qoruyucular) -----------------------------
# Bank təhlükəsizlik toru kimi düşünülüb, amma sürət həddi olmasa
# hər tick bankdan bir post yayımlayır: 5 postluq bank 75 dəqiqəyə
# boşalır. Bu iki hədd bunun qarşısını alır.
MAX_POSTS_PER_DAY = int(os.environ.get("MAX_POSTS_PER_DAY", "1"))
MIN_HOURS_BETWEEN_POSTS = float(os.environ.get("MIN_HOURS_BETWEEN_POSTS", "6"))

# Bu baldan aşağı postlar yayımlanmır (--force olmadan)
MIN_PUBLISH_SCORE = int(os.environ.get("MIN_PUBLISH_SCORE", "5"))
# Bundan çox token yeyən agent haqqında xəbərdarlıq göstərilir
TOKEN_WARN_THRESHOLD = int(os.environ.get("TOKEN_WARN_THRESHOLD", "60000"))

MAX_ITEM_AGE_HOURS = int(os.environ.get("MAX_ITEM_AGE_HOURS", "36"))

# --- Qlobal / yerli balans -------------------------------------------
# Scout-a göstərilən klaster pəncərəsinin neçə hissəsi yerli xəbərə
# ayrılır. 0.5 = yarısı. Sıfır versəniz sistem yalnız qlobal xəbərlə
# işləyir; 1.0 versəniz yalnız yerli ilə. Kvota lazımdır, çünki yerli
# nəşrlər bir-birini təkrar etmir və çarpaz təsdiq balları həmişə
# aşağı olur — vahid siyahıda heç vaxt yuxarı qalxmırlar.
SCOUT_LOCAL_SHARE = float(os.environ.get("SCOUT_LOCAL_SHARE", "0.5"))
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

# Bütün istifadəçi mesajlarında bu zona işlədilir (daxildə həmişə UTC).
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Baku")

# --- Yayım cədvəli ----------------------------------------------------
# Hazırlıq və yayım vaxtı ayrıdır: səhər təsdiqləyirsiniz, sistem
# auditoriyanın aktiv olduğu saatda yayımlayır (UTC).
# Yayım saatı YERLİ vaxtla verilir (məs. 12 = günorta 12:00 Bakı vaxtı).
# Köhnə PUBLISH_HOUR_UTC hələ də işləyir, amma tövsiyə olunmur.
PUBLISH_HOUR = int(os.environ.get("PUBLISH_HOUR", os.environ.get("PUBLISH_HOUR_UTC", "12")))
PUBLISH_HOUR_IS_UTC = "PUBLISH_HOUR" not in os.environ and "PUBLISH_HOUR_UTC" in os.environ
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
# Vurğu rəngi — bütün şəkillərdə vahid stil üçün (məs. #38bdf8).
# Boş buraxsanız dizayner palitraya uyğun rəng seçir.
BRAND_COLOR = os.environ.get("BRAND_COLOR", "").strip()
# assets/ içindəki loqo faylı (PNG və ya SVG). Şəkilə imza ilə yanaşı düşür.
BRAND_LOGO = os.environ.get("BRAND_LOGO", "").strip()

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

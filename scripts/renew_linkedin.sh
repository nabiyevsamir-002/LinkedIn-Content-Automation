#!/usr/bin/env bash
# LinkedIn tokenini yeniləyir və GitHub secret-lərini avtomatik güncəlləyir.
#
#   make li-renew
#
# Token 60 gün yaşayır. Refresh token yalnız partnyor app-lərə verilir,
# ona görə bu addım əl ilə edilməlidir — amma bir əmrə yığılıb.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT"

GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'

echo
echo "${BOLD}1/3  LinkedIn-ə giriş${RESET}"
echo "${DIM}     Brauzer açılacaq — təsdiq edin.${RESET}"
echo
"$PROJECT/scripts/_py" auth/linkedin_oauth.py || {
  echo "${YELLOW}Giriş tamamlanmadı — dayandırıldı.${RESET}"; exit 1;
}

echo "${BOLD}2/3  GitHub secret-ləri yenilənir${RESET}"
if ! command -v gh >/dev/null 2>&1; then
  echo "${YELLOW}     gh CLI yoxdur — secret-ləri əl ilə yeniləyin:${RESET}"
  "$PROJECT/scripts/_py" -m src.cli li-export
  exit 0
fi

"$PROJECT/scripts/_py" - <<'PY'
import json, pathlib, subprocess, sys
tok = json.loads(pathlib.Path("state/linkedin.json").read_text(encoding="utf-8"))
pairs = {
    "LINKEDIN_ACCESS_TOKEN": tok["access_token"],
    "LINKEDIN_PERSON_URN": tok["person_urn"],
    "LINKEDIN_EXPIRES_AT": tok["expires_at"],
    "LINKEDIN_PROFILE_NAME": tok.get("name", ""),
}
failed = []
for name, value in pairs.items():
    r = subprocess.run(["gh", "secret", "set", name], input=value,
                       capture_output=True, text=True)
    print(("     ✓ " if r.returncode == 0 else "     ✗ ") + name)
    if r.returncode:
        failed.append(name)
sys.exit(1 if failed else 0)
PY

echo
echo "${BOLD}3/3  Yoxlama${RESET}"
"$PROJECT/scripts/_py" -m src.cli doctor 2>&1 | grep -A3 "LinkedIn" | head -4

echo
echo "${GREEN}Token yeniləndi. Növbəti yeniləmə ~60 gün sonra —${RESET}"
echo "${GREEN}sistem 7 gün əvvəldən Telegram-a xəbərdarlıq göndərəcək.${RESET}"
echo

"""LinkedIn OAuth — bir dəfəlik giriş.

İşlədilməsi:  make li-auth

Lokal serverdə http://localhost:8765/callback ünvanını dinləyir,
brauzeri açır, siz LinkedIn-də təsdiq edirsiniz, token `state/linkedin.json`
faylına yazılır (icazə 600, git-ə düşmür).
"""
from __future__ import annotations

import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import linkedin as li  # noqa: E402

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)

PAGE = """<!doctype html><meta charset="utf-8">
<style>body{{font:16px -apple-system,sans-serif;background:#0b1220;color:#e2e8f0;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
div{{text-align:center;max-width:420px}}h1{{font-size:22px;margin:0 0 10px}}
p{{color:#94a3b8;line-height:1.5}}</style>
<div><h1>{title}</h1><p>{body}</p></div>"""

_result: dict = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        _result.update({k: v[0] for k, v in params.items()})

        if "code" in _result:
            html = PAGE.format(title="✅ Giriş tamamlandı",
                               body="Bu pəncərəni bağlaya bilərsiniz — terminala qayıdın.")
        else:
            html = PAGE.format(title="❌ Giriş alınmadı",
                               body=_result.get("error_description", "Naməlum xəta"))
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args):  # susdur
        pass


def main() -> int:
    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        print(f"\n{RED}✗ LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET .env-də yoxdur.{RESET}")
        print(f"""
{BOLD}LinkedIn app necə yaradılır (~20 dəqiqə){RESET}

  1. linkedin.com/company/setup/new — Company Page yaradın (pulsuz)
     {DIM}App yaratmaq üçün mütləqdir, məzmun yerləşdirməyə ehtiyac yoxdur.{RESET}
  2. linkedin.com/developers/apps/new — app yaradın, həmin səhifəni seçin
  3. «Products» bölməsi → ikisini də əlavə edin:
       • Sign In with LinkedIn using OpenID Connect
       • Share on LinkedIn
  4. «Auth» bölməsi → «Authorized redirect URLs» sahəsinə tam olaraq bunu yazın:
       {BOLD}{li.REDIRECT_URI}{RESET}
  5. Həmin bölmədən Client ID və Client Secret götürüb .env-ə yazın:
       LINKEDIN_CLIENT_ID=...
       LINKEDIN_CLIENT_SECRET=...
  6. Bu əmri təkrar işlədin: {BOLD}make li-auth{RESET}
""")
        return 2

    state = secrets.token_urlsafe(16)
    url = li.authorize_url(state)
    port = urllib.parse.urlparse(li.REDIRECT_URI).port or 8765

    try:
        server = http.server.HTTPServer(("localhost", port), Handler)
    except OSError as exc:
        print(f"\n{RED}✗ {port} portu tutulub: {exc}{RESET}")
        return 3

    print(f"""
{BOLD}Yoxlayın:{RESET} LinkedIn app-ın «Auth» bölməsində
«Authorized redirect URLs for your app» sahəsində EYNİLƏ bu olmalıdır:

    {BOLD}{li.REDIRECT_URI}{RESET}

{DIM}Fərq olsa (sonda «/», «127.0.0.1», başqa port, boşluq) LinkedIn
«redirect_uri does not match» xətası verir. Əlavə etdikdən sonra
mütləq {RESET}{BOLD}Update{RESET}{DIM} düyməsini basın.{RESET}
""")
    print(f"  Brauzer açılır… Açılmasa bu linki özünüz açın:\n\n  {DIM}{url}{RESET}\n")
    webbrowser.open(url)
    print(f"  {DIM}LinkedIn-də təsdiq gözlənilir…{RESET}")
    server.serve_forever()
    server.server_close()

    if _result.get("state") != state:
        print(f"\n{RED}✗ state uyğunsuzluğu — təhlükəsizlik yoxlaması keçmədi.{RESET}\n")
        return 4
    if "code" not in _result:
        desc = _result.get("error_description", "kod alınmadı")
        print(f"\n{RED}✗ {desc}{RESET}")
        if "redirect" in desc.lower():
            print(f"""
{BOLD}Bu xəta nə deməkdir:{RESET} LinkedIn app-da qeydiyyatdan keçmiş
ünvan bizim göndərdiyimizlə üst-üstə düşmür.

  1. linkedin.com/developers/apps → app-ınızı açın
  2. {BOLD}Auth{RESET} tabı → «Authorized redirect URLs for your app»
  3. «+ Add redirect URL» → aşağıdakını KOPYALAYIB yapışdırın:

     {BOLD}{li.REDIRECT_URI}{RESET}

  4. {BOLD}Update{RESET} düyməsini basın (bu addım tez-tez unudulur)
  5. 30 saniyə gözləyin, sonra: {BOLD}make li-auth{RESET}
""")
        return 5

    try:
        token = li.exchange_code(_result["code"])
    except li.LinkedInError as exc:
        print(f"\n{RED}✗ {exc}{RESET}\n")
        return 6

    print(f"\n  {GREEN}✓ Giriş tamamlandı{RESET}")
    print(f"    profil : {token.name}")
    print(f"    URN    : {token.person_urn}")
    print(f"    bitir  : {token.expires_dt:%d.%m.%Y} ({token.days_left:.0f} gün)")
    print(f"    fayl   : {li.TOKEN_FILE}\n")
    print(f"  {DIM}Növbəti: make doctor{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

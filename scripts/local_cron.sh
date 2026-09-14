#!/usr/bin/env bash
# Lokal ehtiyat cron — GitHub Actions işə düşməsə sistem yenə işləyir.
#
# TƏHLÜKƏSİZLİK: GitHub və lokal eyni anda işləyə bilər. İkiqat postun
# qarşısını almaq üçün:
#   1. Hər qaçışdan ƏVVƏL git-dən vəziyyət çəkilir
#   2. Post artıq bu gün hazırlanıbsa (kim tərəfindənsə) — atlanır
#   3. Qaçışdan SONRA vəziyyət geri göndərilir
#   4. Kilid: iki lokal proses eyni anda işləmir
set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT" || exit 1

MODE="${1:-tick}"
LOCK="$PROJECT/state/.local-cron.lock"
LOG="$PROJECT/out/local-cron.log"
mkdir -p "$(dirname "$LOG")" "$PROJECT/state"

log() { printf '%s  [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$MODE" "$*" >> "$LOG"; }

# --- kilid (mkdir atomikdir) ---
if ! mkdir "$LOCK" 2>/dev/null; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$age" -lt 1800 ]; then
    log "başqa proses işləyir (${age}s) — atlanır"
    exit 0
  fi
  log "köhnəlmiş kilid silinir (${age}s)"
  rmdir "$LOCK" 2>/dev/null
  mkdir "$LOCK" 2>/dev/null || exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# --- 1. GitHub-dan vəziyyəti çək ---
if git rev-parse --git-dir >/dev/null 2>&1; then
  git pull --rebase --autostash -q origin main 2>>"$LOG" \
    && log "git pull OK" \
    || log "git pull alınmadı — lokal vəziyyətlə davam edilir"
fi

# --- 1b. Aktiv saat pəncərəsi (tick üçün) ---
if [ "$MODE" = "tick" ]; then
  hour=$(date '+%H')
  if [ "$hour" -lt 9 ] || [ "$hour" -gt 21 ]; then
    exit 0        # gecə saatlarında işləməyə ehtiyac yoxdur
  fi
fi

# --- 2. Təkrar işin qarşısını al ---
if [ "$MODE" = "prepare" ]; then
  already=$("$PROJECT/scripts/_py" -c "
import sys; sys.path.insert(0, '.')
from src import proposals
print('yes' if proposals.prepared_today() else 'no')
" 2>/dev/null)
  if [ "$already" = "yes" ]; then
    log "bu gün post artıq hazırlanıb (GitHub və ya lokal) — atlanır"
    exit 0
  fi
fi

# --- 3. İşi gör ---
case "$MODE" in
  prepare)
    # Davranış CI (.github/workflows/prepare.yml) ilə EYNİ olmalıdır:
    # TOPIC_SELECTION=1 → namizədlər göndərilir, post seçimdən SONRA
    # yazılır. Əvvəllər lokal ehtiyat `run` işlədirdi — GitHub cron
    # gecikəndə mövzunu sistem özü seçirdi, istifadəçi isə 3 namizəd
    # gözləyirdi (10.09.2026-da məhz belə oldu).
    if [ "${TOPIC_SELECTION:-1}" = "1" ]; then
      log "namizədlər hazırlanır…"
      "$PROJECT/scripts/_py" -m src.cli propose --notify-empty >>"$LOG" 2>&1
      code=$?
      if [ $code -eq 0 ]; then
        log "namizədlər Telegram-a göndərildi — seçim gözlənilir"
      elif [ $code -eq 5 ]; then
        log "uyğun xəbər tapılmadı — bank rejimi"
      elif [ $code -eq 3 ]; then
        log "abunəlik limiti bitib — namizəd yoxdur, Telegram-a xəbərdarlıq getdi"
      else
        log "XƏTA: propose çıxış kodu $code"
      fi
    else
      log "post hazırlanır…"
      "$PROJECT/scripts/_py" -m src.cli run --image --commit --notify-empty >>"$LOG" 2>&1
      code=$?
      if [ $code -eq 0 ]; then
        "$PROJECT/scripts/_py" -m src.cli send >>"$LOG" 2>&1 && log "Telegram-a göndərildi"
        "$PROJECT/scripts/_py" -m src.cli notion-sync >>"$LOG" 2>&1
      elif [ $code -eq 5 ]; then
        log "uyğun xəbər tapılmadı — bank rejimi"
      else
        log "XƏTA: run çıxış kodu $code"
      fi
    fi
    ;;
  tick)
    # `make watch` işləyirsə Telegram-ı o dinləyir — ikinci dinləyici
    # 409 Conflict alır. Poll addımını atlayırıq, qalanı işləyir.
    if pgrep -f "src.cli watch" >/dev/null 2>&1; then
      log "watch dinləyicisi aktivdir — poll atlanır"
    else
      "$PROJECT/scripts/_py" -m src.cli poll >>"$LOG" 2>&1
    fi

    # YAYIM: yalnız GitHub Actions ölübsə.
    # İkisi eyni anda yayımlasa post İKİ DƏFƏ çıxa bilər: vəziyyət git
    # ilə sinxronlaşır və aralarında pəncərə var — CI köhnə vəziyyətlə
    # eyni postu təkrar yayımlaya bilər. Ona görə lokal yalnız ehtiyatdır.
    # CI ürək döyüntüsü. Vəziyyət commit-lərinə baxmaq etibarsızdır:
    # sağlam CI heç nə dəyişməsə commit etmir və «ölü» görünür.
    ci_age=$("$PROJECT/scripts/_py" -c "
import json, pathlib, sys
from datetime import datetime, timezone
p = pathlib.Path('state/ci_heartbeat.json')
if not p.exists(): print(999999); sys.exit()
try:
    d = json.loads(p.read_text())
    # Yalnız GitHub Actions-dan gələn siqnal sayılır; lokal qaçış
    # özünü «CI sağdır» kimi göstərməməlidir.
    if d.get('run', 'local') == 'local':
        print(999999); sys.exit()
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(d['at'])).total_seconds()
    print(int(max(0, age)))
except Exception:
    print(999999)
" 2>/dev/null || echo 999999)
    last_ci=1
    if [ "$ci_age" -lt "${CI_ALIVE_SECONDS:-5400}" ]; then
      # GitHub sağdır: post YARADAN və YAYIMLAYAN addımlar ona qalır.
      # Lokal yalnız idempotent işləri görür (poll, notion-sync).
      log "GitHub Actions aktivdir (${ci_age}s) — yayım və xatırlatma ona buraxılır"
    else
      log "GitHub Actions cavab vermir (${ci_age}s) — lokal ehtiyat işə düşür"
      # Log kifayət etmir: istifadəçi CI-nın ölü olduğunu bilməlidir
      "$PROJECT/scripts/_py" -c "
import sys; sys.path.insert(0, '.')
from src import notify
notify.ci_down($ci_age)
" >>"$LOG" 2>&1 || true
      "$PROJECT/scripts/_py" -m src.cli publish --from-bank >>"$LOG" 2>&1
      "$PROJECT/scripts/_py" -m src.cli remind >>"$LOG" 2>&1
    fi
    "$PROJECT/scripts/_py" -m src.cli notion-sync >>"$LOG" 2>&1
    ;;
  *)
    log "naməlum rejim: $MODE"; exit 1 ;;
esac

# --- 4. Vəziyyəti geri göndər (rebase təkrar cəhdi ilə) ---
if git rev-parse --git-dir >/dev/null 2>&1; then
  if "$PROJECT/scripts/commit_state.sh" "lokal $MODE" >>"$LOG" 2>&1; then
    log "vəziyyət saxlanıldı"
  else
    log "push alınmadı — növbəti qaçışda təkrarlanacaq"
  fi
fi

# --- 5. Yaddaşı təmiz saxla ---
"$PROJECT/scripts/_py" -c "
import sys; sys.path.insert(0,'.')
from src import queue
c = queue.compact(); p = queue.prune_images()
w = queue.prune_workdir(); r = queue.prune_runs()
if c or p or w or r:
    print(f'təmizləndi: {c} element · {p} şəkil · {w} işçi fayl · {r} qaçış')
" >>"$LOG" 2>&1

# jurnalı böyüməkdən saxla
tail -n 2000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
log "bitdi"

#!/usr/bin/env bash
# macOS launchd agentlərini quraşdırır/silir.
#
#   ./scripts/install_launchd.sh install
#   ./scripts/install_launchd.sh uninstall
#   ./scripts/install_launchd.sh status
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
PREPARE="com.avtopost.prepare"
TICK="com.avtopost.tick"
WATCH="com.avtopost.watch"
RUNNER="$PROJECT/scripts/local_cron.sh"

mkdir -p "$AGENTS" "$PROJECT/out"

write_plist() {
  local label="$1" mode="$2" schedule="$3"
  cat > "$AGENTS/$label.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$RUNNER</string>
    <string>$mode</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
$schedule
  <key>StandardOutPath</key><string>$PROJECT/out/launchd-$mode.log</string>
  <key>StandardErrorPath</key><string>$PROJECT/out/launchd-$mode.log</string>
  <key>ProcessType</key><string>Background</string>
  <key>LowPriorityIO</key><true/>
</dict>
</plist>
PLIST
}

# Watch DAİMİ prosesdir — cədvəllə deyil, KeepAlive ilə işləyir.
# Şəbəkə kəsiləndə (Telegram bloku) proses ölə bilər; launchd onu
# dərhal qaldırır, yəni blok pəncərəsi açılan kimi dinləyici yerindədir.
# 10.09.2026-da watch `Terminated: 15` ilə öldü və ölü qaldı —
# düymələr bütün gün cavabsız qaldı. Bu plist məhz onun üçündür.
write_watch_plist() {
  cat > "$AGENTS/$WATCH.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$WATCH</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$PROJECT/scripts/_py</string>
    <string>-m</string>
    <string>src.cli</string>
    <string>watch</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <!-- Sonsuz yenidən başlatma dövrünün qarşısını alır -->
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$PROJECT/out/launchd-watch.log</string>
  <key>StandardErrorPath</key><string>$PROJECT/out/launchd-watch.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST
}

case "${1:-status}" in
  install)
    # Post hazırlığı: iş günləri 09:30 (GitHub 08:30-da işləyir — bu, ehtiyatdır)
    write_plist "$PREPARE" prepare '  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
  </array>'
    # Cavablar/yayım: hər 15 dəqiqə (skript 09:00-21:00 pəncərəsini özü yoxlayır)
    write_plist "$TICK" tick '  <key>StartInterval</key><integer>900</integer>'

    write_watch_plist

    # Əl ilə işləyən dinləyici varsa dayandırırıq — iki dinləyici
    # Telegram-dan 409 alır və bir-birinin yeniləməsini oğurlayır.
    pkill -f "src.cli watch" 2>/dev/null || true

    for label in "$PREPARE" "$TICK" "$WATCH"; do
      launchctl unload "$AGENTS/$label.plist" 2>/dev/null || true
      launchctl load "$AGENTS/$label.plist"
      echo "  ✓ $label quraşdırıldı"
    done
    echo
    echo "  Mac yuxuda olsa işləmir — oyananda buraxılmış qaçış icra olunur."
    ;;

  uninstall)
    for label in "$PREPARE" "$TICK" "$WATCH"; do
      launchctl unload "$AGENTS/$label.plist" 2>/dev/null || true
      rm -f "$AGENTS/$label.plist"
      echo "  ✓ $label silindi"
    done
    ;;

  status)
    for label in "$PREPARE" "$TICK" "$WATCH"; do
      if launchctl list | grep -q "$label"; then
        line=$(launchctl list | grep "$label")
        echo "  ✓ $label   $line"
      else
        echo "  ○ $label   quraşdırılmayıb"
      fi
    done
    ;;

  *) echo "istifadə: $0 {install|uninstall|status}"; exit 1 ;;
esac

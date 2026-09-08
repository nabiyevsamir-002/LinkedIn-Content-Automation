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

    for label in "$PREPARE" "$TICK"; do
      launchctl unload "$AGENTS/$label.plist" 2>/dev/null || true
      launchctl load "$AGENTS/$label.plist"
      echo "  ✓ $label quraşdırıldı"
    done
    echo
    echo "  Mac yuxuda olsa işləmir — oyananda buraxılmış qaçış icra olunur."
    ;;

  uninstall)
    for label in "$PREPARE" "$TICK"; do
      launchctl unload "$AGENTS/$label.plist" 2>/dev/null || true
      rm -f "$AGENTS/$label.plist"
      echo "  ✓ $label silindi"
    done
    ;;

  status)
    for label in "$PREPARE" "$TICK"; do
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

#!/usr/bin/env bash
# Vəziyyət fayllarını repo-ya yazır.
# İki iş axını eyni anda yazsa, rebase ilə təkrar cəhd edilir.
set -euo pipefail

MESSAGE="${1:-vəziyyət yeniləndi}"

# CI-də lokal konfiqurasiya yoxdur; lokalda isə istifadəçinin öz
# ayarlarını pozmuruq.
git config user.name  >/dev/null 2>&1 || git config user.name  "avto-post[bot]"
git config user.email >/dev/null 2>&1 || git config user.email "avto-post@users.noreply.github.com"

git add -A state/ || true

# YALNIZ state/ yoxlanılır və YALNIZ o commit olunur.
#
# 24.09.2026: arqumentsiz `git commit` indeksdəki HƏR ŞEYİ götürür.
# Redaktor eyni anda kod fayllarını `git add` etmişdisə, onlar da
# «chore(state): lokal tick» adı altında commit və push olunurdu —
# real hadisə: 208 sətirlik `src/approval.py` dəyişikliyi belə getdi.
# Pathspec bunu qəti şəkildə bağlayır: indeksdə nə olursa olsun,
# bu commit-ə yalnız state/ düşür.
if git diff --cached --quiet -- state/; then
  echo "dəyişiklik yoxdur"
  exit 0
fi

git commit -m "chore(state): ${MESSAGE}" -- state/

for attempt in 1 2 3; do
  if git push; then
    echo "push OK (cəhd ${attempt})"
    exit 0
  fi
  echo "push uğursuz — rebase edilir (cəhd ${attempt})"
  git pull --rebase --autostash origin "$(git rev-parse --abbrev-ref HEAD)"
  sleep $((attempt * 3))
done

echo "::error::vəziyyət push edilə bilmədi"
exit 1

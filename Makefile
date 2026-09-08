PY := python3

.PHONY: help setup doctor run image send poll watch queue tg-chatid li-auth li-export publish remind report notion-setup notion-sync styles replay sources stats clean

help:
	@echo ""
	@echo "  make doctor    — bütün inteqrasiyaları yoxla (buradan başlayın)"
	@echo "  make run       — tam axını işə sal, postu terminalda göstər"
	@echo "  make image     — son post üçün şəkil hazırla (--all: bütün variantlar)"
	@echo "  make send      — postu Telegram-a təsdiq üçün göndər"
	@echo "  make watch     — DAİMİ dinləyici, düymələrə ani cavab (Ctrl+C ilə dayanır)"
	@echo "  make poll      — Telegram cavablarını emal et (ARGS='--watch 120')"
	@echo "  make queue     — növbə və bankın vəziyyəti"
	@echo "  make tg-chatid — Telegram chat ID-ni tap"
	@echo "  make li-auth   — LinkedIn-ə giriş (bir dəfəlik, 60 gündən bir təkrar)"
	@echo "  make li-export — LinkedIn tokenini GitHub Secrets üçün göstər"
	@echo "  make publish   — vaxtı çatmış postu LinkedIn-ə yayımla"
	@echo "  make remind    — yayımdan sonrakı şərh xatırlatmaları"
	@echo "  make styles    — eyni xəbəri 3 üslubda yaz (üslub kalibrləməsi)"
	@echo "  make replay    — köhnə xəbərlərlə yenidən qaç (prompt sınağı)"
	@echo "  make sources   — mənbələri və hadisə klasterlərini göstər"
	@echo "  make notion-setup — Notion bazasını tap/yarat"
	@echo "  make notion-sync  — Notion ↔ növbə sinxronizasiyası"
	@echo "  make report    — həftəlik yekun (ARGS='--send')"
	@echo "  make stats     — kvota/token hesabatı"
	@echo ""
	@echo "  Əlavə: make run ARGS='--style analyst --commit'"
	@echo ""

setup:
	@cp -n .env.example .env 2>/dev/null || true
	@$(PY) -c "import re,pathlib;t=re.search(r'^CLAUDE_CODE_OAUTH_TOKEN=(.+)',pathlib.Path('.env').read_text(),re.M);print('✓ .env hazırdır, token yerindədir' if t and t.group(1).strip() else '! .env yaradıldı. İndi: claude setup-token → tokeni .env-ə yazın')"

doctor:
	@$(PY) -m src.cli doctor

run:
	@$(PY) -m src.cli run $(ARGS)

image:
	@$(PY) -m src.cli image $(ARGS)

send:
	@$(PY) -m src.cli send $(ARGS)

watch:
	@$(PY) -m src.cli watch

poll:
	@$(PY) -m src.cli poll $(ARGS)

queue:
	@$(PY) -m src.cli queue $(ARGS)

tg-chatid:
	@$(PY) -m src.cli tg-chatid

li-export:
	@$(PY) -m src.cli li-export

li-auth:
	@$(PY) auth/linkedin_oauth.py

publish:
	@$(PY) -m src.cli publish $(ARGS)

remind:
	@$(PY) -m src.cli remind

styles:
	@$(PY) -m src.cli styles $(ARGS)

replay:
	@$(PY) -m src.cli replay $(ARGS)

sources:
	@$(PY) -m src.cli sources $(ARGS)

notion-setup:
	@$(PY) -m src.cli notion-setup

notion-sync:
	@$(PY) -m src.cli notion-sync

report:
	@$(PY) -m src.cli report $(ARGS)

stats:
	@$(PY) -m src.cli stats $(ARGS)

clean:
	@rm -rf out/*.md __pycache__ src/__pycache__
	@echo "✓ təmizləndi"

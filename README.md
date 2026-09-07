# LinkedIn Avto-Post — M1

AI xəbərlərindən Azərbaycan dilində LinkedIn postu hazırlayan agent sistemi.
LLM xərci **$0** — Claude Pro abunəliyi ilə işləyir.

## Başlanğıc

```bash
claude setup-token      # bir dəfə: Claude Code-a giriş
make setup              # .env yaradır
make doctor             # hər şeyi yoxlayır
make run                # ilk postu hazırlayır
```

## Əmrlər

| Əmr | Nə edir |
|---|---|
| `make doctor` | 9 mənbə + SSL + Claude girişi + yaddaş yoxlanılır |
| `make run` | Tam axın: Scout → Researcher → Writer → Reviewer → Reviser |
| `make styles` | Eyni xəbər 3 fərqli üslubda — bəyəndiyinizi seçirsiniz |
| `make replay` | Köhnə xəbərlərlə yenidən qaçır — **prompt dəyişikliyini dərhal sınamaq üçün** |
| `make image` | Son post üçün şəkil zənciri (`--all`: bütün variantlar) |
| `make send` | Postu Telegram-a təsdiq üçün göndər (`--dry-run`: yalnız önizləmə) |
| `make poll` | Telegram cavablarını emal et (`ARGS='--watch 120'`: adaptiv izləmə) |
| `make queue` | Növbə və bankın vəziyyəti |
| `make tg-chatid` | Telegram chat ID-ni tap |
| `make li-auth` | LinkedIn-ə giriş (60 gündən bir təkrarlanır) |
| `make publish` | Vaxtı çatmış postu yayımla (`--dry-run`, `--from-bank`) |
| `make remind` | Yayımdan sonrakı şərh xatırlatmaları |
| `make report` | Həftəlik yekun (`--send`: Telegram-a) |
| `make li-export` | LinkedIn tokenini GitHub Secrets üçün göstər |
| `make sources` | Hansı xəbərlər var, hansı hadisələr neçə mənbədə təsdiqlənib |
| `make stats` | Real token/kvota istifadəsi |

## ⚠️ Doldurulmalı 2 fayl

Sistem işləyir, amma sizi tanımır. Bu iki fayl doldurulmayana qədər
`voice` və `local_relevance` balları aşağı qalacaq:

| Fayl | Nə üçün |
|---|---|
| `prompts/positioning.md` | Kimsiniz, hansı sektorları bilirsiniz, auditoriyanız kimdir. **Yerli kontekstin həqiqi olması üçün.** Boş qalsa, sistem süni "yerli" cümlə yazmır — sadəcə buraxır (belə daha yaxşıdır). |
| `prompts/voice_guide.md` | Öz LinkedIn postlarınızdan 3-5 nümunə. Səs balını qaldıran yeganə şey. |

Doldurduqdan sonra `make replay` — nəticəni dərhal görürsünüz.

## Üslubu necə dəyişirsiniz

1. `prompts/voice_guide.md` faylını açın
2. Bir sətir dəyişin (və ya öz postlarınızı nümunə kimi əlavə edin)
3. `make replay` — eyni xəbərlə nəticəni dərhal görün

Kod dəyişməyə ehtiyac yoxdur. Bütün üslub qərarları promptlardadır.

## Agentlər

| Agent | Model | İşi |
|---|---|---|
| Scout | Haiku | 9 mənbədən gələn hadisələrdən 3 namizəd seçir |
| Researcher | Sonnet + web | İlkin mənbəyə gedir, faktları sitatla çıxarır |
| Writer | Sonnet | 5 rakurs çıxarır, ən güclüsünü seçir, postu yazır |
| Reviewer | Sonnet | Fakt + skeptik oxucu + risk — üç obyektiv, bir çağırış |
| Reviser | Sonnet | Yalnız lazım olanda işə düşür + səs qoruyucusu |

Deterministik (LLM-siz, pulsuz): çarpaz mənbə təsdiqi · klişe filtri ·
LinkedIn kəsilmə önizləməsi · təkrar filtri · sütun balansı.

## Şəkil zənciri (M2)

Visual Director postu oxuyur və vizual **növünü** seçir:

| Növ | Nə vaxt | Nəticə |
|---|---|---|
| `chart` / `bars` | 2+ rəqəm, **eyni vahiddə** | Sütunlu qrafik |
| `chart` / `stats` | Rəqəmlər var, vahidlər fərqli | Göstərici sətirləri |
| `card` | Güclü ifadə, rəqəm yox | Tipoqrafik kart |
| `photo` | Hadisə/obyekt | Pexels fotosu |

Vahid qoruyucusu deterministikdir: faizlə əmsalı bir oxda müqayisə edən
saxta qrafik heç vaxt yaranmır.

Render: HTML → Chrome headless → **1200×1500 PNG** (LinkedIn-in 4:5 formatı).
Inter şrifti repo-ya yığılıb — Azərbaycan hərfləri hər mühitdə düzgün çıxır.
Hər şəkillə birlikdə **alt-text** yaradılır (əlçatanlıq).

## Telegram təsdiqi (M3)

Post hazır olanda Telegram-a şəkil + mətn + 6 düymə gəlir:

```
✅ Yayımla      🏦 Banka at
🖼 Başqa şəkil  🔄 Yenidən yaz
✏️ Mətni dəyiş  ❌ Keç
```

**Mətni dəyiş** — sabit forma yoxdur, adi cümlə ilə yazırsınız:
*«tonu yumşalt, ikinci bəndi at, sondakı sual daha konkret olsun»*

**Bank** — təsdiqlədiyiniz postlar yığılır. Zəif xəbər günü bankdan
yayımlanır, ardıcıllıq pozulmur. Bazar günü 5 postu bir dəfəyə
təsdiqləyib həftəni bağlaya bilərsiniz.

**Əmrlər:** `/status` `/bank` `/pause` `/resume` `/skip` `/help`

**Yayım vaxtı ayrıdır:** siz səhər təsdiqləyirsiniz, sistem
`PUBLISH_HOUR_UTC` saatında ±20 dəqiqə təsadüfi sapma ilə yayımlayır.

### Telegram qurulumu (2 dəqiqə)

1. Telegram-da **@BotFather** → `/newbot` → adı seçin → token alın
2. Tokeni `.env`-ə yazın: `TELEGRAM_BOT_TOKEN=...`
3. Yaratdığınız bota bir söz yazın (ilk mesajı siz göndərməlisiniz)
4. `make tg-chatid` → çıxan `TELEGRAM_CHAT_ID`-ni `.env`-ə yazın
5. `make doctor` → yaşıl ✓

## LinkedIn yayımı (M4)

```
təsdiq → cədvəl → make publish → şəkil yüklənir → post → birinci şərh
                                        ↓
                         Telegram: link + 🗑 10 dəqiqəlik geri-al
                                        ↓
                            +30dq və +2saat şərh xatırlatması
```

**İki təhlükəsizlik mexanizmi:**

1. **Kilid** — cron və əl ilə işə salma eyni anda yayım etmir.
2. **`publishing` statusu** API çağırışından *əvvəl* diskə yazılır. Proses
   həmin anda ölsə, sistem avtomatik təkrar cəhd **etmir** və sizə xəbər
   verir — ikiqat post geri qaytarıla bilməz.

**Çatım detalları:** mənbə linki post gövdəsində yox, **birinci şərhdə**
(gövdədəki xarici link alqoritmik çatımı azaldır). Şəkilə **alt-text**
əlavə olunur. Yayım vaxtına ±20 dəqiqə sapma verilir.

### LinkedIn qurulumu (~20 dəqiqə, bir dəfəlik)

`make li-auth` işlədin — addım-addım təlimat çıxaracaq. Qısaca:

1. **Company Page** yaradın (pulsuz; app üçün mütləqdir, məzmun lazım deyil)
2. **linkedin.com/developers** → app yaradın
3. **Products** → «Sign In with LinkedIn using OpenID Connect» + «Share on LinkedIn»
4. **Auth** → redirect URL: `http://localhost:8765/callback`
5. Client ID/Secret → `.env`
6. `make li-auth` → brauzerdə təsdiq → token `state/linkedin.json`-a yazılır

⚠️ **Token 60 gün yaşayır.** Refresh token yalnız partnyor app-lərə verilir,
ona görə iki ayda bir `make li-auth` təkrarlanmalıdır. `make doctor`
7 gün əvvəldən xəbərdarlıq edir.

## Avtomatlaşdırma (M5)

Üç iş axını, hamısı GitHub Actions-ın pulsuz limitində:

| Workflow | Cron (UTC) | Nə edir |
|---|---|---|
| `prepare.yml` | `30 4 * * 1-5` | Post + şəkil hazırlayır, Telegram-a göndərir |
| `tick.yml` | `*/10 5-6` + `0 7-19` | Cavabları emal edir · yayımlayır · xatırladır |
| `health.yml` | `0 6 * * 1` | Həftəlik hesabat + token müddəti xəbərdarlığı |

`tick` üç işi bir qaçışda birləşdirir — Actions dəqiqələrini iki dəfə azaldır.
Cavab gecikməsi: postdan sonrakı 2 saatda **≤10 dəqiqə**, sonra saatda bir.

**Aylıq sərf: ~730 / 2000 dəqiqə.**

### Dizayn qərarları

- **Növbə özü-özünə yetərlidir** — `research`, `angles`, `director` və şəkil
  elementin içində saxlanılır, çünki `respond`/`publish` işləri `prepare`-in
  müvəqqəti fayllarını görmür.
- **`concurrency: avtopost-state`** — iki iş axını eyni anda vəziyyət yazmır.
- **Push rebase ilə 3 dəfə təkrarlanır** — yarış vəziyyəti itki yaratmır.
- **«Xəbər yoxdur» nasazlıq deyil** (çıxış kodu 5) — yalançı həyəcan gedmir,
  yayım bankdan olur.
- **`/pause`** — `prepare` işi başlamazdan əvvəl yoxlayır.
- **Şəkillər 30 gündən sonra təmizlənir** — repo şişmir.

### Qurulum

```bash
git init && git add -A && git commit -m "ilkin"
gh repo create avto-post-linkedin --private --source=. --push
```

Sonra **Settings → Secrets and variables → Actions**:

| Secret | Haradan |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` |
| `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` | @BotFather · `make tg-chatid` |
| `PEXELS_API_KEY` | pexels.com/api *(opsional)* |
| `OPENAI_API_KEY` | *(opsional, ödənişli şəkil pilləsi)* |
| `LINKEDIN_ACCESS_TOKEN` · `LINKEDIN_PERSON_URN` · `LINKEDIN_EXPIRES_AT` | `make li-export` |

⚠️ **60 gündən bir:** `make li-auth` → `make li-export` → secret-ləri yeniləyin.
`health.yml` 7 gün əvvəldən Telegram-a xəbərdarlıq göndərir.

## Sonrakı mərhələlər

- **M3b** — Notion Kanban (NOTION_TOKEN tələb olunur)

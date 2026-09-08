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
| `make test` | 43 oflayn test (saniyələr, şəbəkəsiz) |
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
| `make notion-setup` | Notion bazasını tap/yarat |
| `make notion-sync` | Notion ↔ növbə sinxronizasiyası |
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

### Foto mənbələri

Real foto lazım olanda **4 mənbədə paralel** axtarılır və nəticələr
növbələşdirilir (hər mənbənin ən yaxşısı əvvəl):

| Mənbə | Açar | Qeyd |
|---|---|---|
| **Openverse** | **lazım deyil** | 800M+ CC şəkil, dərhal işləyir |
| Pexels | pulsuz | yüksək keyfiyyət |
| Unsplash | pulsuz | `unsplash.com/developers` → Demo app |
| Pixabay | pulsuz | `pixabay.com/api/docs` |

1200×1500-ə böyüdüləndə bulanıq görünəcək kiçik şəkillər avtomatik süzülür.

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

**Əmrlər:**

| Əmr | Nə edir |
|---|---|
| `/topic <link>` | **Öz tapdığınız linkdən post yazır** — ən çox işlədəcəyiniz əmr |
| `/preview` | Növbəti yayımlanacaq postu göstərir |
| `/status` | Bank, növbəti yayım, rejim |
| `/bank` | Bankdakı postların siyahısı |
| `/pause` · `/resume` | Məzuniyyət rejimi |
| `/skip` | Gözləyən postu keçir |

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

## Notion Kanban (M3b)

Telegram təsdiq üçün əladır, uzun mətni redaktə etmək üçün yox.
Notion bu boşluğu doldurur.

```bash
make notion-setup     # bazanı tapır və ya yaradır
make notion-sync      # iki tərəfli sinxronizasiya
```

⚠️ **Notion-un klassik tələsi:** inteqrasiya yaratmaq kifayət deyil.
Səhifəni açıb **··· → Connections → inteqrasiyanı əlavə etmək** lazımdır,
yoxsa API `object_not_found` qaytarır.

Sinxronizasiya iki tərəflidir: kartı «Bank» sütununa sürüşdürsəniz növbədə
də status dəyişir; kartın mətnini redaktə etsəniz post yenilənir.
Yayımlanmış postun statusunu Notion-dan dəyişmək olmur — orada həqiqət
mənbəyi LinkedIn-dir.

## Lokal işləmə + CI eyni anda

Həm lokalda, həm GitHub Actions-da işlədirsinizsə, hər ikisi `state/`
qovluğunu dəyişir. Lokal qaçışdan **əvvəl** həmişə:

```bash
git pull --rebase
```

Unutsanız `git pull` xəta verir — o zaman lokal dəyişikliyi saxlayıb
əl ilə birləşdirmək lazım gəlir.

## Lokal ehtiyat cron (macOS launchd)

GitHub Actions cron-u bəzən gecikir və ya yeni repozitoriyalarda saatlarla
işə düşmür. Lokal cron bu boşluğu doldurur — **əvəz etmir, ehtiyat rolundadır.**

```bash
make cron-install     # quraşdır
make cron-status      # vəziyyət
make cron-log         # jurnal
make cron-uninstall   # sil
```

| Agent | Vaxt | İş |
|---|---|---|
| `com.avtopost.prepare` | iş günləri **09:30** Bakı | post hazırlayır |
| `com.avtopost.tick` | hər **15 dəq**, 09:00–21:00 | cavablar · yayım · xatırlatma |

GitHub `prepare`-i 08:30-da işlədir, lokal isə **09:30-da** — yəni yalnız
GitHub işə düşməyibsə.

### İkiqat postun qarşısı necə alınır

Bu, ən vacib məqamdır. Dörd qoruyucu var:

1. **Git sinxronizasiyası** — hər qaçışdan əvvəl `git pull`, sonra `git push`.
   Lokal və GitHub eyni vəziyyəti görür.
2. **Günlük yoxlama** — `prepare` bu gün post yaradılıbsa (kim tərəfindənsə)
   sadəcə atlanır.
3. **Kilid** — iki lokal proses eyni anda işləmir.
4. **`linkedin_urn` yoxlaması** — post bir dəfə yayımlanıbsa təkrar
   yayımlanmır.

### Telegram dinləyicisi ilə ziddiyyət

Telegram-ı eyni anda yalnız bir proses dinləyə bilər (409 Conflict).
Ona görə:

- `make watch` işləyirsə, cron `poll` addımını **atlayır** (jurnalda görünür)
- 409 xətası nasazlıq sayılmır — digər dinləyici yeniləməni götürür

### Məhdudiyyət

Mac yuxuda və ya söndürülü olsa işləmir. Oyananda buraxılmış qaçış
icra olunur (launchd-ın davranışı).

## Sağlamlıq monitorinqi — addım-addım

Daxili bildirişlər yalnız **sistem işləyəndə** işləyir. Sistem tamamilə
dayansa (GitHub sınsa, cron işə düşməsə, token bitsə) sizə heç nə gəlməz.
Xarici monitor məhz bunun üçündür: gözlənilən vaxtda siqnal almasa
**sizə** xəbər verir.

### 1. healthchecks.io-da check yaradın (2 dəqiqə)

1. **healthchecks.io** → **Sign Up** (pulsuz, kart tələb etmir)
2. **Add Check** düyməsi
3. Sahələri doldurun:

   | Sahə | Dəyər | Niyə |
   |---|---|---|
   | Name | `Avto-post prepare` | ad |
   | Period | `1 day` | gündə bir post hazırlanır |
   | Grace Time | `3 hours` | gecikmə payı |

4. **Save**
5. Səhifədə **ping URL** görünəcək:
   `https://hc-ping.com/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`
   → **Copy** düyməsi ilə kopyalayın

### 2. Lokala əlavə edin

`.env` faylını açın, `HEALTHCHECK_URL=` sətrini tapın və yapışdırın:

```
HEALTHCHECK_URL=https://hc-ping.com/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
```

Yoxlayın:

```bash
make doctor
```

«✓ healthcheck siqnalı göndərildi» görsəniz, healthchecks.io səhifəsində
check yaşıl olacaq.

### 3. GitHub-a əlavə edin

```bash
gh secret set HEALTHCHECK_URL
```

Əmr sizdən dəyəri soruşacaq — URL-i yapışdırıb **Enter**, sonra
**Ctrl+D** basın.

*Alternativ (brauzerdən):* repo → **Settings** → **Secrets and variables**
→ **Actions** → **New repository secret** → Name: `HEALTHCHECK_URL`,
Secret: URL → **Add secret**

### 4. Bildiriş kanalını seçin

healthchecks.io → check → **Integrations** tabı. E-poçt avtomatik
qoşulub; istəsəniz Telegram, Slack və s. əlavə edin.

### Nə baş verir

| Vəziyyət | Siqnal | Nəticə |
|---|---|---|
| Workflow başlayır | `/start` | «işləyir» |
| Uğurla bitir | `/` | yaşıl, sayğac sıfırlanır |
| Xəta ilə bitir | `/fail` | **dərhal xəbərdarlıq** |
| Ümumiyyətlə işə düşmür | siqnal yoxdur | **3 saat sonra xəbərdarlıq** |

Sonuncu ən vacibidir — sistemin *səssiz ölümünü* tutan yeganə mexanizmdir.

## Testlər

```bash
make test     # 43 test, ~0.05 saniyə, şəbəkə və LLM olmadan
```

Əhatə: klişe filtrləri · LinkedIn kəsilməsi · klaster balı · növbə həyat
dövrü · vaxt formatı · LinkedIn escape · tədqiqat keyfiyyəti · vahid
qoruyucusu · Notion uyğunlaşdırma · JSON çıxarma · təsdiq axını · yayım
qoruyucuları · RSS/Atom parse · `/topic` axını.

CI-də hər push-da və `prepare` işə düşməzdən **əvvəl** qaçır — sınıq
kodla kvota yandırmağın mənası yoxdur.

## Keyfiyyət qoruyucuları

| Qoruyucu | Nə edir |
|---|---|
| Doldurucu tədqiqat aşkarlanması | Researcher «Test claim» kimi süni fakt qaytarsa axın dayanır — faktsız post yazılmır |
| Minimum bal həddi | Reviewer 5/10-dan aşağı bal veribsə yayım bloklanır (`--force` ilə keçilir) |
| Klişe filtri | AZ və EN klişeləri deterministik tutulur |
| Vahid qoruyucusu | Faizlə əmsalı bir oxda müqayisə edən saxta qrafik yaranmır |
| İkiqat post qoruması | `publishing` statusu API çağırışından əvvəl yazılır |

## Agent büdcələri

Abunəlikdə pul xərci yoxdur, amma kvota var. Ölçülmüş bir qaçışda
Researcher **122 000 token** yedi, çünki səhifədən səhifəyə gəzirdi.
İki qoruyucu qoyulub:

- Promptda sərt hədd: **1 WebSearch + ən çoxu 2 WebFetch**
- `--max-budget-usd` sərt həddi (büdcə aşılanda təkrar cəhd edilmir)

Nəticə: **122 781 → 20 052 token (84% azalma)**, üstəlik keyfiyyət artdı.

⚠️ Tur həddi çox sərt olsa (8 tur) agent araşdırmanı bitirə bilmir və
sxemi doldurmaq üçün süni fakt yazır. Hazırkı hədd **14 turdur**;
doldurucu aşkarlansa axın dayanır.

## Sonrakı mərhələlər

- **M3b** — Notion Kanban (NOTION_TOKEN tələb olunur)

# Təhvil sənədi — yeni sessiya üçün

> Bu fayl söhbət kontekstini əvəz etmək üçündür. Yeni sessiyada
> **əvvəlcə bunu oxu**, sonra `README.md`-yə bax.
> Son yenilənmə: 09.09.2026

---

## Layihə nədir

AI xəbərlərindən **Azərbaycan dilində** LinkedIn postu hazırlayan agent
sistemi. Sahibi: Samir Nabiyev.

**LLM xərci $0** — Claude Pro abunəliyi ilə işləyir (`claude -p` başsız
rejim, `CLAUDE_CODE_OAUTH_TOKEN`). Ölçülmüş: ~90k token / post.

Axın:
```
9 RSS mənbəsi → çarpaz təsdiq → Scout 3 namizəd verir
  → istifadəçi Telegram-da seçir → Researcher → Writer → Reviewer → Reviser
  → şəkil → Telegram təsdiqi → cədvəl → LinkedIn → arxiv
```

---

## Hazırkı vəziyyət (09.09.2026)

| | |
|---|---|
| Kod | ~10 300 sətir · 157 test (hamısı keçir, 0.15s, oflayn) |
| Repo | `github.com/nabiyevsamir-002/avto-post-linkedin` (private) |
| Workflow | `prepare` · `tick` · `health` · `test` — hamısı aktiv, cron işləyir |
| Lokal cron | launchd: `prepare` (08:35) · `tick` (15 dəq) · `watch` (daimi) |
| Dinləyici | launchd `com.avtopost.watch` — KeepAlive, öz-özünə qalxır |
| LinkedIn | Samir Nabiyev, token 59 gün qalır |
| Kalibrləmə | ✅ tamamlanıb (positioning 7/7, voice 2 nümunə) |

**Növbə:** 1 post cədvəldə (sabah 12:03), 2 post təsdiq gözləyir.

**✅ İlk real LinkedIn postu yayımlandı** — 09.09.2026, 11:45
(«abunəçilərdən Claude tokenlərinin oğurlanması», Claude qrafiki ilə).
Sürət həddi işlədi: ikinci post avtomatik sabaha keçdi.
`urn:li:share:7503357866381127681`

---

## ⚠️ Bahalı dərslər — təkrarlama

Bunlar sınaq-səhv yolu ilə tapılıb, hər biri vaxt aparıb:

1. **`make watch` dayandırılanda vəziyyət itə bilərdi** → bütün JSON
   yazıları atomikdir (`src/store.py`, temp + `os.replace` + `.bak`).
   Yeni vəziyyət faylı əlavə edəndə **mütləq `store.write_json`** işlət.

2. **Bank gün ərzində onlarla post yayımlayırdı** (5 post 75 dəqiqəyə).
   İki hədd qoyulub: `MAX_POSTS_PER_DAY=1`, `MIN_HOURS_BETWEEN_POSTS=6`.
   `pick_due()` **və** `publish_item()` — iki nöqtədə yoxlanılır.

3. **GitHub və lokal cron eyni postu iki dəfə yayımlaya bilərdi.**
   Lokal artıq yalnız GitHub ölübsə yayımlayır; CI `state/ci_heartbeat.json`
   yazır (`GITHUB_RUN_ID` olan siqnal sayılır, lokal özünü CI kimi göstərə bilmir).

4. **macOS-da headless Chrome şəkli yazır, amma çıxmır** → prosesi
   gözləmək yerinə faylın sabitləşməsini izləyib `terminate` edirik
   (`src/images/render.py::_run_chrome`).

5. **Telegram `answerCallbackQuery` gec çağırılanda 400 verir** və
   əvvəllər əməliyyatı kəsirdi → indi xəta udulur, düymələr işləyir.

6. **`Item` naməlum sahələri atır** — sxem dəyişəndə köhnə `queue.json`
   sistemi sındırmamalıdır (karusel silinəndə real olaraq sındırdı).

7. **LinkedIn API versiyası müddətlidir** → avtomatik aşkarlanır,
   `426` alınanda yeni versiya ilə təkrar cəhd edilir. `.env`-də boş buraxılıb.

8. **Testlər oflayndır** — `tests/test_core.py`-də şəbəkə qoruyucusu var.
   Test şəbəkəyə çıxsa dərhal xəta verir (əvvəl 10.5s sürürdü, indi 0.14s).

9. **Karusel silindi** — istifadəçi «slaydlar darıxdırıcıdır, heç kim
   baxmır» dedi. Git tarixçəsindədir (`c805647`), qaytarmaq lazım deyil.

10. **Model bəzən JSON əvəzinə alət-çağırışı sintaksisi ilə cavab verir.**
    Onda ilk sahə qalan hamısını udur: `design_brief` içində
    `</design_brief><parameter name="pexels_query">…` ilişib qalır.
    `extract_json` bunu tutmur — cavab formal olaraq düzgün JSON-dur.
    `src/images/__init__.py::recover_tagged_fields` bərpa edir.
    **Yeni agent əlavə edəndə bu bərpanı da qoş.**

11. **Səssiz ehtiyata düşmək = gizli nasazlıq.** `photo_queries()`
    heç nə tapmayanda `["technology abstract"]` qaytarırdı və bunu
    heç kim görmürdü — kvant postu 3 mücərrəd klişe ilə getdi.
    İndi `queries_are_generic()` var və `make image` xəbərdarlıq edir.
    **Qayda: ehtiyat variant həmişə görünən olmalıdır.**

12. **Telemetriya real vaxtı ölçmürdü.** `duration_ms` claude CLI-nin
    öz ölçüsündən götürülürdü — kvota pəncərəsi və proses növbəsi ona
    daxil deyil. Bir şəkil qaçışı 6 saat sürdü, telemetriya 142s dedi.
    İndi `AgentResult.wall_ms` (real divar saatı) və `.stalled` var.
    **«Ölçmə» prinsipi alətin özü düzgün ölçdükdə işləyir.**

13. **Sınaq aləti real axını əks etdirməlidir.** `make image`
    `director["_post"]`-u qoymurdu, `approval.py` isə qoyurdu — nəticədə
    təkrar filtri və model seçimi yalnız Telegram axınında işləyirdi.
    Sınaq yaxşı görünürdü, real nəticə fərqli idi.

14. **Telegram bloklananda dinləyici «gözləyir…» yazırdı.** `URLError`
    → `OSError` alt sinfidir və mesajı «timed out» olur, ona görə uzun
    polling-in NORMAL sükutu (bağlantı qurulur, yeniləmə gəlmir) ilə
    TAM BLOK (bağlantı heç qurulmur) eyni sayılırdı. İndi 3 ardıcıl
    sükutdan sonra `getMe` ilə əlaqə yoxlanır → `TelegramUnreachable`.
    Xəbərdarlıq **konsola və healthcheck-ə** gedir, Telegram-a yox —
    bloklu kanalla blok haqqında bildiriş göndərmək mənasızdır.
    *Ölçüldü 09.09.2026 16:59: xəbərdarlıq ~3 dəqiqəyə çıxdı.*

15. **Telegram bloku ARALIQdır — və watch ölüb ölü qalırdı.**
    Blok daimi deyil: 10.09.2026-da 06:30-da bir neçə dəqiqə açıldı
    (düymə məhz onda emal olundu), sonra bağlandı, 13:00-da tam açıldı.
    Üç fərqli mexanizm görülüb: `Errno 60` (paket udulur), `Errno 61`
    (RST qaytarılır), `Errno 8` (DNS kəsilir).
    **Əsl problem bloku keçmək deyil, PƏNCƏRƏNİ TUTMAQ idi** — watch
    `Terminated: 15` ilə öldü və heç kim onu qaldırmadı, düymələr
    bütün gün cavabsız qaldı.
    İndi watch launchd altındadır: `com.avtopost.watch`, `KeepAlive`,
    `ThrottleInterval 30`. *Ölçüldü: proses öldürüldü → 3 saniyəyə
    özü qalxdı.* `make watch` isə launchd dinləyicisi işləyəndə
    xəbərdarlıq edib dayanır (iki dinləyici = Telegram 409).

16. **Arxiv silinən postu saxlayırdı.** `sync_all()` yalnız ƏLAVƏ
    edirdi, `rebuild_index()` isə diskdəki bütün faylları sayırdı —
    LinkedIn-dən çıxarılan post arxivdə əbədi qalırdı (indeks 3
    göstərdi, reallıqda 2 idi). İndi `archive.prune()` var.
    ⚠️ `path_for()` **unikal deyil** — tarix+başlıqdan qurulur, yəni
    yenidən yazılmış post eyni fayla düşür. Prune əvvəlcə saxlanacaq
    yolları toplamalıdır; ilk versiyam bunu etmədi və yayımdakı postun
    faylını sildi.

17. **Lokal ehtiyat CI ilə EYNİ davranmalıdır.** CI `propose`
    işlədirdi (3 namizəd), lokal `prepare` isə `run` — mövzunu sistem
    özü seçirdi. GitHub cron gecikəndə istifadəçi namizəd gözləyir,
    sistem başqa iş görürdü. İndi hər ikisi `TOPIC_SELECTION`-a tabedir.
    Dublikat qoruması da təklifləri sayır (`proposals.prepared_today`)
    — `propose` növbəyə item YAZMIR, ona görə yalnız `queue.json`-a
    baxmaq ikinci namizəd dəstinə səbəb olurdu.
    **Gün sərhədi YERLİ vaxtladır** — cron da yerli işləyir.

18. **GitHub `schedule` qaçışları ATLANIR — gecikmir, ümumiyyətlə
    işləmir.** 10 və 11.09.2026-da CI bütün gün bir dəfə də schedule
    qaçışı etmədi. *Ölçüldü:* eyni gün `push` qaçışı **işlədi** —
    yəni kvota bitməyib, Actions sağdır, problem yalnız `schedule`
    event-indədir. GitHub sənədi bunu təsdiqləyir (yüksək yüklənmə).
    **Nəticə: CI-ya cədvəl üçün GÜVƏNMƏ.** Lokal launchd əsas kanal
    sayılmalıdır, CI isə bonus.
    Ona görə lokal `prepare` 09:30 → **08:35** çəkildi (CI-dan cəmi
    5 dəqiqə sonra). Əvvəl CI atlananda istifadəçi bir saat gözləyirdi.
    Təkrarın qarşısını hər iki tərəfdə `prepared_today()` alır.

19. **Qərar ağacında sıra hər şeyi həll edir.** `news` formatı quruldu,
    amma prompt «2+ rəqəm varsa → chart» qaydasını BİRİNCİ sırada
    saxlayırdı. Demək olar ki, hər xəbərdə rəqəm var (qiymət, tarix,
    versiya), ona görə `news` praktiki olaraq heç vaxt seçilmirdi —
    istifadəçi səhər yenə köhnə dizayn aldı.
    İndi `news` birincidir, `chart` isə yalnız «rəqəmləri çıxarsan
    post dağılır» halındadır.
    **Dərs: yeni format əlavə edəndə seçim qaydasının SIRASINI yoxla,
    təkcə formatın özünü deyil.**

20. **Loqo `<img>` + base64 ilə İŞLƏMİR.** SVG ana sənədin rəngini
    görmür, `currentColor` ölür. `render.logo_svg()` faylı INLINE
    hopdurur — `brand_block` və `news.py` ikisi də onu işlədir.
    Yan təsir: inline loqo köhnə «vurğu rəngli zolaq» ehtiyatını əvəz
    etdi və `BRAND_COLOR` tətbiq olunmaz qaldı — mövcud test tutdu.

---

## Üzərində işlədiyimiz son məsələ

**Şəkillərin mövzuya uyğunluğu.** İstifadəçi «3 fotodan yalnız 1-i uyğun
gəldi» dedi.

Tapılan səbəb: Visual Director hərfi sorğular yazırdı
(`«laptop login screen dark»`), sonra da söz üst-üstə düşməsi ilə
sıralama əşya metaforalarını (paslı kilid) insanlı səhnələrdən yuxarı
qaldırırdı — fotoqraflar əşyaları daha hərfi etiketləyir.

Edilənlər:
- **Üç səviyyəli sorğu**: səhnə → metafora → geniş (`photo_queries`)
- **Təkrar filtri**: eyni konseptli şəkillər atılır (14 → 6 namizəd)
- **Model seçir**: `prompts/photo_picker.md` — Haiku təsvirləri oxuyub
  **üç FƏRQLİ konsept** seçir (insanlı səhnə · atmosfer · simvolik obyekt)
- Hər variantın **niyə seçildiyi** Telegram-da göstərilir
- Ölçüldü: kapüşonlu haker 6-cı sıradan 2-ci sıraya qalxdı, 130s → 62s

### 09.09.2026 (günorta) — düzəlişlər Telegram-a çatmamışdı

İstifadəçi albomu yoxlamağa hazırlaşırdı. **Ölçmə göstərdi ki, albom
köhnə idi:** şəkillər 09:15-də çəkilmişdi, düzəlişlər isə 09:40 və
10:14-də gəlmişdi. Yəni baxılacaq albom heç bir düzəlişi görməmişdi.

Üstəlik üç ayrı baq tapıldı (hamısı ölçmə ilə, hamısına regresiya testi):

| Baq | Faktiki nəticə | Düzəliş |
|---|---|---|
| Director cavabı parse olunmurdu | kvant postu üçün sorğu `['technology abstract']` | `recover_tagged_fields()` |
| Ehtiyata düşmək səssiz idi | heç kim görmürdü | `queries_are_generic()` + xəbərdarlıq |
| Təkrar filtri modeldən asılı idi | iki eyni kolba şəkli | dedupe artıq həmişə işləyir |

Bərpadan sonra sorğu: `technology abstract` → `superconducting quantum
chip lab`. Yeni director düzgün 3 səviyyəli sorğu verir:
`researcher adjusting lab equipment night` · `focused scientist quantum
lab equipment` · `quantum computing laboratory abstract blue`.

**Ayrıca tapıldı:** `make image` `director["_post"]`-u qoymurdu,
`approval.py` isə qoyurdu — sınaq aləti real axından fərqli nəticə
verirdi. Bu, ölçməni yanıltdı, düzəldildi.

Hələ də uyğunsuzluq qalsa, növbəti addım **AI şəkil generasiyası**
(`OPENAI_API_KEY`, ~$0.03/şəkil) — stok kitabxanalarda sadəcə uyğun
şəkil olmaya bilər.

---

## Yeni: `news` vizual formatı (10.09.2026)

İstifadəçi bəyəndiyi bir Azərbaycan səhifəsinin (Tedroid) kart formatını
istədi: **yuxarıda foto, aşağıda iri başlıq zolağı**. Skrinşotlardan
struktur çıxarıldı və `visual_type: "news"` kimi quruldu.

**Niyə vacibdir:** bu formatda **başlıq mənanı daşıyır, foto isə fondur**.
Ona görə 09.09-da 6 saat sərf etdiyimiz «stok foto mövzuya uyğun gəlmir»
problemi xeyli yumşalır — foto mükəmməl olmasa da kart işləyir.

**Dizayn SABİTDİR, modelə buraxılmır** (`src/images/news.py`). Model
yalnız məzmun verir: `headline` (70-95 simvol, nida ilə), `support`
(kapsul detalı), `kicker` (kateqoriya), `accent_words` (1-2 vurğu sözü).
Səbəb `render.brand_block` şərhindəki ilə eynidir: brend ardıcıllığı
təkrarlanmaqdan yaranır.

Pillə sırası: `("news", True)` — dairəvi ikinci şəkillə, `("news", False)`
— onsuz. Telegram-da «başqa şəkil» ilə seçilir. Foto mənbəsi yoxdursa
adi kartlara düşür.

Ölçülər istifadəçi ilə birlikdə seçildi (`out/proto/` altında sınaqlar):
dairə **290px**, `top:140 right:44`. **Dərs:** ilk versiyada dairə eyni
290px idi, amma `top:330 right:-70` — kadrın ortasına düşüb arxadakı
adamı örtürdü. Problem ölçüdə deyil, **yerləşmədə** idi.

Loqo: `assets/logo.svg` (SN monoqram, `currentColor`). **İNLINE** qoşulur,
base64 data URI kimi YOX — `<img>` daxilindəki SVG ana sənədin rəngini
görmür.

⚠️ **`BRAND_NAME` CI-da təyin edilməyib.** `news.build()` adı kənardan,
`images.brand()` vasitəsilə alır — o, LinkedIn tokenindən ehtiyat ad
götürür. Birbaşa `config.BRAND_NAME` oxunsa, CI-da hazırlanan kart adsız
çıxardı. Workflow-lara `vars.BRAND_NAME` / `vars.BRAND_HANDLE` əlavə
edildi — GitHub-da doldurulsa daha etibarlıdır.

---

## ⏸ Telegram bloku — davam edir

Lokal şəbəkədən `api.telegram.org` TCP 443 bloklanıb (DNS həll olunur,
bağlantı qurulmur; Pexels və GitHub işləyir). Nəticə:

- lokal `watch` düymələrə cavab verə bilmir (indi ən azı xəbərdarlıq edir)
- **CI-dakı `tick` isə şərtsiz `poll` işlədir** → düymələr işləyir, amma
  gecikmə ilə: 05-06 UTC hər 10 dəqiqə, 07-19 UTC saatda bir
- 09.09-un iki albomu göndərilməyib (`out/images/2026-09-09T05-*`)

---

## Növbəti addımlar (istifadəçi seçəcək)

- Bu gün ilk real postun yayımını izləmək
- Şəkil uyğunluğu hələ zəifdirsə → AI generasiya pilləsini açmaq
- `BRAND_COLOR` / `BRAND_LOGO` boşdur — istəsə doldura bilər
- Müzakirə olunmuş, amma qurulmamış: səsli mesaj, həftəlik toplu təsdiq,
  post seriyası, rədd səbəbinin toplanması

---

## Faydalı əmrlər

```bash
make doctor     # bütün inteqrasiyalar
make test       # 116 oflayn test, 0.14s
make smoke      # real API sınağı (LinkedIn-də qaralama yaradıb silir)
make watch      # Telegram dinləyicisi (ani cavab)
make queue      # növbə və bank
make propose    # 3 namizəd göndər
make replay     # eyni xəbərlə yenidən yaz (prompt sınağı)
make li-renew   # token + GitHub secret-ləri yenilə (60 gündən bir)
```

**Telegram əmrləri:** `/topic` `/edit` `/preview` `/now` `/undo` `/skip`
`/status` `/bank` `/health` `/pause` `/resume` `/help` — `/` yazanda
siyahı çıxır, arqumentsiz əmr sual verir, təhlükəlilər təsdiq istəyir.

---

## İş üslubu (istifadəçinin gözləntisi)

- **Cavablar Azərbaycan dilində**
- Fərziyyə yox, **ölçmə**: problemi sınaqla təsdiqlə, sonra düzəlt
- Hər düzəlişə **regresiya testi** yaz
- Öz səhvini tapanda **açıq de**, gizlətmə
- Dəyişiklikdən sonra: `make test` → commit → push → `make watch` yenidən

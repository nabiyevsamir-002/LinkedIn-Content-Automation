# Təhvil sənədi — yeni sessiya üçün

> Bu fayl söhbət kontekstini əvəz etmək üçündür. Yeni sessiyada
> **əvvəlcə bunu oxu**, sonra `README.md`-yə bax.
> Son yenilənmə: **15.09.2026**

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

## Hazırkı vəziyyət (11.09.2026)

| | |
|---|---|
| Kod | ~11 000 sətir · **181 test** (hamısı keçir, 0.2s, oflayn) |
| Repo | `github.com/nabiyevsamir-002/avto-post-linkedin` (private) |
| Lokal cron | launchd: `prepare` (08:35) · `tick` (15 dəq) · `watch` (KeepAlive) |
| Dinləyici | kod/prompt dəyişəndə **özü yenidən yüklənir** (~27s) |
| LinkedIn | Samir Nabiyev · token 57 gün qalır |
| Şəkil | `news` xəbər kartı · SN loqosu · AI fonu aktiv (`OPENAI_API_KEY` var) |
| VPN | qurulub — Telegram sabit işləyir |

**Yayımlanmış: 3 post** (arxivlə uyğun, yoxlanılıb):
- 09.09 — Claude token oğurluğu
- 10.09 — GPT-6 Astra *(ilk `news` kartı)*
- 11.09 — Spirit Airlines / Google data alışı *(ilk AI fonlu kart)*

**Növbə hazırda BOŞDUR** — pending/scheduled/bank sıfır.
Gündəlik hədd bu gün doludur (1 post çıxıb).

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

21. **«Başqa şəkil» ŞABLONU dəyişməməlidir.** Zəncirdə `news`-dən
    sonra Claude tipoqrafik kartları dururdu, ona görə ikinci basışda
    dizayn tamamilə dəyişirdi. İstifadəçi isə eyni kartı BAŞQA FOTO
    ilə gözləyir. İndi `news` zənciri yalnız foto variantlarıdır:
    `[("news", 0), ("news", 1), …]`, payload = fon fotosunun indeksi.
    Claude kartları YALNIZ foto mənbəyi tamamilə işləmədikdə qalır.
    ⚠️ **Köhnə tipoqrafik üslub istifadəçi tərəfindən RƏDD EDİLİB** —
    onu zəncirə geri qaytarma.

22. **`make image` növbəni YENİLƏMİR.** Yalnız fayl və manifest yazır.
    11.09.2026: şəkli yenidən qurdum, `image_path` yenilədim, amma
    `director` növbədə köhnə (`chart`) qaldı — nəticədə Telegram
    düyməsi köhnə plandan işlədi və Claude kartı çıxardı.
    **Şəkli əl ilə dəyişəndə `director`-u da manifestdən köçür.**

23. **Şəkil uyğunsuzluğunun səbəbi MƏNBƏLƏRDƏ deyil, PROMPTDA idi.**
    Aylarla «stok kitabxanalarda uyğun şəkil yoxdur» deyə düşünüldü.
    *Ölçüldü (11.09.2026):*

        4284×5712  Colorful Google logo on modern building exterior
        5304×7952  A modern Microsoft office skyscraper
        4000×6000  Exterior view of Intel's headquarters with logo
        —          Spirit Airlines Aircraft from ACY Terminal

    Hamısı yüksək keyfiyyətlidir və `_big_enough` filtrindən keçir.
    Prompt isə şirkət adlarını QADAĞAN edirdi («Orada YOXDUR: konkret
    şirkətlər»), ona görə director mücərrəd səhnə yazırdı.

    İndi birinci sorğu şirkətin ADI ilədir, ada kontekst sözü qoşulur
    (logo · building · headquarters · store · aircraft · campus).

    ⚠️ İki istisna, hər ikisi ölçülüb:
    - **Yeni/rəqəmsal şirkətlər stokda YOXDUR** — `"OpenAI office"` və
      `"Anthropic office"` sadəcə ümumi şüşəli bina qaytarır.
    - **Çoxmənalı adlar yanıldır** — `"Amazon warehouse"` → tutuquşu
      (macaw, exotic bird). Kontekst sözü məcburidir.

    **Dərs: «mənbə kasaddır» qənaətinə gəlməzdən əvvəl sorğunun özünü
    ölç.** Burada mənbə zəngin, sorğu isə kasad idi.

24. **Dinləyici kodu YADDAŞDA saxlayır — düzəliş ona çatmır.**
    11.09.2026-da bu, ÜÇ dəfə təkrarlandı: düzəliş push olunur,
    istifadəçi düyməni basır və artıq həll edilmiş səhvi yenidən görür.
    İndi `cli.code_fingerprint()` `src/` və `prompts/` mtime-ini izləyir;
    dəyişiklik görünəndə proses özü çıxır, launchd `KeepAlive` onu
    qaldırır. *Ölçüldü: prompt toxundurulandan 27 saniyə sonra
    avtomatik yeniləndi.*
    ⚠️ Bu mexanizm YENİ koddadır — onu ilk dəfə işə salmaq üçün bir
    dəfə əl ilə restart lazım gəldi (toyuq-yumurta).

25. **Promptdakı NÜMUNƏ default-a çevrilir.** `kicker` qaydası belə
    idi: «kateqoriya, 1-2 söz: «SÜNİ İNTELLEKT», «TEXNOLOGİYA»».
    Model nümunəni seçim kimi deyil, cavab kimi götürdü — iflas və
    məlumat satışı haqqında posta da «SÜNİ İNTELLEKT» yazdı.
    İndi sabit siyahı yoxdur, cədvəldə müxtəlif mövzular var və
    açıq qadağa qoyulub.
    **Dərs: promptda bir-iki nümunə vermə — ya heç verme, ya da
    müxtəlif cür 4-5 nümunə ver.**

26. **AI şəkil modelinə KART brifini vermə.** `design_brief` içində
    «üstündə iri xəbər başlığı zolağı» kimi göstərişlər olur; şəkil
    modeli onu hərfi qəbul edib şəklin üstünə mətn çəkir (real hal:
    «CORPORATE SECRECY» SN loqosunun üstünə düşdü). `ai_prompt()`
    yalnız səhnədən qurulur. Ölçülmüş vaxt: 67-160 s, ~$0.03.

27. **İstisna yolu VAR idi, amma səhv TİPƏ baxırdı.** `get_updates`
    409-u `except TelegramError`-da tuturdu, `urllib` isə HTTP xətasını
    `HTTPError` (OSError alt sinfi) kimi atır — yol heç vaxt işləmirdi.
    Nəticə: CI tick-in `poll` addımı lokal uzun polling ilə toqquşanda
    hər dəfə «⚠️ Dinləyicidə xəta» Telegram-a düşürdü. *Ölçüldü
    (12.09.2026):* log-dakı 409 vaxtları CI `chore(state): tick`
    commit-ləri ilə üst-üstə düşür (09:22 və 11:54 UTC). Eyni yolla
    `RemoteDisconnected` (uzun polling-in cavabsız kəsilməsi) də xəta
    sayılırdı. İndi `_is_conflict()` və `_is_blind_poll()` tipdən
    asılı deyil. 409 özü zərərsizdir — yeniləməni CI götürür.
    **Dərs: istisna yolunu yazanda hansı TİPİN gəldiyini real
    traceback-lə yoxla, `str(exc)`-yə güvənmə.**

28. **Limit mesajı dəyişdi, nümunə dəyişmədi — limit «xəbər yoxdur»
    kimi görünürdü.** 14.09.2026 08:35: Scout «You've hit your
    **weekly** limit · resets **6pm**» aldı; `_QUOTA_PAT` yalnız
    «usage limit» və «resets at» tanıyırdı. Nəticə: `QuotaExhausted`
    atılmadı, 3 təkrar cəhd (12 s boş gözləmə), `prepare` log-a
    «uyğun xəbər tapılmadı — bank rejimi» yazdı, Telegram-a xəbərdarlıq
    getmədi — istifadəçi limiti öz hesabından öyrəndi. Nümunə
    genişləndi (`weekly|daily|monthly|session limit`, `hit your limit`,
    `resets 6pm`), cron log-u çıxış kodu 3-ü ayrıca yazır, xəbərdarlıq
    mətni yalnız doğru olanı vəd edir (lokal `prepare` gündə birdir,
    tick namizəd hazırlamır — «bir saat sonra təkrar» yalan idi).
    **Dərs: xarici alətin xəta mətninə bağlı nümunə varsa, real
    mesajı testə qoy — mətn dəyişəndə test sənə deyəcək.**

29. **Promptun azərbaycanca olması cavabın azərbaycanca olmasını
    TƏMİN ETMİR.** Scout promptu tam azərbaycanca idi, amma giriş
    (klasterlər) ingiliscədir — model giriş dilinə düşürdü. *Ölçüldü
    (15.09.2026):* 6 təklif dəstindən 4-ü ingiliscə gəlmişdi, heç kim
    sistemli baxmamışdı. İndi promptda «Dil — MƏCBURİ» bölməsi var
    (sahə-sahə), `pipeline.candidates_in_azerbaijani()` nəticəni
    yoxlayır və səhv Telegram mesajının özündə «⚠️» kimi görünür
    (`Proposal.warnings`). Düzəlişdən sonra ilk real qaçış: 3/3
    azərbaycanca, 14k token.
    **Dərs: çıxış dilini hər mətn sahəsi üçün açıq tələb et və
    nəticəni kodla yoxla — modelin «başa düşməsinə» güvənmə.**

---

## Üzərində işlədiyimiz son məsələ (11.09.2026)

**Şəkil uyğunluğu və dizayn.** İstifadəçi bəyəndiyi bir Azərbaycan
səhifəsinin (Tedroid) kart formatını istədi: yuxarıda foto, aşağıda
iri başlıq zolağı. Format quruldu (`visual_type: news`), sonra bir
neçə qat problem üzə çıxdı və hamısı həll olundu:

| Problem | Kök səbəb | Həll |
|---|---|---|
| Köhnə dizayn çıxırdı | qərar ağacında `chart` birinci idi | `news` standart oldu |
| «Başqa şəkil» şablonu dəyişirdi | zəncirdə Claude kartları vardı | zəncir yalnız `news` variantları |
| Şəkil mövzuya uyğun gəlmirdi | prompt şirkət adlarını **qadağan edirdi** | brend adı + kontekst sözü |
| Uyğun şəkil seçilmirdi | `photo_picker`-də mövzu meyarı YOX idi | 1-ci meyar oldu |
| AI şəkil üstünə mətn yazırdı | `design_brief` AI-ya ötürülürdü | yalnız səhnə ötürülür |
| Kicker həmişə «SÜNİ İNTELLEKT» | prompt nümunəsi default-a çevrilmişdi | mövzudan asılı cədvəl |
| Düzəliş dinləyiciyə çatmırdı | proses kodu yaddaşda saxlayırdı | `code_fingerprint()` |

**Təsdiqlənmiş dizayn** (dəyişdirmə): SN loqosu (inline SVG) + ad +
üfüqi xətt · kicker · foto fonu · sağ yuxarıda dairəvi ikinci şəkil
(290px, `top:140 right:44`) · kapsul (bir sətir, `_fit_capsule`) ·
tünd başlıq zolağı + mavi vurğu sözlər · sol altda profil linki.

⚠️ **Köhnə tipoqrafik üslub (Claude `chart`/`card`) istifadəçi
tərəfindən RƏDD EDİLİB.** O, yalnız bütün foto mənbələri sıradan
çıxanda ehtiyat kimi qalır. Test `test_plan_is_only_news_variants`
onu zəncirə qaytarmağa qoymur.

**AI generasiya açıqdır:** zəncirin son pilləsi, ~$0.03, 67-160 saniyə.
Sonda «başqa şəkil» AI-nı təkrar çağırır — zəncir bitmir.

**AI kadrı növbə ilə dəyişir** (11.09.2026, sonuncu iş): hər çəkiliş
`images.SHOT_VARIANTS`-dan növbəti kadrı alır — yaxın plan → geniş
plan → yandan → qürub işığı → gecə → yenidən. Sayğac ayrıca vəziyyət
deyil, `out/images/<run>/NN-bg-aiNN.png` fayllarının sayıdır
(`ai_take()`), ona görə Telegram və `make image` eyni cür növbələyir.
Əvvəlki fonlar üstünə yazılmır. Kadr adı etiketdə və «yaradılır…»
mesajında görünür. *Real şəkillə hələ ölçülməyib* — növbə boş idi;
ilk AI çəkilişində fərqin doğrudan görünüb-görünmədiyinə bax.

---

## Yarımçıq qalan iş

Yoxdur. Son açıq təklif (AI kadr variasiyası) qurulub — yuxarıya bax.

---

## Növbəti addımlar (istifadəçi seçəcək)

Müzakirə olunmuş, amma qurulmamış:
- `BRAND_COLOR` boşdur (loqo artıq var: `assets/logo.svg`)
- Uğursuz Telegram bildirişlərini növbəyə alıb sonra göndərmək
- Səsli mesaj · həftəlik toplu təsdiq · post seriyası
- Rədd səbəbinin toplanması (niyə «Keç» basıldı)

⚠️ **GitHub `schedule` cron-una GÜVƏNMƏ** — 10 və 11.09-da bütün gün
işləmədi (bax dərs 18). Lokal launchd əsas kanaldır.

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

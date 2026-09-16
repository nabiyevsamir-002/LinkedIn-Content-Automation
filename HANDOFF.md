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
| Kod | ~12 600 sətir · **223 test** (hamısı keçir, 0.4s, oflayn) |
| Repo | `github.com/nabiyevsamir-002/avto-post-linkedin` (private) |
| Lokal cron | launchd: `prepare` (08:35) · `tick` (15 dəq + girişdə dərhal; 09-18 telafi) · `watch` (KeepAlive) |
| Dinləyici | kod/prompt dəyişəndə **özü yenidən yüklənir** (~27s) |
| LinkedIn | Samir Nabiyev · token 57 gün qalır |
| Şəkil | `news` kartı · **foto müfəttişi** (model şəkli görür, qaydalar kodda) · kollaj · AI fonu yalnız şəxssiz hekayədə |
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

30. **«Namizədlər darıxdırıcıdır» — səbəb promptda deyil, PƏNCƏRƏDƏ idi.**
    İstifadəçi 15.09.2026-da daha maraqlı xəbər tələb etdi. Xam xəbərləri
    Scout-un gördüyü kimi yenidən qurdum — üç qat problem:
    (1) `_clusters_payload` 28 klasterdən **12-ni** verirdi; günün ən
    maraqlıları (agentlər həmkarlarını ələ verdi, Microsoft AI kodeksi,
    RubyGems boşluğu) siyahıya düşmürdü; (2) sıralama mənbə çəkisinə
    görə idi — Google bloqunun «DevFest is back»-i (1.53) əsl xəbərlərin
    (1.2-1.28) üstündə; (3) promptun 1-ci meyarı «praktik dəyər» vendor
    keys-stadilərinə aparırdı (Fyxer, Perplexity — tək mənbəli, əslində
    qadağan kateqoriya). Ayrıca: eyni hadisə fərqli başlıqlarla 4 ayrı
    klasterə düşürdü («pump the brakes / hit the brakes / doomer turn /
    warnings of doom») — Jaccard bunu tutmur, indi prompt Scout-dan
    siyahını bütöv oxuyub eyni hadisəni tanımağı istəyir.
    Düzəliş: `SCOUT_WINDOW=24`; tək mənbəli vendor bloqu −0.3; prompt:
    «oxucu sürüşdürməyi dayandıracaqmı?» birinci meyar, 5 müxtəlif
    diqqət növü (dərs 25), darıxdırıcı siyahısı, məcburi `hook` sahəsi
    (sxemdə `required`), Telegram-da 💬 kimi görünür.
    *Ölçüldü, eyni giriş:* köhnə → slop / Fyxer / Perplexity;
    yeni → slop 9 / Glass Imaging $300M 8 / agent-xəbərçilər 8 (MIT TR,
    köhnə pəncərədə yox idi). 18.8k token (əvvəl 14.4k).
    **Dərs: «model pis seçir» deməzdən əvvəl modelin NƏ GÖRDÜYÜNÜ
    çap et — seçim keyfiyyəti pəncərə keyfiyyətindən yuxarı ola bilməz.**

31. **«Başqa xəbər» düyməsi (15.09.2026).** Scout indi 6 namizəd verir:
    3 göstərilir, 3 ehtiyat (`Proposal.offset`, `.shown`, `PAGE=3`).
    İlk basış ehtiyatdan gəlir — pulsuz, ani. Ehtiyat bitəndə
    `pipeline.propose_more()` Scout-u QALAN klasterlərlə çağırır
    (göstərilənlər xaric, pəncərə məhdud deyil). Düymələr MÜTLƏQ
    indeks daşıyır (`pick4`), ekranda nömrə nisbidir — pəncərə sürüşəndə
    seçim düz düşür. «Sən seç» və auto-pick pəncərənin 1-cisini götürür
    (əvvəlkiləri istifadəçi rədd edib). Ehtiyat gətirilməsə köhnə
    düymələr SİLİNMİR — istifadəçi düyməsiz qalmasın.
    ⚠️ `cluster_id` təklifdə saxlanmış `items`-dən qurulur —
    `_items_from_proposal()` hər iki yerdə (yazı, ehtiyat) eyni siyahını
    işlədir; təzə RSS çəkilsə indekslər sürüşər və BAŞQA xəbər yazılar.
    *Ölçüldü:* 6 namizəd 23.7k token (3 namizəd 18.8k idi).
    ⚠️ Haiku-nun azərbaycancası hook-larda kobuddur («spam-spam etyib»,
    «xilafını eşittilər») — seçim düzgündür, mətn çirklidir. Həll
    olunmayıb; variant: `MODEL_SCOUT`-u böyütmək (+~24k token/gün).

32. **Uğursuz seçim təklifi DALANA salırdı.** 15.09.2026: istifadəçi
    VPN-siz düymə basdı → Researcher (WebFetch) mənbələri aça bilmədi →
    «heç bir fakt tapılmadı» (18.8k token boşa) → təklif `picked` qaldı,
    düymələr silindi — təkrar seçmək mümkün deyildi, istifadəçi əl ilə
    müdaxilə istədi. İndi `_handle_pick` yazı alınmayanda (xəta və ya
    `ok=False`) `proposals.reopen()` edir və namizədləri düymələrlə
    yenidən göndərir; pəncərə (`offset`) saxlanılır. Mövzu «görülmüş»
    sayılmır — `mark_seen` yalnız təsdiqdən sonradır, ona görə eyni mövzu
    təkrar seçilə bilər.
    **Dərs: hər uğursuz addımdan sonra istifadəçinin NÖVBƏTİ hərəkəti
    mümkün olmalıdır — «alınmadı» mesajı kifayət deyil, düymə qayıtmalıdır.**

33. **`cluster_id` MÖVQE indeksidir və sabit deyil — sistem BAŞQA xəbər
    yazdı.** 15.09.2026: istifadəçi «AI botlar» seçdi (indeks 1); klaster
    balı 3 rəqəmə yuvarlaqlanır, təzəlik balı hər dəqiqə azalır, «AI
    botlar» ilə «Tramp/Huang» arasında 0.001 fərq var idi — 23 dəqiqə
    sonra yerləri dəyişdi və `write_from_proposal` indeks 1-də duran
    Tramp xəbərini yazdı. `chosen.title` bot xəbərini, `research.headline`
    Tramp zəngini göstərirdi; heç kim görmədi, istifadəçi postu bəyəndi.
    İndi `pipeline.cluster_index_for()` klasteri namizədin LİNKİ ilə
    tapır, indeks yalnız ehtiyatdır; `propose_more` də linklə çıxarır.
    **Dərs: iki proses arasında ötürülən identifikator DƏYƏRƏ (link)
    bağlı olmalıdır, sıraya yox.**

34. **«Şəkil uyğunsuz» — bu dəfə dörd səbəb, hamısı ölçüldü.**
    (1) `_finish_and_send` `director["_post"]` qoymurdu → ilk şəkil üçün
    model seçici atlanırdı (dərs 13, ÜÇÜNCÜ yer) və xam sıra memo-ya
    düşüb 7 «başqa şəkil» basışına qalırdı — memo açarına `post` daxil
    edildi, seçici işləməyəndə etiket «· seçici işləmədi» deyir.
    (2) `_relevance` brend adına çəki vermirdi: Unsplash-də 5 Nvidia
    şəkli var idi, amma Intel/Google binaları eyni bal alır, «man
    holding smartphone» sorğusuna uyan «man, father, holding, baby»
    hamısını keçirdi — indi böyük hərfli söz (Nvidia, Jensen) məcburidir:
    təsvirdə varsa +0.5, yoxdursa bal yarıya enir.
    (3) Openverse `aspect_ratio=tall` filtri ilə çağırılırdı — ictimai
    şəxslərin yeganə mənbəyi (Wikimedia/Flickr) yatıq foto verir, filtr
    hamısını atırdı; 6 s hədd də onu həmişə kənarda qoyurdu (ölçülüb:
    6-10 s). Filtr silindi, hədd 18 s. Direktor promptu: tanınmış ŞƏXS
    → adı + kontekst birinci sorğu («Jensen Huang keynote» → CES 2025
    keynote, 4032×3024, CC0).
    (4) `_next_image`/`_use_image` krediti yeniləmirdi → ilk şərhə
    YANLIŞ fotoqraf düşəcəkdi (BY-SA-da lisenziya pozuntusu). Düzəldildi.
    ⚠️ **Həll olunmayan:** seçici şəkli GÖRMÜR, təsviri oxuyur. «Jensen
    Huang — Nvidia Keynote» fotosunda Huang kadrın küncündə kiçik
    fiqurdur, kadr laptop slaydıdır — seçici onu 1-ci qoydu. Ayrıca:
    stok foto əvvəl 4:5-ə kəsilir, sonra kart 1200×860 pəncərə göstərir
    — yatıq fotoların yanları itir. Növbəti addım namizədləri MODELƏ
    GÖSTƏRMƏK (thumbnail + Read) və `news` üçün yatıq kəsim.

35. **Özünü yeniləmə (dərs 24) yarış vəziyyətində susurdu.** `git pull`
    faylları bir neçə saniyəyə yazır; proses İLK dəyişiklikdə qalxır,
    sonrakı fayl import-dan SONRA, barmaq izi çəkilməzdən ƏVVƏL yazılır
    → iz yeni mtime-i daşıyır, yaddaşdakı kod köhnədir, yenilənmə heç
    vaxt gəlmir. *Ölçüldü 15.09.2026 11:42:28:* proses :28.000-də
    başladı, `approval.py` :28.858-də yazıldı, 70 s sonra da köhnə kod.
    İndi `cli.BOOT_TIME` faylın ilk sətrində (bütün import-lardan
    əvvəl) çəkilir və `code_fingerprint() > BOOT_TIME` yoxlanır.
    **Dərs: «dəyişdi?» sualını sonradan çəkilmiş izlə yox, prosesin
    başlanğıc anı ilə cavabla.**

36. **Şəkil seçimi yenidən quruldu — «telefon şəkli» səhvi (15.09.2026).**
    Tramp–Huang zəngi postuna sistem telefon fotosu seçirdi: açar söz
    uyğun idi, hekayə yox. Kök səbəb üç qat idi: (a) hekayə anlaşılmırdı —
    direktor birbaşa sorğu yazırdı; (b) seçici modelə YALNIZ təsvir mətni
    göndərirdi (`pick_best` → `listing`), şəkli görmürdü; (c) rədd yolu
    yox idi — nəsə həmişə seçilirdi.
    İndi (`src/images/story.py`, `inspect.py`, `prompts/photo_inspector.md`):
    - Direktor `story` bloku verir (kim/nə/harada/nə vaxt, `irrelevant`);
      tədbir yalnız tədqiqat mətnində keçəndə təsdiqlənir
      (`_confirmed_in` — ümumi sözlər atılır: «All-In konfransı» ≈
      «All-In Summit»); sorğular koddan qurulur, kənar obyekt düşmür.
    - Mənbə sırası: təsdiqlənmiş aktiv keşi (`state/assets.json`) →
      şəxs adı ilə Openverse (`_person_lookup`, `state/person_photos.json`
      keşi; Openverse bütün sözləri tələb edir — «Jensen Huang portrait»
      0, «Jensen Huang» 5 nəticə) → stok sorğuları → məqalə `og:image`.
    - Müfəttiş `Read` aləti ilə ≤640 px önizləmələrə BAXIR; 0-3 ballar
      ayrıca: subyekt · tədbir · aydınlıq · aldadıcı · səhv subyekt ·
      fokus qutusu. Kimlik üzdən yox, mənbə təsvirindən (`identity_basis`).
    - Qərar kodda (`inspect.decide`): lisenziya (platforma / CC / PD;
      NC-ND rədd; məqalə şəkli baxılmadan rədd, amma hesabatda), subyekt
      ≥2, aydınlıq ≥2, aldadıcı yox, kimlik təsvirdən. Növ: `event`
      yalnız tarix tədbirlə ±3 gün; köhnə tarix → `archive` (kreditə
      «arxiv foto, 2023» əlavə olunur); tarixsiz → `contextual`.
    - Zəncir = qəbul edilənlər (≤2) → kollaj (iki şəxsin portreti,
      ad etiketləri, «Redaksiya kollajı» qeydi) → SON. Ümumi stok fotosu
      heç vaxt düşmür; AI fon yalnız şəxssiz hekayədə. Heç nə keçmirsə
      Telegram «Uyğun şəkil tapılmadı» deyir və düymələr verir:
      🔎 Tədbir fotosu axtar · 🖼 Redaksiya kartı · 🔤 Mətn kartı (yalnız
      istəyinizlə — avtomatik zəncirdə yoxdur, dərs 21 qüvvədədir).
    - Kəsim fokus qutusuna görədir (`render.crop_box`) — Huang küncdə
      qalmır.
    - Qərarlar `out/images/<run>/selection.json`-dadır; dinləyici ayrı
      prosesdir, təkrar pul xərcləmir. `make image --run <id>` tam
      hesabat çap edir (dry run, növbəyə toxunmur).
    *Ölçüldü (dry run, eyni post):* köhnə → telefon/«father holding
    baby»; yeni → Huang arxiv fotosu (Commons, BY 2.0, 2023) + Tramp rəsmi
    portreti + kollaj; TechCrunch-un ƏSL tədbir fotosu tapıldı və
    lisenziya səbəbilə rədd edildi (hesabatda linkə baxılır). 1 tur =
    ~20k token, 2 tur ~40k; direktor 12k.
    ⚠️ Məhdudiyyətlər: model balları qaçışdan qaçışa dəyişir (haiku; bir
    dry run-da Tramp portreti «səhv subyekt» aldı) — `MODEL_INSPECT=sonnet`
    sabitlik üçün variantdır; Openverse yavaşdır (7-35 s) və vaxtaşırı
    cavabsız qalır (Tramp üçün keş boşdur); məqalə fotolarının
    lisenziyası yoxlanılmır → heç vaxt yayımlanmır; kollaj etiketləri
    təsdiqlənmiş dizayna kiçik əlavədir (yalnız kollaj rejimində).
    **Dərs: modelə «uyğundurmu?» sualını mətnlə yox, ŞƏKİLLƏ ver — və
    qərarı model yox, açıq qaydalar versin; «heç biri» düzgün cavabdır.**

37. **Mac 08:35-də sönülü olanda gün boyu namizəd gəlmir.** 16.09.2026:
    Mac 09:04-də açıldı (`uptime`), launchd `prepare`
    (`StartCalendarInterval`) buraxılmış işi yalnız YUXUDAN oyananda
    tamamlayır, söndürülüb-yandırılanda yox; CI də işləmədi (dərs 18);
    `tick` isə namizəd hazırlamır (dərs 17). İki kanal da susdu, telafi
    edən yox idi. İndi `tick` 09:00–14:00 arası (`PREPARE_CATCHUP_FROM/
    UNTIL`) `prepared_today()` «no» deyəndə `do_prepare` işlədir —
    prepare ilə eyni funksiya, CI-nın işini də sayır (təkrar yoxdur).
    **Dərs: cədvəlli iş üçün «buraxılsa kim tutacaq?» sualına cavab
    olmalıdır — ehtiyatın da ehtiyatı lazımdır.**
    Əlavə (16.09): `tick` plist-də `RunAtLoad` — Mac açılan kimi bir tick
    (telafi 15 dəqiqə gözləmir); pəncərə 09-18; Telegram `/propose` —
    istifadəçi özü başladır (eyni gün ikinci dəst təsdiq istəyir, açıq
    təklif bağlanır). `pmset repeat wakepoweron 07:45` qurulub, amma
    qapağı bağlı MacBook oyanıb dərhal yatır — ona güvənmə.
    ⚠️ **Mac-sız işləmək üçün** yeganə etibarlı yol xarici cron →
    `workflow_dispatch`: hər iki workflow-da `workflow_dispatch` var;
    cron-job.org (və ya istənilən HTTP cron) 08:30-da
    `POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/prepare.yml/dispatches`
    (`{"ref":"main"}`, `Authorization: Bearer <PAT actions:write>`),
    hər 15 dəqiqə `tick.yml` üçün eyni. Dispatch qaçışları schedule kimi
    atlanmır (dərs 18 yalnız `schedule` event-inə aiddir). Düymələr onda
    CI tick ilə 15 dəqiqəyə cavablanır. PAT-ı istifadəçi özü yaradır.

38. **Dinləyicini restart edəndə içindəki YAZI da ölür.** 16.09.2026
    10:35: istifadəçi namizəd seçdi, yazı dinləyici prosesində başladı;
    10:44-də mən `install_launchd.sh` işlətdim (`pkill -f "src.cli
    watch"`) — yazı kəsildi, heç iz qalmadı (qaçış faylı yalnız sonda
    yazılır), təklif `picked` qaldı (dərs 32-nin reopen-i xətanı tutur,
    prosesin ölümünü yox). «3 dəqiqə» dedi, 15 dəqiqə heç nə gəlmədi.
    İndi: seçim basılanda `state/inflight.json` yazılır, bitəndə
    silinir; dinləyici qalxanda `approval.resume_inflight()` faylı
    görüb təklifi yenidən açır və eyni seçimi DAVAM ETDİRİR (≤60 dəq;
    köhnədirsə yalnız yenidən açıb istifadəçiyə deyir). Quraşdırıcı
    `inflight.json` varkən dinləyicini öldürmür — 10 dəq gözləyir
    (`FORCE=1` keçir). Özünü yeniləmə (dərs 24/35) təhlükəsizdir:
    yoxlama dövrün başında, yəni işlər arasındadır.
    **Dərs: uzun iş görən prosesi restart etməzdən əvvəl «içində nə
    var?» soruş — və işin özü diskdə iz qoysun ki, davam edilə bilsin.**

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

**Şəkil düymələri (news):** 🔄 Başqa şəkil (qəbul edilənlər → kollaj →
son) · 📷 Real foto (müfəttiş seçimləri: növ · izah · mənbə) · 1️⃣2️⃣ Bu
şəkil · 🔎 Tədbir fotosu axtar · 🖼 Redaksiya kartı · 🔤 Mətn kartı.

**Namizəd düymələri:** 1️⃣2️⃣3️⃣ seç · 🎲 Sən seç (pəncərənin 1-cisi) ·
🔄 Başqa xəbər (əvvəl ehtiyat 4-6, pulsuz; bitəndə Scout qalan
klasterlərə baxır, ~20k token) · ❌ Bu gün keç.

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

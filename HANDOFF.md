# Təhvil sənədi — yeni sessiya üçün

> Bu fayl söhbət kontekstini əvəz etmək üçündür. Yeni sessiyada
> **əvvəlcə bunu oxu**, sonra `README.md`-yə bax.
> Son yenilənmə: **24.09.2026**

---

## Yeni sessiyaya başlarkən — 60 saniyəlik giriş

1. Bu faylı oxu (xüsusən **Bahalı dərslər**, 42 ədəd — hamısı real
   səhvdən çıxıb, təkrarlama).
2. Vəziyyəti ÖLÇ, fərz etmə:
   ```bash
   date; make queue; make test
   tail -20 out/launchd-watch.log; tail -20 out/local-cron.log
   python3 -c "import json;d=json.load(open('state/proposals.json'));p=d['proposals'][-1];print(p['id'],p['status'],p.get('picked_index'))"
   ```
3. Dinləyiciyə (`src.cli watch`) əl ilə toxunma: kod dəyişəndə özü
   yenidən qalxır; `state/inflight.json` varsa post YAZILIR — gözlə
   (dərs 38, 40).
4. Hər düzəlişə regresiya testi yaz → `make test` → commit → push.
   Cavablar **Azərbaycan dilində**.

---

## Layihə nədir

AI xəbərlərindən **Azərbaycan dilində** LinkedIn postu hazırlayan agent
sistemi. Sahibi: Samir Nabiyev.

**LLM xərci $0** — Claude Pro abunəliyi ilə işləyir (`claude -p` başsız
rejim, `CLAUDE_CODE_OAUTH_TOKEN`). Ölçülmüş: ~90k token / post.

Axın:
```
26 RSS mənbəsi (18 qlobal + 8 yerli) → çarpaz təsdiq → Scout 3 namizəd verir
  → istifadəçi Telegram-da seçir → Researcher → Writer → Reviewer → Reviser
  → şəkil → Telegram təsdiqi → cədvəl → LinkedIn → arxiv
```

---

## Hazırkı vəziyyət (24.09.2026)

| | |
|---|---|
| Kod | ~12 800 sətir · **228 test** (hamısı keçir, 0.3s, oflayn) |
| Repo | `github.com/nabiyevsamir-002/avto-post-linkedin` (private) |
| Lokal cron | launchd: `prepare` (08:35) · `tick` (15 dəq + girişdə dərhal; 09-18 telafi) · `watch` (KeepAlive) |
| Dinləyici | kod/prompt dəyişəndə **özü yenidən yüklənir** (~27s) |
| LinkedIn | Samir Nabiyev · token **44 gün** qalır (`make li-renew`) |
| Şəkil | `news` kartı · **foto müfəttişi** (model şəkli görür, qaydalar kodda) · kollaj · AI fonu yalnız şəxssiz hekayədə |
| VPN | qurulub — Telegram sabit işləyir |

**Yayımlanmış: 8 post:**
- 09.09 — Claude token oğurluğu
- 10.09 — GPT-6 Astra *(ilk `news` kartı)*
- 11.09 — Spirit Airlines / Google data alışı *(ilk AI fonlu kart)*
- 16.09 — BloombergNEF: ABŞ data mərkəzləri qaz tələbi *(müfəttiş seçdiyi
  real foto — Pexels enerji stansiyası; bax dərs 40)*
- 17.09 — Anthropic Claude Chat + Cowork
- 22.09 — Google/Gemini sızması *(ilk yayım kart #2 ilə getdi, istifadəçi
  sildi, kart #1 ilə yenidən yayımlandı; bax dərs 42)*
- 23.09 — Microsoft kütləvi hack platformasını dayandırdı *(AI fonu,
  geniş plan — yeni yatıq fon, bax dərs 41)*

⚠️ **Arxiv commit edilməyib:** `archive/2026/09/`-da 4 yeni fayl +
`INDEX.md` dəyişikliyi `git status`-da gözləyir (16, 17, 22, 23.09
postları). Növbəti `tick` onları özü commit edir; tələsirsinizsə
`scripts/commit_state.sh "arxiv"`.

⚠️ **LinkedIn ilk şərh 403** (22.09-dan): `partnerApiSocialActions.CREATE`
icazəsi yoxdur — API versiyası 202609-a keçəndən sonra. Post yayımlanır,
şərh yox; Telegram «əl ilə yazın» deyir. Kodla düzəlmir — LinkedIn
tətbiqinin məhsul icazəsi / token yenilənməsi (`make li-renew`) lazımdır.

**Növbənin vəziyyəti (24.09 səhər):**
- Bugünkü təklif `2026-09-24T05-40-58` **AÇIQDIR** — 09:40-da göndərilib,
  cavab gəlməsə **12:40-da** sistem 1-cini özü seçəcək. Namizədlər:
  ① Samsung soyuducu firmware · ② $11M yarışda AI yanğını · ③ Hindistan
  ağıllı gözlüklər (+3 ehtiyat «🔄 Başqa xəbər»-də).
- Bank boşdur. Bu gün hələ post çıxmayıb (gündəlik hədd açıqdır).
- ⚠️ `2026-09-15T07-14-48` **pending qalıb** (AI botlar/spam) — 15.09-da
  şəkil zəncirində qaldı, təsdiqlənmədi. Lazım deyilsə Telegram-da
  `/skip` ilə bağlayın; növbə hesabatlarında görünməyə davam edir.

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

39. **«Rədd edilmiş dizayn» promptda üstünlük idi, kodda qadağa yox.**
    16.09.2026: rəqəmli post («proqnoz 2,2 dəfə artdı») üçün direktor
    `chart` seçdi — dərs 19-un «yalnız rəqəmləri çıxarsan post dağılır»
    istisnası — və köhnə tipoqrafik kart yenə çıxdı. İstifadəçi: «bir
    dəfəlik düzəlt». İndi `force_news()` tək nöqtədir; `plan()` da
    qoruyur. **Dərs: istifadəçinin «istəmirəm» dediyi şey prompt
    üstünlüyü ilə yox, kodda bir çökə nöqtəsi ilə qadağan olunmalıdır —
    model üstünlüyü istisna ilə keçər, kod keçməz.**

40. **CANLI elementə paralel əl müdaxiləsi — dərs 38-in təkrarı, bu dəfə
    yayım anında.** 16.09.2026 12:02–12:05: istifadəçi Telegram-da «Başqa
    şəkil» basdı (dinləyici yeni kodla real foto kartı qurdu), sonra «İndi
    yayımla»; eyni anda mən həmin elementi skriptlə yenidən qururdum
    (direktor + müfəttiş + 3 AI fon, $0.09). `state/images/<id>.png` tək
    fayldır — hər iki proses onu yazdı; yayım 12:05:06-da diskdəki faylı
    (12:05:05, enerji stansiyası kartı) yüklədi, növbədəki metadata isə
    mənim aralıq AI etiketimlə qaldı (sonradan düzəldildi). Şəkil düzgün
    çıxdı, amma təsadüfən. Ayrıca tapıntı: `store.read_json` `.bak`-a
    düşür — `selection.json`-u silmək keşi təmizləmir, `.bak` da silinməli.
    **Dərs: istifadəçinin işlədiyi elementə skriptlə toxunma — dinləyici
    onsuz da eyni kodu işlədir; lazımdırsa Telegram düyməsi ilə et.**

41. **«$0.03-a boş şəkil» — şəkil boş deyildi, kartın pəncərəsindən
    kənarda idi.** 17.09.2026: AI fonu portret (1024×1536) yaradılırdı,
    «geniş plan» variantı subyekti kadrın altına qoydu («open sky
    above»), sorğuda köhnə dizayndan qalan «upper third must stay calm»
    qaydası da vardı; xəbər kartı isə şəklin yalnız yuxarı ~57%-ni
    göstərir (1200×860 pəncərə, `object-position: center 18%`) —
    görünən hissə boş səma oldu. İndi `aigen.generate` YATIQ (1536×1024)
    yaradır və `fit_photo(size=WINDOW)` ilə birbaşa 1200×860-a kəsir —
    kart bütün kompozisiyanı göstərir; sorğu «horizontal 3:2, subject in
    the middle, no large empty sky», «upper third» qaydası silindi.
    **Dərs: şəkil sorğusu göstərilən PƏNCƏRƏYƏ yazılmalıdır — dizayn
    dəyişəndə (tam ekran portret → yuxarı yatıq pəncərə) sorğudakı
    kompozisiya qaydaları da dəyişməlidir; «kalıb qaydası» yeni kalıbı
    boşaldır.**

42. **✅ düyməsi mesajdakı şəklə yox, elementin O ANDAKI şəklinə aid idi.**
    22.09.2026: 09:13 kart #1 gəldi; 09:15:35 «Başqa şəkil» kart #2-ni
    cari etdi; 09:15:55 istifadəçi kart #1-in altındakı ✅-i basdı →
    təsdiq cari şəklə (kart #2) düşdü, 12:00-da LinkedIn-ə kart #2 getdi.
    İstifadəçi «səhv post» sandı (mətn eyni idi, şəkil fərqli), postu
    sildi; kart #1 ilə yenidən yayımlandı (`publish_item(force=True)`,
    gündəlik hədd keçildi). İndi təsdiq düymələri pilləni daşıyır
    (`ok@1`); pillə cari ilə uyğun gəlmirsə sistem DAYANIR və soruşur:
    «🖼 Kart #N-ə qayıt» (`useimg N` — hər göstərilən kart
    `image_choices.json`-da yol/etiket/kreditlə saxlanır) və ya «➡️ cari
    ilə davam» (`showkb`). Tələb 6 («təsdiq baxdığım mətn və şəklə aid
    olmalıdır») əslində indi ödənir.
    **Dərs: təsdiq düyməsi «nəyi» təsdiqlədiyini özündə daşımalıdır —
    vəziyyət dəyişə bilən hər şeydə düymə identifikator saxlasın.**

43. **Mənbələr 9-dan 26-ya çıxdı; yarısı Azərbaycan və region (24.09.2026).**
    İstifadəçinin tələbi: «gələn xəbərlər xoşuma gəlmir, heç biri yaxşı
    baxış almır — mənbələri artıraq, yarısı qlobal, yarısı Azərbaycan
    olsun». Üç ayrı problem çıxdı, hər biri fərqli qatda:

    **(a) Qlobal dəst çox dar idi.** 9 mənbənin 3-ü vendor bloqu
    (OpenAI/Google/DeepMind), biri TechCrunch — yəni siyahının yarısı
    məhsul elanı verirdi. Ona görə namizədlər «növbəti versiya çıxdı»
    tipində olurdu. Əlavə olunan 9 mənbə məhz başqa xəbər növü gətirir:
    münaqişə və araşdırma (404 Media, BBC), pul və sızma (The
    Information), istifadəçiyə toxunan dəyişiklik (Verge, WIRED,
    Decoder), inkişaf edən bazarlar (Rest of World), «sahə bu gün nəyi
    danışır» (Techmeme), developer iş axını (GitHub Blog).

    **(b) Yerli xəbər ƏSLA seçilə bilmirdi — bal sistemi buna imkan
    vermirdi.** Çarpaz təsdiq balı «neçə müstəqil nəşr yazıb» sualına
    söykənir. Azərbaycan nəşrləri bir-birini təkrar etmir, ona görə
    yerli klasterin balı ~1.1-1.2, qlobalınkı 2.5-5.0 olur. Yerli xəbər
    24-lük pəncərəyə heç vaxt düşmürdü. Düzəliş balda YOX, siyahıda:
    `pipeline._split_window` pəncərəni ikiyə bölür (`SCOUT_LOCAL_SHARE=0.5`),
    hər tərəf öz içində yarışır, bir tərəf kvotasını doldurmasa yerlər
    o birinə keçir. `SCOUT_WINDOW` 24→32 qaldırıldı ki, bölgü qlobal
    tərəfi 12-yə sıxmasın.

    **(c) İngiliscə açar söz filtri azərbaycancada yalan işləyir.**
    Ümumi xəbər saytlarında texnologiya payı ~5%-dir, ona görə filtr
    şərtdir. Ölçüldü — köhnə siyahı ilə: «proqram» televiziya verilişini,
    «model» mankeni, «meta» metallurgiyanı, «ikt» diktoru, «Aİ» (Avropa
    İttifaqı) isə süni intellekti tuturdu. İndi: çoxmənalı sözlər
    siyahıdan çıxarılıb, Azərbaycan kökləri yalnız SOLDAN bağlanır
    (dil şəkilçi yığır: «startap» → «startaplara»), «AI» isə xam mətndə
    böyük hərflə axtarılır (`_AI_ACRONYM`) — «Aİ» ilə qarışmasın deyə.
    Ayrıca `_fold()`: Python-da «İ».lower() birləşən nöqtə saxlayır, ona
    görə «İKT» heç vaxt «ikt» ilə uyğun gəlmirdi.

    Kiçik, amma görünən şeylər: InfoCity hər xəbəri həm azərbaycanca,
    həm rusca verir — kiril nüsxələr atılır, yoxsa siyahı ikiqat olur.
    `cluster._WORD` Azərbaycan hərflərini tanıyır və STOPWORDS-a
    azərbaycanca köməkçi sözlər əlavə edildi (onlarsız yerli başlıqlar
    məzmuna görə yox, «üçün olub edib» sözlərinə görə birləşirdi).

    *Ölçüldü, real qaçış:* 134 xəbər → 111 klaster (əvvəl ~40);
    pəncərədə 16 qlobal + 12 yerli; Scout 6 namizəddən birini yerli
    seçdi («Texnologiyalar parkında 20 illik vergi güzəşti»). Gözlənilməz
    bonus: InfoCity qlobal klasterlərə qoşulur («GPT-6 Sol» klasterində
    5 mənbədən biri odur) — yəni `covered_by_local_media` bayrağı işləyir.
    26 mənbənin hamısı çəkildi, 0 xəta.

    **Dərs: yeni növ mənbə əlavə edəndə onu ölçən metrikanın həmin növ
    üçün işlədiyini yoxla. Bizim metrika «neçə nəşr təkrarladı» idi —
    yerli mətbuat üçün bu ölçü mənasızdır, ona görə mənbəni əlavə etmək
    tək başına heç nə dəyişmirdi.**

44. **Dərs 42 yarımçıq idi: qoruyucu PİLLƏYƏ baxırdı, kartlar isə
    pilləni BÖLÜŞÜR (24.09.2026).** İstifadəçinin şikayəti: «başqa şəkil
    seçib yayımla deyirəm, sonuncu redaktə olunan şəkil gedir».

    22.09-dakı düzəliş düyməyə `ok@<pillə>` yazırdı. Amma zəncirin
    sonundakı AI pilləsi bitmir — `_next_image` onu təkrar-təkrar icra
    edir (hər dəfə başqa kadr). Yəni iki FƏRQLİ kartın pilləsi eynidir,
    qoruyucu fərqi görmür və keçirir.

    Daha pisi, fayl da itirdi: `images.produce` faylı pilləyə görə
    adlandırır (`out/images/<id>/03-news.png`), ona görə ikinci icra
    birincinin faylını ÜSTÜNDƏN yazırdı. `image_choices.json` da eyni
    açarı (`"3"`) əzirdi. «Kart #1-ə qayıt» düyməsi mövcud olan yeganə
    fayla baxırdı — o isə artıq sonuncu şəkildi.

    *Sübut istifadəçinin öz məlumatındadır* — `2026-09-23T05-13-28`:
    tarixçədə iki `image_advanced` («yaxın plan», «geniş plan»), diskdə
    isə `01-bg-ai00.png` + `01-bg-ai01.png` (iki fon saxlanılıb), amma
    hazır kart yalnız BİR dənə: `01-news.png`. Birinci kart yox idi.

    Düzəliş — kimlik pillədən ayrıldı:
    - `queue.Item.image_card` — artan, təkrarsız kart nömrəsi;
      düymələr indi `ok@<kart>` daşıyır, `useimg<kart>` da kart alır.
    - `_remember_card()` hər göstərilən kartı DƏRHAL
      `state/images/<id>-cN.png` altına köçürür. `out/` işçi qovluqdur,
      üstündən yazıla bilər; anbar isə toxunulmazdır.
    - Kart siyahısı qırxılmır: nömrə mövqedir, başdan bir element atsan
      bütün nömrələr sürüşür (bu, düzəlişin özündə tutulan səhv idi).
    - `_card()` köhnə, pillə açarlı qeydləri də oxuyur — yeniləmədən
      əvvəl göndərilmiş düymələr işləməyə davam edir.
    - `cli.cmd_send` də ilk kartı qeyd edir, yoxsa `make send` yolunda
      birinci kart nömrəsini sonrakı kart oğurlayırdı.
    - `queue.prune_images()` kart nüsxələrini post bitən kimi silir.
      Bunsuz `state/images/` (repoya commit olunur) hər postdan 4-6 MB
      yığacaqdı — 12 MB-lıq qovluq aylıq ~110 MB-a çatardı.

    **Dərs: «düymə nəyi təsdiqlədiyini daşısın» kifayət deyil — daşıdığı
    identifikator HƏQİQƏTƏN təkrarsız olmalıdır. Pillə nömrəsi kimlik
    kimi görünürdü, amma deyildi.**

45. **«Başqa şəkil» indi SƏBƏB soruşur (24.09.2026).** Əvvəl düymə
    kor-koranə zəncirin növbəti pilləsini verirdi — istifadəçi nəyi
    bəyənmədiyini deyə bilmirdi. İndi düymə soruşur: «Bu şəkildə nə
    dəyişsin, nə qalsın?» Yazmaq istəməyən üçün «🎲 Sadəcə dəyiş»
    düyməsi var — köhnə davranış bir basışla əlçatandır.

    Rəy `item.image_note`-da qalır, yəni SONRAKI bütün AI variantlarına
    da tətbiq olunur (`_director_for` → `_image_brief`). Haiku rəyi qısa
    ingiliscə göstərişə çevirir (`gpt-image-1` ingiliscəyə xeyli yaxşı
    reaksiya verir); model əlçatmazdırsa rəy olduğu kimi işlənir.
    Göstəriş sorğunun ORTASINA düşür — sona qoysaq «mətn olmasın»
    qaydası ilə növbəyə girib zəifləyir.

    ⚠️ Vacib məhdudiyyət: rəy YALNIZ AI fonunda işləyir. Arxiv fotosunu
    sözlə dəyişmək mümkün deyil, o hazır şəkildir. Hekayədə real şəxs
    varsa AI pilləsi onsuz da zəncirə düşmür (tələb 5) — belə halda
    sistem bunu AÇIQ deyir və sadəcə növbəti variantı göstərir.

46. **Telegram-da doğrulama bloku (24.09.2026).** İstifadəçinin tələbi:
    «hər dəfə məlumatın təzə olub-olmadığını və uydurma olmadığını
    sübut et». `approval.verification()` təsdiq mesajının SONUNA —
    düymələrin düz üstünə — bunları yazır:

    - xəbərin neçə saatlıq olduğu və dərc tarixi
    - neçə MÜSTƏQİL nəşrin yazdığı
    - ilkin mənbənin linki (açıb yoxlamaq üçün)
    - faktların və rəqəmlərin neçəsinin mənbə linki ilə gəldiyi

    Zəiflik varsa ⚠️ ilə açıq yazılır: tək mənbə, 48 saatdan köhnə
    xəbər, aqreqator (Techmeme/Google News) ilkin mənbə kimi, linksiz
    fakt və ya rəqəm, aşağı etibarlı iddia. Yerli xəbərdə «tək mənbə»
    xəbərdarlıq SAYILMIR — yerli nəşrlər bir-birini təkrar etmir.

    Model çağırılmır: bütün rəqəmlər elementin öz məlumatından
    hesablanır, ona görə pulsuzdur və blok özü uydura bilmir.

    **Dərs: «uydurma deyil» HÖKMÜ vermirik — sübut göstəririk. Sistem
    faktın doğruluğunu bilmir; bildiyi odur ki, iddia neçə mənbəyə
    söykənir və link açıqdır. Fərqi gizlətmək etibarı uydurmaq olardı.**

47. **Silinmiş postu bərpa yolu yox idi — çıxılmaz vəziyyət (24.09.2026).**
    Post LinkedIn-ə çıxdı, sahibi bəyənmədi və LinkedIn-dən ƏL İLƏ
    sildi. Sonra təkrar yayım istədi — sistem «artıq yayımlanıb» dedi.

    Niyə mövcud yollar işləmirdi:
    - `publish_item()` qoruyucusu `force` ilə DƏ keçilmir:
      `status == PUBLISHED or linkedin_urn` şərti şərtsizdir.
    - `undo()` postu API ilə silir — yəni post hələ LinkedIn-də
      olmalıdır. Sahibi artıq silmişdisə çağırış boşa çıxır. Üstəlik
      geri-al pəncərəsi (60 dəqiqə) bağlanmış ola bilər.
    - `undo()` statusu `skipped` edir — o da terminaldır, yəni bərpa
      etmir.

    Yeganə yol `queue.json`-u əl ilə redaktə etmək idi (dərs 42-də məhz
    bu edilmişdi).

    İndi `publisher.restore()` var: LinkedIn-ə TOXUNMUR, sadəcə
    `linkedin_urn`, `linkedin_url`, `published_at`, xatırlatmalar və
    göstəriciləri təmizləyir, statusu `pending`-ə qaytarır və arxiv
    qeydini silir (arxiv «yayımlanmış postlar» siyahısıdır — silinmiş
    post orada qalsa sonrakı təhlil mövcud olmayan postu sayar).
    ⚠️ Arxiv `published_at`-dan ƏVVƏL silinməlidir: fayl yolu ondan qurulur.

    Gündəlik hədd avtomatik azad olur — `published_today()` yalnız
    `published_at`-ı olan `published` elementləri sayır.

    Giriş nöqtələri: yayım bildirişindəki «♻️ LinkedIn-dən özüm sildim»
    düyməsi, `/restore` əmri, və sistem postu özü siləndən sonra çıxan
    «♻️ Bərpa et və düzəlt» düyməsi. Hamısı ƏVVƏLCƏ soruşur: «LinkedIn-də
    silmisinizmi?» — post hələ oradadırsa bərpa + yayım profildə İKİ
    eyni post yaradır.

    **Dərs: hər terminal vəziyyətin geri yolu olmalıdır. «Yayımlandı»
    sistemin daxilində son nöqtə idi, amma LinkedIn-də deyil — kənar
    dünya dəyişəndə sistem bunu qəbul edə bilməlidir.**

48. **Cron başqasının işini öz commit-inə yığırdı (24.09.2026).**
    `commit_state.sh` arqumentsiz `git commit` çağırırdı — o isə
    İNDEKSDƏKİ HƏR ŞEYİ götürür. Redaktor eyni anda `git add` etmişdisə,
    kod da «chore(state): lokal tick» adı altında commit və push olunurdu.
    Real hadisə: `ad82135` commit-inə 208 sətirlik `src/approval.py`,
    testlər və HANDOFF qeydləri «lokal tick» adı ilə düşdü.

    Düzəliş: həm yoxlama, həm commit pathspec ilə (`git commit ... --
    state/ archive/`). İndeksdə nə olursa olsun, bu commit-ə yalnız
    həmin iki qovluq düşür.

    ⚠️ `archive/` SİYAHIYA AÇIQ YAZILMALIDIR. Əvvəl o, məhz catch-all
    davranış sayəsində TƏSADÜFƏN commit olunurdu. Pathspec-i yalnız
    `state/` ilə qoysaq, arxiv bir daha push olunmazdı — halbuki o,
    yayımlanmış postların yeganə nüsxəsidir.

    **Dərs: təsadüfən işləyən şeyi düzəldəndə, onun təsadüfən nəyi
    daşıdığını da yoxla. Dar düzəliş burada səssiz məlumat itkisi
    olacaqdı.**

---

## Şəkil axını — hazırkı memarlıq (24.09.2026)

15-22.09 arasında şəkil seçimi tamamilə yenidən quruldu. Sıra belədir
(hər addımın kodu mötərizədə):

1. **Hekayəni anla** (`src/images/story.py`) — direktor `story` bloku
   verir: növ · şəxslər · təşkilatlar · məhsullar · hərəkət · tədbir ·
   `must_show` · `irrelevant`. **Tədbir yalnız tədqiqat mətnində
   keçəndə təsdiqlənir** (`_confirmed_in`); təsdiqlənməmiş tədbir adı
   sorğuya düşmür. Sorğular KODDAN qurulur (şəxs → təşkilat → səhnə),
   kənar obyekt («telephone», «smartphone») heç vaxt.
2. **Namizədlər** (`images._pool`) — təsdiqlənmiş aktiv keşi
   (`state/assets.json`) → şəxs adı ilə Openverse (`_person_lookup`,
   keş `state/person_photos.json`) → stok sorğuları (Pexels/Unsplash/
   Pixabay/Openverse) → məqalə `og:image` (namizəd kimi; lisenziyasız →
   baxılmadan rədd, amma hesabatda görünür).
3. **Müfəttiş ŞƏKLƏ BAXIR** (`src/images/inspect.py`,
   `prompts/photo_inspector.md`) — ≤640 px önizləmə, `claude -p` +
   `Read` aləti. Ballar ayrıca: subyekt · tədbir · aydınlıq · aldadıcı ·
   səhv subyekt · görünən yazı · fokus qutusu. Kimlik üzdən yox, mənbə
   təsvirindən (`identity_basis`).
4. **Qərarı KOD verir** (`inspect.decide`) — lisenziya (platforma/CC/PD,
   NC-ND rədd), subyekt ≥2, aydınlıq ≥2, aldadıcı yox. Növ: `event`
   yalnız tarix tədbirlə ±3 gün; köhnə → `archive`; tarixsiz →
   `contextual`. Nəticə `out/images/<run>/selection.json`-dadır —
   dinləyici ayrı prosesdir, təkrar pul xərcləmir.
5. **Zəncir** = qəbul edilənlər (≤2) → kollaj (iki şəxsin portreti, ad
   etiketləri) → son. Ümumi stok fotosu HEÇ VAXT; AI fonu yalnız şəxssiz
   hekayədə. Heç nə keçmirsə «Uyğun şəkil tapılmadı» deyilir.

**Telegram düymələri:** ✅ Yayımla · 🏦 Banka at · ⚡ İndi yayımla ·
🔄 Başqa şəkil · 🔄 Yenidən yaz · ✏️ Mətni dəyiş · ❌ Keç.
Zəncirin sonunda seçimlər mesajı: 1️⃣2️⃣ Bu şəkil · 🔎 Tədbir fotosu axtar ·
🖼 Redaksiya kartı. («📷 Real foto» və «🔤 Mətn kartı» 16.09-da silindi.)
Təsdiq düymələri **baxılan şəklin pilləsini daşıyır** (`ok@1`) — şəkil
arada dəyişibsə sistem dayanır və «Kart #N-ə qayıt» təklif edir (dərs 42).

**Təsdiqlənmiş dizayn** (dəyişdirmə): SN loqosu (inline SVG) + ad +
üfüqi xətt · kicker · foto fonu · sağ yuxarıda dairəvi ikinci şəkil
(290px, `top:140 right:44`) · kapsul (bir sətir, `_fit_capsule`) ·
tünd başlıq zolağı + mavi vurğu sözlər · sol altda profil linki.

⚠️ **Köhnə tipoqrafik üslub (Claude `chart`/`card`) istifadəçi
tərəfindən RƏDD EDİLİB — 16.09.2026-dan KODDA qadağadır.**
`images.force_news()` direktorun seçimini həmişə `news`-ə çevirir
(`_requested_type` telemetriya üçün qalır); `plan()` `news`-dən başqa
növü yalnız `_allow_claude` bayrağı ilə qəbul edir; foto mənbəsi
yoxdursa zəncir BOŞDUR (şəkilsiz post), köhnə dizayn yox. Testlər:
`test_visual_type_is_always_news`, `test_plan_never_falls_back_to_claude_designs`.

**AI generasiya açıqdır:** zəncirin son pilləsi, ~$0.03, 67-160 saniyə.
Sonda «başqa şəkil» AI-nı təkrar çağırır — zəncir bitmir.

**AI kadrı növbə ilə dəyişir:** hər çəkiliş `images.SHOT_VARIANTS`-dan
növbəti kadrı alır — yaxın plan → geniş plan → yandan → qürub işığı →
gecə → yenidən. Sayğac `out/images/<run>/NN-bg-aiNN.png` fayllarının
sayıdır (`ai_take()`). 17.09-dan fon **yatıq** (1536×1024) yaradılır və
birbaşa kart pəncərəsinə (1200×860) kəsilir — əvvəl portret idi və kart
yalnız boş səmanı göstərirdi (dərs 41).

**Digər avtomatlaşdırma (16.09):**
- `tick` plist-də `RunAtLoad` — Mac açılan kimi bir qaçış; 09:00-18:00
  arası `prepared_today()` «no» deyirsə səhər hazırlığını TELAFİ edir
  (Mac 08:35-də sönülü olanda namizədlər yenə gəlir, dərs 37).
- Telegram `/propose` — istifadəçi namizədləri özü başlada bilir; eyni
  gün ikinci dəst təsdiq istəyir və köhnə açıq təklifi bağlayır.
- `state/inflight.json` — seçim basılanda yazılır, yazı bitəndə silinir.
  Dinləyici qalxanda yarımçıq yazını ÖZÜ davam etdirir (≤60 dəq);
  `install_launchd.sh` məşğul dinləyicini öldürmür (dərs 38).

---

## Yarımçıq qalan iş (24.09.2026)

1. **LinkedIn ilk şərh 403** — mənbə linki postlara düşmür (yuxarı bax).
   Növbəti addım: `make li-renew` ilə token yeniləyib icazəni yoxlamaq;
   düzəlməsə LinkedIn tətbiqinin məhsul icazəsinə baxmaq. Kodla həll
   olunmur.
2. **Müfəttiş balları qaçışdan qaçışa dəyişir** (haiku) — eyni şəkil bir
   qaçışda keçir, birində «səhv subyekt» alır. Variant:
   `MODEL_INSPECT=sonnet` (`.env`), +~20k Sonnet token/post. Sınanmayıb.
3. **Mac-sız işləmək** — hazırda hər şey bu laptopdadır. Yeganə etibarlı
   yol: xarici HTTP cron → GitHub `workflow_dispatch` (dərs 37-nin
   sonundakı resept; PAT-ı istifadəçi yaradır). Qurulmayıb.
4. **Scout-un azərbaycancası kobuddur** (haiku): «spam-spam etyib»,
   «xilafını eşittilər». Seçim düzgündür, mətn çirkli. Variant:
   `MODEL_SCOUT=sonnet`, +~24k token/gün. Sınanmayıb.
5. **Video/hərəkətli kart** — müzakirə olundu, qurulmadı. Qərar: əvvəlcə
   şəkil uyğunluğu, sonra hərəkət; ffmpeg lokalda var, LinkedIn Videos
   API-si yazılmayıb.
6. **`2026-09-15T07-14-48` pending** — yuxarı bax, `/skip` ilə bağlanmalı.

7. **Yerli mənbələrin məhsuldarlığı izlənməlidir** (24.09.2026-dan).
   Report.az ilk qaçışda 0 xəbər verdi — lenti yalnız son 30 xəbəri
   saxlayır və o an texnologiya xəbəri yox idi; bu normaldır, amma bir
   həftə ardıcıl 0 olarsa mənbə əvəzlənməlidir. `make sources` hər
   mənbənin 72 saatlıq sayını göstərir. Namizədlik alan yerli xəbərlərin
   payı da izlənməlidir: Scout hədəfi «təxminən yarısı» olsa da, ölçülən
   ilk qaçışda 6-dan 1-i yerli idi — o gün doğrudan yerli xəbər az idi,
   amma bu nisbət bir neçə gün eyni qalsa, ya kvota, ya da prompt
   yenidən baxılmalıdır.

8. **Türkiyə mənbəsi (Webrazzi) sınaq mərhələsindədir.** «Yerli» yolda
   sayılır, amma Azərbaycan deyil. Namizədlərə çox düşürsə çıxarılmalı:
   `sources.LOCAL_FEEDS` siyahısından bir sətir silmək kifayətdir.

---

## Növbəti addımlar (istifadəçi seçəcək)

Müzakirə olunmuş, amma qurulmamış:
- Namizədləri MODELƏ göstərmək artıq var (müfəttiş); növbəti səviyyə —
  seçimləri Telegram-da albom kimi göndərmək (indi bir-bir gəlir)
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
make test       # 228 oflayn test, 0.3s
make smoke      # real API sınağı (LinkedIn-də qaralama yaradıb silir)
make watch      # Telegram dinləyicisi (ani cavab)
make queue      # növbə və bank
make propose    # 6 namizəd göndər (3 göstərilir + 3 ehtiyat)
make replay     # eyni xəbərlə yenidən yaz (prompt sınağı)
make li-renew   # token + GitHub secret-ləri yenilə (60 gündən bir)
```

**Şəkil düymələri (news):** 🔄 Başqa şəkil (qəbul edilənlər → kollaj →
sonda seçimlər mesajı) · seçimlər mesajında 1️⃣2️⃣ Bu şəkil · 🔎 Tədbir
fotosu axtar · 🖼 Redaksiya kartı. «📷 Real foto» 16.09-da silindi
(«Başqa şəkil» onsuz da real fotolardır); «🔤 Mətn kartı» da silindi.

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

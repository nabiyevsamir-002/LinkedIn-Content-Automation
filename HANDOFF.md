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
| Kod | ~9350 sətir · 116 test (hamısı keçir, 0.14s, oflayn) |
| Repo | `github.com/nabiyevsamir-002/avto-post-linkedin` (private) |
| Workflow | `prepare` · `tick` · `health` · `test` — hamısı aktiv, cron işləyir |
| Lokal cron | launchd: `com.avtopost.prepare` (09:30) · `com.avtopost.tick` (15 dəq) |
| Dinləyici | `make watch` — Telegram düymələrinə ani cavab |
| LinkedIn | Samir Nabiyev, token 59 gün qalır |
| Kalibrləmə | ✅ tamamlanıb (positioning 7/7, voice 2 nümunə) |

**Növbə:** 2 post cədvəldə (bu gün 11:40 və 12:00 — sürət həddinə görə
**yalnız biri çıxacaq**, digəri sabaha keçəcək), 2 post təsdiq gözləyir.

**LinkedIn-də hələ bir post da yayımlanmayıb** — ilk real post bu gün.

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

**Gözlənilən cavab:** istifadəçi yeni albomu Telegram-da yoxlayacaq.
Hələ də uyğunsuzluq olsa, növbəti addım **AI şəkil generasiyası**
(`OPENAI_API_KEY`, ~$0.03/şəkil) — stok kitabxanalarda sadəcə uyğun
şəkil olmaya bilər.

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

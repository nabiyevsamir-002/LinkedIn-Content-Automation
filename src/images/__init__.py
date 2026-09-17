"""Şəkil zənciri: Visual Director → pillələr.

Zəncirin sırası Visual Director-un qərarı ilə müəyyən olunur:

  visual_type = photo  →  Pexels ×4 → Claude kart → Claude alt → AI generasiya
  visual_type = chart  →  Claude qrafik → Claude alt → Pexels ×2 → AI generasiya
  visual_type = card   →  Claude kart  → Claude alt → Pexels ×2 → AI generasiya

Pulsuz pillələr həmişə öndədir; ödənişli AI generasiyası yalnız
hər şey rədd edildikdə işə düşür. M3-də Telegram düymələri bu
pillələr arasında gəzdirəcək.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import asdict, dataclass, field

from .. import config, llm, store
from . import aigen, inspect as _inspect, news, render, stock
from . import schemas as vschemas
from . import story as _story


@dataclass
class Candidate:
    rung: int
    kind: str                 # pexels | claude | aigen
    label: str
    path: str = ""
    alt_text: str = ""
    credit: str = ""
    palette: str = ""
    error: str = ""
    tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class VisualPlan:
    director: dict = field(default_factory=dict)
    rungs: list = field(default_factory=list)      # (kind, payload) cütləri
    candidates: list = field(default_factory=list)
    agents: list = field(default_factory=list)

    @property
    def alt_text(self) -> str:
        return self.director.get("alt_text", "")


def _prompt(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def direct(post: str, research: dict, agents: list | None = None) -> dict:
    """Visual Director: hansı növ vizual lazımdır və brif nədir."""
    payload = json.dumps({
        "post": post,
        "numbers": research.get("numbers", []),
        "facts": research.get("facts", [])[:6],
        "headline": research.get("headline", ""),
        "pexels_available": stock.available(),
    }, ensure_ascii=False, indent=2)

    result = llm.call_agent(
        "visual_director", _prompt("visual_director"), payload,
        schema=vschemas.DIRECTOR, timeout=300,
    )
    if agents is not None:
        agents.append({
            "name": result.name, "model": result.model, "ok": result.ok,
            "total_tokens": result.total_tokens, "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms, "wall_ms": result.wall_ms,
            "stalled": result.stalled, "error": result.error,
        })
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(f"Visual Director uğursuz: {result.error}")
    return force_news(enforce_unit_safety(recover_tagged_fields(result.data)))


# Claude-un tipoqrafik dizaynları (chart/card/photo) istifadəçi tərəfindən
# QƏTİ rədd edilib (11.09 və 16.09.2026). 16.09-da direktor rəqəmli post
# üçün `chart` seçdi və köhnə dizayn yenə çıxdı — «news standartdır» yalnız
# promptda idi, kodda qadağa yox idi. İndi qadağa BURADADIR: direktorun
# seçimi telemetriya üçün saxlanır, kart isə həmişə `news`-dur.
FORCED_VISUAL_TYPE = "news"


def force_news(director: dict) -> dict:
    requested = (director.get("visual_type") or "").lower()
    if requested and requested != FORCED_VISUAL_TYPE:
        director["_requested_type"] = requested
        print(f"  ↪ direktor «{requested}» istədi — həmişə `news` (tipoqrafik dizayn rədd edilib)",
              flush=True)
    director["visual_type"] = FORCED_VISUAL_TYPE
    return director


# Model bəzən JSON əvəzinə alət-çağırışı sintaksisi ilə cavab verir.
# Onda ilk sahə qalan hamısını udur: `design_brief` içində
# `</design_brief><parameter name="pexels_query">…` ilişib qalır və
# `photo_queries` boş görünür — nəticədə foto axtarışı sakitcə
# «technology abstract»-a düşür, yəni mövzudan tamam kənara.
_TAG_PAT = re.compile(r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', re.S)
_TAIL_PAT = re.compile(r"</[a-z_]+>\s*(?:<parameter\b|$)", re.S)


def recover_tagged_fields(director: dict) -> dict:
    """Bir sahəyə ilişmiş `<parameter …>` bloklarını öz yerinə qaytarır."""
    if not isinstance(director, dict):
        return director
    recovered: dict = {}
    for key, value in list(director.items()):
        if not isinstance(value, str) or "<parameter" not in value:
            continue
        for name, raw in _TAG_PAT.findall(value):
            raw = raw.strip()
            if not name or not raw:
                continue
            # Yalnız BOŞ sahələri doldururuq — mövcud dəyər üstün tutulur.
            if director.get(name) in (None, "", [], {}):
                if raw.startswith("["):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        pass
                recovered[name] = raw
        # Mənbə sahəni ilk qapanan teqdən kəsirik.
        cut = value.find("<parameter")
        closing = _TAIL_PAT.search(value)
        if closing and closing.start() < cut:
            cut = closing.start()
        recovered[key] = value[:cut].rstrip()
    if recovered:
        director = {**director, **recovered}
        director["_tag_recovered"] = sorted(k for k in recovered if not k.startswith("_"))
    return director


def enforce_unit_safety(director: dict) -> dict:
    """Fərqli vahidli rəqəmləri sütunlu qrafikdə müqayisə etməyə qoymur.

    Model bəzən 3,1x · 3,9x · >50%-i bir oxda çəkir — bu, saxta qrafikdir.
    Vahidlər fərqlidirsə üslub məcburi olaraq "stats"-a keçirilir.
    """
    points = director.get("data_points") or []
    if len(points) < 2:
        return director
    units = {
        (p.get("unit") or _guess_unit(str(p.get("value", "")))).strip().lower()
        for p in points
    }
    if len(units) > 1 and director.get("chart_style") == "bars":
        director["chart_style"] = "stats"
        director["_unit_guard"] = f"vahidlər fərqlidir ({', '.join(sorted(units))}) → stats"
    elif not director.get("chart_style"):
        director["chart_style"] = "bars" if len(units) == 1 else "stats"
    return director


def _guess_unit(value: str) -> str:
    value = value.strip()
    if "%" in value:
        return "%"
    if value.lower().endswith("x"):
        return "x"
    if any(sym in value for sym in ("$", "USD", "€")):
        return "usd"
    return "other"


def brand() -> dict:
    """Şəkildə görünəcək imza — sahibliyi aydın göstərir."""
    name = config.BRAND_NAME
    if not name:
        try:
            from .. import linkedin

            token = linkedin.load_token()
            name = token.name if token else ""
        except Exception:  # noqa: BLE001
            name = ""
    return {
        "name": name,
        "handle": config.BRAND_HANDLE,
        "color": config.BRAND_COLOR,
        "has_logo": bool(config.BRAND_LOGO),
    }


def design(director: dict, variant: str, agents: list | None = None) -> tuple[str, str, dict]:
    """Claude vizualı: brifdən HTML dizayn."""
    payload = json.dumps({
        "visual_type": director.get("visual_type"),
        "kicker": director.get("kicker", ""),
        "headline": director.get("headline", ""),
        "support": director.get("support", ""),
        "chart_style": director.get("chart_style", "stats"),
        "data_points": director.get("data_points", []),
        "design_brief": director.get("design_brief", ""),
        "variant_instruction": variant,
        "brand": brand(),
    }, ensure_ascii=False, indent=2)

    result = llm.call_agent(
        "visual_design", _prompt("visual_design"), payload,
        schema=vschemas.DESIGN, timeout=420,
    )
    if agents is not None:
        agents.append({
            "name": result.name, "model": result.model, "ok": result.ok,
            "total_tokens": result.total_tokens, "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms, "wall_ms": result.wall_ms,
            "stalled": result.stalled, "error": result.error,
        })
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(f"Vizual dizayn uğursuz: {result.error}")
    data = result.data
    return data.get("html", ""), data.get("palette", ""), data


VARIANT_PRIMARY = (
    "Əsas variant: brifə sadiq qal, ən aydın və oxunaqlı həlli seç."
)
VARIANT_ALT = (
    "ALTERNATİV variant: birincidən açıq şəkildə fərqlən — başqa palitra, "
    "başqa kompozisiya (məsələn mərkəzləşdirilmiş yerinə sol-yaslı, və ya "
    "qrafik yerinə böyük rəqəm vurğusu). Eyni fikri fərqli görüntü ilə ver."
)


# --- Seçim: hekayə → axtarış → müfəttiş → qərarlar ---------------------------

@dataclass
class Selection:
    story: dict = field(default_factory=dict)
    queries: list = field(default_factory=list)
    accepted: list = field(default_factory=list)     # Decision.to_dict()
    rejected: list = field(default_factory=list)
    searched: int = 0
    expanded: bool = False

    @property
    def none_suitable(self) -> bool:
        return not self.accepted


def _selection_path(run_id: str) -> pathlib.Path:
    return config.OUT_DIR / "images" / run_id / "selection.json"


def load_selection(run_id: str) -> Selection | None:
    data = store.read_json(_selection_path(run_id), None)
    return Selection(**data) if data else None


def _save_selection(run_id: str, sel: Selection) -> None:
    store.write_json(_selection_path(run_id), asdict(sel))


_DECISIONS: dict[str, list] = {}       # run_id → canlı Decision obyektləri (foto ilə)


PERSON_CACHE = config.STATE_DIR / "person_photos.json"


def _person_lookup(people: list, timeout: float = 60.0) -> list:
    """İctimai şəxsləri Openverse-də (Wikimedia/Flickr, azad lisenziya) ADLA axtarır.

    Openverse bütün sözləri tələb edir: «Jensen Huang portrait» → 0 nəticə,
    «Jensen Huang» → CES keynote 4032×3024 CC0 (ölçülüb 15.09.2026). Ona görə
    şəxs üçün YALNIZ ad göndərilir; nəyin portret olduğunu müfəttiş deyir.
    Yavaşdır (7-30 s) — paralel və öz həddi ilə.
    """
    import concurrent.futures

    if not people or "Openverse" not in stock.active_providers():
        return []
    cache = store.read_json(PERSON_CACHE, {}) or {}
    out: list = []
    todo = []
    for name in people[:2]:
        rows = cache.get(name.lower())
        if rows:
            out += [_photo_from_row(r) for r in rows]
        else:
            todo.append(name)
    if todo:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(todo))
        futures = {pool.submit(stock._openverse, name, 8): name for name in todo}
        try:
            for fut in concurrent.futures.as_completed(futures, timeout=timeout):
                try:
                    rows = [p for p in fut.result() if stock._big_enough(p)]
                except Exception:  # noqa: BLE001
                    continue
                if rows:
                    cache[futures[fut].lower()] = [_row_from_photo(p) for p in rows]
                out += rows
        except concurrent.futures.TimeoutError:
            pass          # gecikən ad bu dəfə nəticəsiz qalır (görünən: Telegram «tədbir axtar»)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        store.write_json(PERSON_CACHE, cache)
    for p in out:
        p.score = max(p.score, 1.6)     # ad mənbəyi — stok «uyğunluğundan» yuxarı
    return out


def _row_from_photo(p) -> dict:
    return {"url": p.url, "page_url": p.page_url, "provider": p.provider,
            "photographer": p.photographer, "width": p.width, "height": p.height,
            "license": p.license, "caption": p.caption, "date": getattr(p, "date", "")}


def _photo_from_row(r: dict):
    p = stock.Photo(url=r["url"], provider=r.get("provider", "Openverse"),
                    photographer=r.get("photographer", ""), page_url=r.get("page_url", ""),
                    width=r.get("width", 0), height=r.get("height", 0),
                    license=r.get("license", ""), caption=r.get("caption", ""))
    p.date = r.get("date", "")
    return p


def _pool(story: _story.Story, director: dict, event_only: bool = False) -> list:
    """Namizəd hovuzu: keş → şəxs adı (Openverse) → sorğular → məqalə şəkilləri."""
    queries = _story.queries(story, extra=[] if event_only else photo_queries(director))
    if event_only:
        pair = " ".join(story.people[:2])
        year = story.event_date[:4] if story.event_date else ""
        queries = [q for q in (
            f"{pair} {story.event_name}".strip() if story.event_confirmed else "",
            f"{pair} {year}".strip(), f"{pair} meeting".strip() if pair else "",
        ) if q.strip()]
    found = [] if event_only else _person_lookup(story.people)
    for start in range(0, min(len(queries), 9), 3):        # üç-üç: hər dəstə bir axtarış
        found += stock.search(queries[start:start + 3], limit=14 if start == 0 else 8)
    found = [_inspect.commons_enrich(p) for p in found]
    pool = _inspect.cached_assets(story) + found
    if story.source_urls:
        pool += _inspect.article_images(story.source_urls)
    seen, out = set(), []
    for p in pool:
        if p.key not in seen:
            seen.add(p.key)
            out.append(p)
    return out


def analyze(director: dict, run_id: str, agents: list | None = None,
            force: bool = False, event_only: bool = False) -> Selection:
    """Hekayəni anla → namizədləri tap → müfəttiş baxsın → qərarlar.

    Nəticə diskə yazılır (`selection.json`) — Telegram dinləyicisi ayrı
    prosesdir və eyni qərarları təkrar pul xərcləmədən oxumalıdır.
    """
    if not force and run_id in _DECISIONS:
        sel = load_selection(run_id)
        if sel:
            return sel
    post = director.get("_post", "")
    story = _story.from_director(director, director.get("_research"))
    pool = _pool(story, director, event_only=event_only)
    queries = _story.queries(story, extra=photo_queries(director))

    def expand():
        return _pool(story, director, event_only=True)

    accepted, rejected = ([], [])
    if pool:
        accepted, rejected = _inspect.select(
            pool, story, post, run_id, agents, want=2,
            expand=None if event_only else expand)
    if event_only and run_id in _DECISIONS:
        # Tədbir axtarışı əvvəlki qəbulları ƏVƏZ ETMİR — üstünə gəlir
        old_ok = [d for d in _DECISIONS[run_id] if d.accepted]
        keys = {d.photo.key for d in accepted}
        accepted = accepted + [d for d in old_ok if d.photo.key not in keys]
        order = {"event": 0, "archive": 1, "contextual": 2}
        accepted.sort(key=lambda d: order.get(d.image_type, 9))
    _DECISIONS[run_id] = accepted + rejected
    sel = Selection(
        story=story.to_dict(), queries=queries,
        accepted=[d.to_dict() for d in accepted],
        rejected=[d.to_dict() for d in rejected],
        searched=len(pool), expanded=bool(event_only),
    )
    _save_selection(run_id, sel)
    if sel.none_suitable:
        # Görünən ehtiyat (dərs 11): boş nəticə səssiz keçmir
        print(f"  ⚠ uyğun şəkil tapılmadı — {len(pool)} namizəd baxıldı, "
              f"hamısı rədd edildi", flush=True)
    return sel


def decisions(run_id: str, director: dict | None = None,
              agents: list | None = None) -> list:
    """Bu qaçış üçün canlı Decision obyektləri (foto ilə). Diskdən bərpa edir."""
    if run_id in _DECISIONS:
        return _DECISIONS[run_id]
    sel = load_selection(run_id)
    if sel is None:
        if director is None:
            return []
        analyze(director, run_id, agents)
        return _DECISIONS.get(run_id, [])
    out = []
    for row in sel.accepted + sel.rejected:
        ph = row["photo"]
        photo = stock.Photo(url=ph["url"], provider=ph["provider"], photographer="",
                            page_url=ph["page_url"], caption=ph.get("caption", ""),
                            license=row.get("license", ""))
        photo.date = ph.get("date", "")
        out.append(_inspect.Decision(
            photo=photo, accepted=row["accepted"], image_type=row["image_type"],
            reasons=row.get("reasons", []), relevance=row.get("relevance", ""),
            uncertainty=row.get("uncertainty", ""), focus=row.get("focus"),
            source_page=row.get("source_page", ""), date=row.get("date", ""),
            attribution=row.get("attribution", ""), license=row.get("license", ""),
            people_count=int(row.get("people_count", 0) or 0),
        ))
    _DECISIONS[run_id] = out
    return out


def accepted_decisions(run_id: str) -> list:
    return [d for d in decisions(run_id) if d.accepted]


def collage_pair(run_id: str, story: dict | None = None) -> tuple | None:
    """İki FƏRQLİ şəxsin qəbul edilmiş portreti — kollaj üçün."""
    people = [p for p in (story or {}).get("people", [])]
    if len(people) < 2:
        return None
    ok = accepted_decisions(run_id)

    def subject_of(d):
        cap = (d.photo.caption or "").lower()
        for person in people:
            last = person.split()[-1].lower()
            if last in cap:
                return person
        return None
    by_person: dict[str, object] = {}
    # Tək şəxsli portret üstündür — iki nəfərli kadr «görüş» təəssüratı verir
    for d in sorted(ok, key=lambda d: (d.people_count != 1, d.people_count)):
        who = subject_of(d)
        if who and who not in by_person:
            by_person[who] = d
    if len(by_person) < 2:
        return None
    first, second = people[0], next(p for p in people[1:] if p in by_person) \
        if people[0] in by_person else (None, None)
    if first not in by_person:
        return None
    return (first, by_person[first], second, by_person[second])


def plan(director: dict, run_id: str | None = None,
         agents: list | None = None) -> list[tuple[str, object]]:
    """Vizual növünə görə pillə sırasını qurur.

    `news` üçün pillələr MÜFƏTTİŞİN qəbul etdiyi şəkillərdir (ən çox 2),
    sonra kollaj (iki şəxsin portreti varsa). Rədd edilmiş və ya ümumi
    stok fotosu zəncirə DÜŞMÜR — heç nə qalmayanda zəncir bitir və
    istifadəçiyə «uyğun şəkil tapılmadı» deyilir (15.09.2026).
    """
    # Növ nə olursa olsun zəncir `news`-dur: Claude tipoqrafik dizaynları
    # avtomatik zəncirə DÜŞMÜR (`force_news`). Köhnə `chart`/`card`/`photo`
    # zəncirləri yalnız açıq `_allow_claude` bayrağı ilə qalır (sınaq/manual).
    kind = (director.get("visual_type") or "news").lower()
    if kind != "news" and not director.get("_allow_claude"):
        kind = "news"
    claude_rungs = [("claude", VARIANT_PRIMARY), ("claude", VARIANT_ALT)]
    photo_count = 6 if kind == "photo" else 4
    photo_rungs = [("pexels", i) for i in range(photo_count)] if stock.available() else []
    ai_rungs = [("aigen", None)] if aigen.available() else []

    if kind == "news":
        if not photo_rungs:
            # Foto mənbəsi yoxdursa zəncir BOŞDUR — köhnə dizayna düşmək
            # yoxdur; post şəkilsiz gedir və istifadəçi bunu görür.
            return []
        people = (director.get("story") or {}).get("people") or []
        if run_id is None:
            # Təhlilsiz plan (sxem sınaqları üçün): 2 foto yeri + kollaj yeri
            variants = [("news", 0), ("news", 1)]
            if len(people) >= 2:
                variants.append(("collage", None))
        else:
            sel = load_selection(run_id) or analyze(director, run_id, agents)
            people = (sel.story or {}).get("people") or people
            variants = [("news", i) for i in range(min(2, len(sel.accepted)))]
            if collage_pair(run_id, sel.story):
                variants.append(("collage", None))
        # AI fon YALNIZ şəxssiz hekayələrdə: real insanların iştirak etdiyi
        # hadisəni foto-realistik «çəkmək» uydurmadır (tələb 5).
        if aigen.available() and not people:
            variants.append(("news", "ai"))
        return variants

    if kind == "photo":
        return photo_rungs + claude_rungs + ai_rungs
    return claude_rungs + photo_rungs + ai_rungs


def produce(
    director: dict, rung: int, rungs: list, run_id: str,
    agents: list | None = None, fallback_query: str = "",
) -> Candidate:
    """Bir pilləni istehsal edir."""
    out_dir = config.OUT_DIR / "images" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    if fallback_query and not director.get("pexels_query"):
        director = {**director, "_fallback_query": fallback_query}
    kind, payload = rungs[rung]
    dst = out_dir / f"{rung:02d}-{kind}.png"

    try:
        if kind == "collage":
            sel = load_selection(run_id) or analyze(director, run_id, agents)
            pair = collage_pair(run_id, sel.story)
            if not pair:
                return Candidate(rung, kind, "Redaksiya kollajı",
                                 error="iki şəxsin təsdiqlənmiş portreti yoxdur")
            name_a, dec_a, name_b, dec_b = pair
            fon = out_dir / f"{rung:02d}-bg.png"
            bub = out_dir / f"{rung:02d}-bubble.png"
            stock.download(dec_a.photo, fon, focus=dec_a.focus)
            stock.download(dec_b.photo, bub, focus=dec_b.focus)
            body, css = news.build(director, str(fon), str(bub), brand(),
                                   labels={"main": name_a, "bubble": name_b})
            render.html_to_png(render.wrap(body, css, brand=False), dst)
            credit = f"{dec_a.attribution} · {dec_b.attribution}"
            return Candidate(
                rung=rung, kind=kind, path=str(dst),
                label=f"Redaksiya kollajı — {name_a} + {name_b} (arxiv portretləri)",
                alt_text=director.get("alt_text", ""), credit=credit,
            )

        if kind == "news":
            if payload == "ai":
                # Hər çağırış ayrı kadr variasiyasıdır (yaxın plan → geniş
                # plan → …), yoxsa eyni sorğu oxşar şəkillər verir. Əvvəlki
                # fonlar silinmir — hər biri ~$0.03-a başa gəlib.
                take = ai_take(run_id, rung)
                fon = out_dir / f"{rung:02d}-bg-ai{take:02d}.png"
                aigen.generate(ai_prompt(director, take), fon)
                body, css = news.build(director, str(fon), "", brand())
                render.html_to_png(render.wrap(body, css, brand=False), dst)
                return Candidate(
                    rung=rung, kind=kind, path=str(dst),
                    label=f"Xəbər kartı — AI fonu · {ai_shot(take)[0]} (ödənişli)",
                    alt_text=director.get("alt_text", ""), cost_usd=0.03,
                )

            sel = load_selection(run_id) or analyze(director, run_id, agents)
            ok = accepted_decisions(run_id)
            index = int(payload)
            if index >= len(ok):
                return Candidate(rung, kind, "Xəbər kartı",
                                 error="uyğun şəkil tapılmadı — bütün namizədlər rədd edildi"
                                 if not ok else "bu sıra üçün təsdiqlənmiş şəkil yoxdur")
            dec = ok[index]
            fon = out_dir / f"{rung:02d}-bg.png"
            stock.download(dec.photo, fon, focus=dec.focus)

            # Dairəvi ikinci şəkil YALNIZ təsdiqlənmiş başqa şəkildən —
            # rədd edilmiş və ya ümumi foto kartda görünməməlidir.
            bubble = ""
            others = [d for d in ok if d is not dec]
            if others:
                bub = out_dir / f"{rung:02d}-bubble.png"
                try:
                    stock.download(others[0].photo, bub, focus=others[0].focus)
                    bubble = str(bub)
                except Exception:  # noqa: BLE001 — ikinci şəkil məcburi deyil
                    bubble = ""

            body, css = news.build(director, str(fon), bubble, brand())
            render.html_to_png(render.wrap(body, css, brand=False), dst)
            credit = dec.attribution
            if dec.image_type == "archive" and dec.date:
                credit += f" (arxiv foto, {dec.date[:4]})"
            return Candidate(
                rung=rung, kind=kind, path=str(dst),
                label=f"Xəbər kartı #{index + 1} — {dec.label}: {dec.relevance[:60]}",
                alt_text=director.get("alt_text", ""), credit=credit,
            )

        if kind == "claude":
            variant = "əsas" if payload is VARIANT_PRIMARY else "alternativ"
            html, palette, _ = design(director, str(payload), agents)
            render.html_to_png(render.wrap(html, palette=palette), dst)
            return Candidate(
                rung=rung, kind=kind, path=str(dst),
                label=f"Claude dizaynı ({director.get('visual_type')}, {variant})",
                alt_text=director.get("alt_text", ""), palette=palette,
                tokens=agents[-1]["total_tokens"] if agents else 0,
                cost_usd=agents[-1]["cost_usd"] if agents else 0.0,
            )

        if kind == "pexels":
            # Üç sorğu (səhnə → metafora → geniş) birlikdə axtarılır və
            # nəticələr uyğunluğa görə sıralanır. Azərbaycanca başlıqla
            # axtarmaq mənasızdır — nəticə tamamilə uyğunsuz olur.
            query = photo_queries(director)
            photos = _photo_cache(query, director.get("_post", ""), agents)
            index = int(payload)
            if index >= len(photos):
                return Candidate(rung, kind, f"Foto #{index + 1}",
                                 error="bu sıra üçün foto tapılmadı")
            photo = photos[index]
            stock.download(photo, dst)
            return Candidate(
                rung=rung, kind=kind, path=str(dst),
                label=(photo.reason[:70] if photo.reason
                   else f"{photo.provider} #{index + 1}"),
                alt_text=director.get("alt_text", ""), credit=photo.credit,
            )

        if kind == "aigen":
            prompt = (
                f"{director.get('design_brief', '')}. "
                f"Photorealistic editorial photograph, vertical 4:5, "
                f"no text, no logos, professional lighting."
            )
            aigen.generate(prompt, dst)
            return Candidate(
                rung=rung, kind=kind, path=str(dst), label="AI generasiyası (ödənişli)",
                alt_text=director.get("alt_text", ""), cost_usd=0.03,
            )
    except Exception as exc:  # noqa: BLE001 — bir pillə zənciri dayandırmır
        return Candidate(rung, kind, f"{kind} #{rung}", error=f"{type(exc).__name__}: {exc}")

    return Candidate(rung, kind, "naməlum pillə", error="dəstəklənməyən növ")


_PHOTO_MEMO: dict[str, list] = {}
_PICKER_MEMO: dict[str, str] = {}


# AI çəkilişləri növbə ilə bu kadrlardan keçir. Eyni sorğu ilə model
# hər dəfə oxşar kompozisiya verirdi (11.09.2026) — «başqa şəkil» basan
# istifadəçi isə açıq fərq gözləyir. İşıq da variasiyanın hissəsidir:
# qürub və gecə əsas sorğudakı «gündüz» işığı ilə toqquşmasın deyə
# işıq sözləri sabit hissədə yox, buradadır.
SHOT_VARIANTS: tuple[tuple[str, str], ...] = (
    ("yaxın plan", "close-up shot, tight framing on the main subject, "
                   "shallow depth of field, soft natural daylight"),
    ("geniş plan", "wide establishing shot, the subject clearly visible at the "
                   "centre of the frame with its environment around it, deep focus"),
    ("yandan", "side view from a low angle, strong diagonal perspective, "
               "dramatic directional side lighting"),
    ("qürub işığı", "golden hour at sunset, long warm shadows, "
                    "orange and amber glow, backlit haze"),
    ("gecə", "night scene, artificial city lights and reflections, "
             "deep blue shadows, moody low-key lighting"),
)


def ai_shot(take: int) -> tuple[str, str]:
    """`take`-ci çəkilişin (etiket, sorğu parçası) cütü — dövri."""
    return SHOT_VARIANTS[take % len(SHOT_VARIANTS)]


def ai_take(run_id: str, rung: int) -> int:
    """Bu pillə üçün neçənci AI çəkilişidir.

    Sayğac ayrıca vəziyyət faylı deyil — əvvəlki fon fayllarının sayıdır
    (`NN-bg-aiNN.png`). Beləcə Telegram axını da, `make image` də eyni
    qovluğa baxır və eyni cür növbələyir (bax dərs 13).
    """
    out_dir = config.OUT_DIR / "images" / run_id
    return len(list(out_dir.glob(f"{rung:02d}-bg-ai*.png")))


def ai_prompt(director: dict, take: int = 0) -> str:
    """Brifdən AI şəkil sorğusu; `take` kadr variasiyasını seçir.

    Loqo və mətn İSTƏMİRİK: model onları səhv çəkir (əyri hərflər,
    uydurma brend nişanları) və üstəlik brend loqosunu generasiya
    etmək hüquqi problemdir. Kartın öz başlığı onsuz da mətni daşıyır.
    """
    # `design_brief` BURAYA QOŞULMUR. O, KART dizaynı üçün yazılır və
    # içində «üstündə iri xəbər başlığı zolağı» kimi göstərişlər olur —
    # şəkil modeli onu hərfi qəbul edib şəklin üstünə mətn yazır.
    # 11.09.2026-da məhz belə oldu: AI «CORPORATE SECRECY» çəkdi və
    # kartın öz başlığı ilə toqquşdu.
    scene = (photo_queries(director) or ["editorial scene"])[0]
    _, shot = ai_shot(take)
    # Kompozisiya YATIQDIR və subyekt mərkəzdədir — kart bu kadrı bütöv
    # göstərir. Köhnə «upper third calm» qaydası (başlıq şəklin üstündə
    # olanda lazım idi) xəbər kartında göstərilən sahəni boşaldırdı.
    return (
        f"{scene}. {shot}. "
        "Photorealistic editorial photograph, horizontal 3:2 composition, "
        "main subject in the middle of the frame filling a good part of it, "
        "no large empty sky or empty foreground, "
        "cinematic, muted realistic colors, documentary style. "
        "CRITICAL: the image must contain absolutely no text, no letters, "
        "no words, no captions, no titles, no signage, no logos, "
        "no watermarks and no user interface elements."
    )


def photo_queries(director: dict) -> list:
    """Direktorun foto sorğuları — 3 səviyyə, ehtiyat variantları ilə."""
    queries = [q for q in (director.get("photo_queries") or []) if q]
    if not queries and director.get("pexels_query"):
        queries = [director["pexels_query"]]          # köhnə formatla uyğunluq
    if not queries and director.get("_fallback_query"):
        queries = [director["_fallback_query"]]
    return queries or list(GENERIC_FALLBACK)


# Bura düşmək HƏMİŞƏ nasazlıqdır: mövzu ilə əlaqəsi olmayan stok
# klişeləri gəlir. Əvvəllər səssiz baş verirdi — kvant kalibrasiyası
# haqqında post 3 mücərrəd "texnologiya" şəkli ilə Telegram-a getdi.
GENERIC_FALLBACK = ["technology abstract"]


def queries_are_generic(director: dict) -> bool:
    """Sorğu mövzudan qopubmu — çağıran tərəf xəbərdarlıq göstərsin."""
    return photo_queries(director) == GENERIC_FALLBACK


def _photo_cache(query, post: str = "", agents: list | None = None) -> list:
    """Axtarır və modelə ən uyğunları seçdirir.

    Söz üst-üstə düşməsi zəif göstəricidir — əşya metaforaları etiket
    sıx olduğu üçün insanlı səhnələri sıxışdırır. Model isə şəklin
    hekayəyə yaraşıb-yaraşmadığını həqiqətən qiymətləndirir.
    """
    # Açarda `post` da var: postsuz (seçicisiz) nəticə postlu çağırışı
    # zəhərləməsin — 15.09.2026-da ilk şəkil postsuz quruldu, xam sıra
    # memo-ya düşdü və 7 «başqa şəkil» basışı eyni sıranı gördü.
    key = (" | ".join(query) if isinstance(query, list) else query) + f" #post={bool(post)}"
    if key in _PHOTO_MEMO:
        return _PHOTO_MEMO[key]

    found = stock.search(query, limit=14)
    # Təkrar filtri modelin seçimindən ASILI OLMAMALIDIR: iki eyni
    # kolba şəkli bir seçim deməkdir, iki yox. Əvvəllər bu filtr yalnız
    # `pick_best` daxilində idi, o da `post` boş olanda atlanırdı.
    found = stock._dedupe_by_concept(found)
    picker = "atlandı"
    if post and len(found) > 3:
        try:
            ranked = stock.pick_best(found, post, count=6, agents=agents)
            # Seçilməyənlər sıranın sonuna qalır — «başqa şəkil» üçün
            rest = [p for p in found if p not in ranked]
            found = ranked + rest
            picker = "ok" if any(p.reason for p in ranked) else "işləmədi"
        except Exception as exc:  # noqa: BLE001 — seçim sınsa sıralama qalır
            picker = f"xəta: {type(exc).__name__}"
    if picker != "ok":
        # Ehtiyat görünən olmalıdır (dərs 11): seçici işləməyəndə şəkillər
        # xam söz-uyğunluğu sırası ilə gedir — bunu həm konsol, həm etiket desin.
        print(f"  ⚠ foto seçici {picker} — sıra xam söz-uyğunluğudur", flush=True)
    _PICKER_MEMO[key] = picker
    _PHOTO_MEMO[key] = found
    return found


def picker_state(query, post: str = "") -> str:
    """Bu sorğu üçün model seçici işləyibmi — etiket üçün."""
    key = (" | ".join(query) if isinstance(query, list) else query) + f" #post={bool(post)}"
    return _PICKER_MEMO.get(key, "atlandı")


def save_manifest(run_id: str, plan_obj: VisualPlan) -> pathlib.Path:
    """M3-də Telegram zənciri bu faylı oxuyacaq."""
    path = config.OUT_DIR / "images" / run_id / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "run_id": run_id,
        "director": plan_obj.director,
        "rungs": [{"rung": i, "kind": k} for i, (k, _) in enumerate(plan_obj.rungs)],
        "candidates": [asdict(c) for c in plan_obj.candidates],
        "agents": plan_obj.agents,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(run_id: str) -> dict:
    """Saxlanmış vizual planı oxuyur (Telegram şəkil zənciri üçün)."""
    path = config.OUT_DIR / "images" / run_id / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"Vizual manifest tapılmadı: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))

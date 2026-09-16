"""Şəkil müfəttişi: model şəkli GÖRÜR, qaydalar isə kodda QƏRAR verir.

15.09.2026-a qədər seçici (`stock.pick_best`) modelə yalnız təsvir mətni
göndərirdi. «Jensen Huang — Nvidia Keynote» fotosu 1-ci seçildi — kadrda
Huang küncdə kiçik fiqur idi, kadr laptop slaydı. Mətn uyğun idi, şəkil
yox. İndi:

  1. namizədlər kiçik önizləməyə (≤640 px) endirilir;
  2. model `Read` aləti ilə HƏR faylı açır və 0-3 ballarla qiymətləndirir
     (subyekt · tədbir · aydınlıq · aldadıcılıq · görünən yazı · fokus);
  3. QƏRAR bu modulda, açıq qaydalarla verilir — model bal verir, kod
     qəbul/rədd edir; lisenziya, mənbə və tarix modelin fikri deyil,
     metadatadır.

«99% uyğunluq» burada ölçülən məqsəddir: hər qərar strukturlaşdırılmış,
səbəbli və manifestə yazılır. Heç bir namizəd keçmirsə cavab «uyğun
şəkil yoxdur»dur — bu, uğursuzluq deyil, düzgün nəticədir.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from .. import config, llm, net
from . import stock, story as _story

INSPECT_MAX = int(os.environ.get("INSPECT_MAX", "6"))   # bir turda baxılan namizəd
THUMB_SIDE = 640

# Yayım üçün qəbul edilən lisenziyalar. Provayder platforma lisenziyası
# (Pexels/Unsplash/Pixabay) kommersiya istifadəsinə icazə verir; Openverse
# lisenziya kodunu qaytarır; məqalə şəkli isə naməlumdur → rədd.
PLATFORM_LICENSED = {"Pexels", "Unsplash", "Pixabay"}
OPEN_LICENSES = {"cc0", "pdm", "by", "by-sa", "publicdomain", "public domain",
                 "cc-by", "cc-by-sa", "cc by", "cc by-sa"}

INSPECT_SCHEMA = {
    "type": "object",
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "scene": {"type": "string"},
                    "visible_text": {"type": "string"},
                    "people_count": {"type": "integer"},
                    "identity_basis": {"type": "string"},
                    "subject_relevance": {"type": "integer"},
                    "event_relevance": {"type": "integer"},
                    "clarity": {"type": "integer"},
                    "misleading": {"type": "boolean"},
                    "wrong_subject": {"type": "boolean"},
                    "focus": {"type": ["array", "null"], "items": {"type": "number"}},
                    "note": {"type": "string"},
                },
                "required": ["index", "scene", "subject_relevance", "event_relevance",
                             "clarity", "misleading"],
            },
        },
        "none_suitable": {"type": "boolean"},
    },
    "required": ["assessments"],
}


@dataclass
class Assessment:
    index: int
    scene: str = ""
    visible_text: str = ""
    people_count: int = 0
    identity_basis: str = "none"
    subject_relevance: int = 0
    event_relevance: int = 0
    clarity: int = 0
    misleading: bool = False
    wrong_subject: bool = False
    focus: list | None = None
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Assessment":
        def _i(k, lo=0, hi=3):
            try:
                return max(lo, min(hi, int(d.get(k, 0))))
            except (TypeError, ValueError):
                return 0
        focus = d.get("focus")
        if not (isinstance(focus, list) and len(focus) == 4):
            focus = None
        else:
            try:
                focus = [max(0.0, min(1.0, float(v))) for v in focus]
            except (TypeError, ValueError):
                focus = None
        return cls(
            index=int(d.get("index", -1)), scene=str(d.get("scene") or ""),
            visible_text=str(d.get("visible_text") or ""),
            people_count=_i("people_count", 0, 99),
            identity_basis=str(d.get("identity_basis") or "none"),
            subject_relevance=_i("subject_relevance"),
            event_relevance=_i("event_relevance"), clarity=_i("clarity"),
            misleading=bool(d.get("misleading")), wrong_subject=bool(d.get("wrong_subject")),
            focus=focus, note=str(d.get("note") or ""),
        )


@dataclass
class Decision:
    """Strukturlaşdırılmış qərar — Telegram, manifest və testlər üçün."""
    photo: stock.Photo
    accepted: bool
    image_type: str                 # event | archive | contextual | rejected
    reasons: list = field(default_factory=list)
    relevance: str = ""             # niyə uyğundur (modelin səhnə təsviri)
    uncertainty: str = ""
    focus: list | None = None
    source_page: str = ""
    date: str = ""
    attribution: str = ""
    license: str = ""
    people_count: int = 0           # kollaj üçün: tək şəxsli portret üstündür

    def to_dict(self) -> dict:
        d = asdict(self)
        d["photo"] = {"url": self.photo.url, "page_url": self.photo.page_url,
                      "provider": self.photo.provider, "caption": self.photo.caption,
                      "date": getattr(self.photo, "date", "")}
        return d

    @property
    def label(self) -> str:
        return {"event": "tədbir fotosu", "archive": "arxiv fotosu",
                "contextual": "kontekst fotosu"}.get(self.image_type, "rədd")


# --- lisenziya və tarix -------------------------------------------------

def licensed(photo: stock.Photo) -> bool:
    """Yayım üçün istifadəyə icazə varmı.

    Commons «CC BY 2.0», «by-sa-4.0», «cc0-1.0», «Public domain» kimi yazır —
    versiya və ayırıcılar atılır, NC/ND (kommersiya/törəmə qadağası) rədd
    olunur. 15.09.2026 dry run: «by-2.0» tanınmadığı üçün 5 Jensen Huang
    fotosundan 4-ü lisenziyasız sayılmışdı.
    """
    if photo.provider in PLATFORM_LICENSED:
        return True
    lic = (photo.license or "").strip().lower()
    if not lic:
        return False
    tokens = [t for t in re.split(r"[\s\-_/.]+", lic) if t and not re.match(r"^\d+$", t)]
    if any(t in ("nc", "nd") for t in tokens):
        return False
    core = "".join(t for t in tokens if t != "cc")
    return core in {"by", "bysa", "0", "zero", "pdm", "publicdomain", "public",
                    "publicdomainmark", "cc0"} or core.startswith("by") or \
        core.startswith("publicdomain") or lic in OPEN_LICENSES


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not m:
        m = re.match(r"(\d{4})[:/](\d{2})[:/](\d{2})", value)      # EXIF «2025:01:07»
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# --- qaydalar -------------------------------------------------------------

def decide(photo: stock.Photo, a: Assessment, story: _story.Story) -> Decision:
    """Açıq qəbul/rədd qaydaları. Hər meyar ayrıca, səbəblər siyahıda."""
    reasons: list[str] = []
    photo_date = _parse_date(getattr(photo, "date", "") or "")
    event_date = _parse_date(story.event_date) if story.event_confirmed else None

    if not licensed(photo):
        reasons.append("lisenziya təsdiqlənməyib — yayım üçün istifadə olunmur")
    if a.clarity == 0 and not a.scene:
        reasons.append("şəkil açıla bilmədi")
    if a.wrong_subject:
        reasons.append("səhv subyekt (başqa məhsul/tədbir/şirkət)")
    if a.subject_relevance < 2:
        reasons.append("hekayənin subyekti görünmür — yalnız kənar açar söz"
                       if a.subject_relevance == 0 else "subyekt şəkildə yoxdur")
    if a.identity_basis == "none" and a.subject_relevance >= 2 and story.people:
        reasons.append("şəxsin kimliyi mənbə təsvirindən təsdiqlənmir")
    if a.clarity < 2:
        reasons.append("aydınlıq/kompozisiya zəifdir (subyekt kiçik və ya bulanıq)")
    if a.misleading:
        reasons.append("başlıqla yanaşı aldadıcı olar")

    # Növ: tədbir fotosu yalnız tədbir təsdiqlənib, model 2+ verib VƏ tarix
    # tədbirlə üst-üstə düşəndə. Köhnə foto «tədbir» kimi getmir.
    image_type = "contextual"
    if story.event_confirmed and a.event_relevance >= 2:
        if photo_date and event_date and abs((photo_date - event_date).days) <= 3:
            image_type = "event"
        elif photo_date and event_date and photo_date < event_date:
            image_type = "archive"
        else:
            image_type = "contextual"     # tarix yoxdur → tədbir iddiası yoxdur
    elif photo_date and event_date and photo_date < event_date:
        image_type = "archive"

    accepted = not reasons
    if not accepted:
        image_type = "rejected"
    uncertainty = a.note or ""
    if accepted and image_type != "event" and story.event_confirmed:
        uncertainty = (uncertainty + " · " if uncertainty else "") + \
            "tədbirin öz fotosu deyil — kontekst/arxiv kimi işlədilir"
    if accepted and not photo_date:
        uncertainty = (uncertainty + " · " if uncertainty else "") + "çəkiliş tarixi naməlumdur"
    return Decision(
        photo=photo, accepted=accepted, image_type=image_type, reasons=reasons,
        relevance=a.scene, uncertainty=uncertainty, focus=a.focus,
        source_page=photo.page_url, date=getattr(photo, "date", "") or "",
        attribution=photo.credit, license=photo.license or
        ("platform" if photo.provider in PLATFORM_LICENSED else ""),
        people_count=a.people_count,
    )


# --- önizləmə və model ------------------------------------------------------

def thumbnails(photos: list, run_id: str, max_side: int = THUMB_SIDE) -> list[pathlib.Path | None]:
    """Kiçik önizləmələr — model bunlara baxır. Alınmayan → None."""
    from PIL import Image

    out_dir = config.OUT_DIR / "images" / run_id / "inspect"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[pathlib.Path | None] = []
    for i, photo in enumerate(photos):
        dst = out_dir / f"{i:02d}.jpg"
        try:
            if not dst.exists():
                raw = out_dir / f"{i:02d}.src"
                raw.write_bytes(net.fetch(photo.url, timeout=40))
                with Image.open(raw) as im:
                    im = im.convert("RGB")
                    im.thumbnail((max_side, max_side))
                    im.save(dst, "JPEG", quality=82)
                raw.unlink(missing_ok=True)
            paths.append(dst)
        except Exception:  # noqa: BLE001 — bir şəkil turu dayandırmır
            paths.append(None)
    return paths


def assess(photos: list, story: _story.Story, post: str, run_id: str,
           agents: list | None = None) -> tuple[list[Assessment], bool]:
    """Model hər faylı açıb qiymətləndirir. Qaytarır: (qiymətlər, none_suitable)."""
    thumbs = thumbnails(photos, run_id)
    listing = []
    for i, (photo, path) in enumerate(zip(photos, thumbs)):
        listing.append({
            "index": i,
            "file": str(path.resolve()) if path else None,
            "caption": (photo.caption or "")[:200],
            "source_page": photo.page_url, "provider": photo.provider,
            "creator": photo.photographer, "license": photo.license or "platform",
            "date": getattr(photo, "date", "") or "naməlum",
        })
    payload = json.dumps({
        "brief": _story.brief_text(story, post), "post": post[:900],
        "candidates": listing,
        "instruction": "Read EVERY candidate file first, then answer.",
    }, ensure_ascii=False, indent=2)
    result = llm.call_agent(
        "photo_inspector",
        (config.PROMPTS_DIR / "photo_inspector.md").read_text(encoding="utf-8"),
        payload, model=config.MODEL_INSPECT,
        tools="Read", schema=INSPECT_SCHEMA, timeout=300, retries=1,
    )
    if agents is not None:
        agents.append({"name": result.name, "model": result.model, "ok": result.ok,
                       "total_tokens": result.total_tokens, "cost_usd": result.cost_usd,
                       "duration_ms": result.duration_ms, "error": result.error})
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(f"müfəttiş uğursuz: {result.error}")
    by_index = {}
    for row in result.data.get("assessments", []) or []:
        a = Assessment.from_dict(row)
        if 0 <= a.index < len(photos):
            by_index[a.index] = a
    out = []
    for i, path in enumerate(thumbs):
        a = by_index.get(i) or Assessment(index=i, note="model bu şəkli qiymətləndirmədi")
        if path is None:
            a = Assessment(index=i, clarity=0, note="önizləmə alınmadı")
        out.append(a)
    return out, bool(result.data.get("none_suitable"))


# --- seçim (kiçik dəst → lazım olsa genişlən) ------------------------------

def name_hits(photo: stock.Photo, story: _story.Story) -> int:
    """Təsvirdə TAM ad (bütün sözləri) keçən subyekt sayı.

    Tək soyad kifayət deyil: Pixabay «paprika, yellow, huang» şəklini
    «Jensen Huang» sayırdı (15.09.2026 dry run). Təşkilat adı tək sözdürsə
    o, olduğu kimi axtarılır (Nvidia).
    """
    have = stock._terms(photo.caption) | {w for w in re.findall(r"[a-z0-9\-]{2,}", (photo.caption or "").lower())}
    hits = 0
    # Şəxs təşkilatdan ağırdır: hekayədə insan varsa, loqo kontekstdir
    for weight, names in ((2, story.people), (1, story.organizations + story.products)):
        for name in names:
            words = [w for w in re.findall(r"[a-z0-9\-]{2,}", name.lower())]
            if words and all(w in have for w in words):
                hits += weight
    return hits


def _pre_rank(photos: list, story: _story.Story) -> list:
    """Ucuz ilkin sıra: subyekt adı təsvirdə olan öndə, kənar obyekt arxada."""
    banned = _story.peripheral_terms(story)

    def rank(p):
        have = stock._terms(p.caption)
        # Şəxssiz hekayədə ad uyğunluğu ZƏRƏRLİDİR: «Meta» → «meta
        # information» teqi, «Apple» → alma (16.09.2026: metasequoia
        # ağacları data mərkəzi fotolarını sıradan çıxardı). Səhnə balı qalır.
        hit = name_hits(p, story) if story.people else 0
        periph = 1 if (have & banned and not hit) else 0
        return (-hit, periph, -p.score)
    return sorted(photos, key=rank)


def select(photos: list, story: _story.Story, post: str, run_id: str,
           agents: list | None = None, want: int = 2,
           expand: "callable | None" = None) -> tuple[list[Decision], list[Decision]]:
    """Kiçik dəstə bax; kifayət etməsə `expand()` ilə genişlən (bir dəfə).

    Qaytarır: (qəbul edilənlər — HAMISI, sıralı; rədd edilənlər). Göstərmək
    üçün `want` qədəri götürülür, kollaj isə hamısına baxa bilir.
    """
    accepted: list[Decision] = []
    rejected: list[Decision] = []
    seen: set[str] = set()
    # Lisenziyası naməlum namizəd (məqalə şəkli) yayımlana bilməz — onu
    # modelə göstərmək boş xərcdir. Hesabatda qalır: istifadəçi tədbirin
    # əsl fotosunun mənbədə OLDUĞUNU görür və linkə gedə bilər.
    for p in photos:
        if not licensed(p):
            seen.add(p.key)
            rejected.append(Decision(
                photo=p, accepted=False, image_type="rejected",
                reasons=["lisenziya təsdiqlənməyib — yayım üçün istifadə olunmur (baxılmadı)"],
                relevance="", uncertainty="mənbədə tədbir fotosu ola bilər — linkə baxın",
                source_page=p.page_url, date=getattr(p, "date", "") or "",
                attribution=p.credit, license=p.license or ""))
    pool = _pre_rank([p for p in photos if p.key not in seen], story)
    for round_no in range(2):
        batch = [p for p in pool if p.key not in seen][:INSPECT_MAX]
        if not batch:
            break
        seen.update(p.key for p in batch)
        assessments, _none = assess(batch, story, post, f"{run_id}/r{round_no}", agents)
        for photo, a in zip(batch, assessments):
            d = decide(photo, a, story)
            (accepted if d.accepted else rejected).append(d)
        order = {"event": 0, "archive": 1, "contextual": 2}
        accepted.sort(key=lambda d: (order.get(d.image_type, 9), -d.photo.score))
        if len(accepted) >= want or expand is None or round_no == 1:
            break
        more = expand() or []
        # Xərc nəzarəti: 2-ci turda YALNIZ subyekt adı daşıyan namizədlərə
        # baxılır — «huangshan dağı» və «paprika» üçün model çağırılmır.
        # Şəxssiz (mövzu) hekayədə ad uyğunluğu yoxdur — səhnə fotoları keçir
        pool = _pre_rank([p for p in more if p.key not in seen
                          and (not story.people or name_hits(p, story)
                               or p.provider in ("Məqalə", "keş"))], story)
    return accepted, rejected


# --- məqalə şəkilləri (og:image) ------------------------------------------

_OG = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG_ALT = re.compile(r'<meta[^>]+property=["\']og:image:alt["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_PUB = re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']', re.I)


def article_images(urls: list, limit: int = 3) -> list:
    """Məqalənin sosial önizləmə şəkli — NAMİZƏDDİR, sübut deyil.

    Lisenziya naməlumdur (`license=""`, provayder «Məqalə») → qaydalar onu
    yayım üçün rədd edir, amma müfəttiş hesabatında görünür: istifadəçi
    tədbirin əsl fotosunun mövcud olduğunu bilir və mənbəyə gedə bilər.
    """
    out = []
    for url in urls[:limit]:
        try:
            html = net.fetch_text(url, timeout=15)
        except Exception:  # noqa: BLE001
            continue
        m = _OG.search(html)
        if not m:
            continue
        alt = _OG_ALT.search(html)
        pub = _PUB.search(html)
        photo = stock.Photo(
            url=m.group(1), provider="Məqalə", photographer=url.split("/")[2],
            page_url=url, license="", caption=(alt.group(1) if alt else "") or "",
        )
        photo.date = (pub.group(1)[:10] if pub else "")
        out.append(photo)
    return out


# --- Wikimedia Commons metadatası -----------------------------------------

def commons_enrich(photo: stock.Photo) -> stock.Photo:
    """Openverse-dən gələn Commons şəklinə tarix/təsvir/müəllif əlavə edir."""
    m = re.search(r"commons\.wikimedia\.org/w/index\.php\?curid=(\d+)", photo.page_url or "")
    if not m:
        return photo
    try:
        raw = net.fetch(
            "https://commons.wikimedia.org/w/api.php?action=query&format=json"
            f"&pageids={m.group(1)}&prop=imageinfo&iiprop=extmetadata", timeout=15)
        pages = json.loads(raw.decode("utf-8")).get("query", {}).get("pages", {})
        info = next(iter(pages.values())).get("imageinfo", [{}])[0].get("extmetadata", {})
    except Exception:  # noqa: BLE001
        return photo
    def _v(key):
        return re.sub(r"<[^>]+>", "", str(info.get(key, {}).get("value", ""))).strip()
    photo.date = (_v("DateTimeOriginal") or _v("DateTime"))[:10]
    desc = _v("ImageDescription")
    if desc:
        photo.caption = f"{photo.caption} — {desc[:300]}".strip(" —")
    if _v("Artist"):
        photo.photographer = _v("Artist")[:80]
    lic = _v("LicenseShortName")
    if lic:
        photo.license = lic.lower().replace("cc ", "").replace(" ", "-")
    return photo


# --- təsdiqlənmiş aktivlərin keşi ------------------------------------------

ASSETS = config.STATE_DIR / "assets.json"


def cached_assets(story: _story.Story) -> list:
    """Əvvəl təsdiqlənmiş, eyni subyektə aid aktivlər (mənbə ilə birlikdə)."""
    from .. import store

    rows = (store.read_json(ASSETS, {}) or {}).get("assets", [])
    names = {n.lower() for n in story.people + story.organizations}
    out = []
    for row in rows:
        if names & {s.lower() for s in row.get("subjects", [])}:
            p = stock.Photo(url=row["url"], provider=row.get("provider", ""),
                            photographer=row.get("creator", ""), page_url=row.get("page_url", ""),
                            width=row.get("width", 0), height=row.get("height", 0),
                            license=row.get("license", ""), caption=row.get("caption", ""))
            p.date = row.get("date", "")
            p.score = 2.0                  # keş öndə gəlir
            out.append(p)
    return out


def remember_asset(decision: Decision, story: _story.Story, used_in: str) -> None:
    """Təsdiqlənmiş şəkli mənbə və istifadə məlumatı ilə saxlayır."""
    from .. import store

    data = store.read_json(ASSETS, {}) or {}
    rows = data.get("assets", [])
    p = decision.photo
    for row in rows:
        if row.get("page_url") == p.page_url:
            row.setdefault("used_in", []).append(used_in)
            break
    else:
        rows.append({
            "url": p.url, "page_url": p.page_url, "provider": p.provider,
            "creator": p.photographer, "license": p.license, "caption": p.caption,
            "width": p.width, "height": p.height, "date": getattr(p, "date", ""),
            "subjects": story.people + story.organizations,
            "image_type": decision.image_type, "approved_at": datetime.now().isoformat(),
            "used_in": [used_in],
        })
    store.write_json(ASSETS, {"assets": rows[-200:]})

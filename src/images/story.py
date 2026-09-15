"""Hekayəni anlamaq → vizual brif → axtarış sorğuları.

Şəkil axtarışından ƏVVƏL post «kim, nə, harada, nə vaxt» səviyyəsində
başa düşülməlidir. 15.09.2026: Tramp–Huang zəngi haqqında posta sistem
«telefon» şəkli seçdi — açar söz uyğun gəlirdi, hekayə yox.

Direktor (`prompts/visual_director.md`) `story` blokunu doldurur; bu
modul onu yoxlayır (tədbir yalnız mənbə təsdiqləyəndə «təsdiqlənmiş»
sayılır), sorğuları QURUR (iştirakçılar → təşkilat → tədbir → səhnə) və
kənar obyektləri («telephone») sorğudan kənarda saxlayır.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

KINDS = ("news", "product", "research", "comparison", "explainer")

# Hekayənin mərkəzində olmayan, amma mətndə keçən obyektlər. Bunlar
# sorğuya düşməməlidir — stok kitabxana məhz onları «tapır».
PERIPHERAL_DEFAULT = (
    "telephone", "phone", "smartphone", "call", "laptop", "screen", "keyboard",
    "microphone", "podium", "stage", "office", "handshake", "desk",
)

# Şəxs/təşkilat sorğusuna qoşulan kontekst sözləri — hekayə növünə görə.
PERSON_CONTEXT = {
    "news": ("speech", "press conference", "portrait"),
    "product": ("keynote", "presentation", "portrait"),
    "research": ("portrait", "lecture"),
    "comparison": ("portrait",),
    "explainer": ("portrait",),
}
ORG_CONTEXT = ("logo", "headquarters", "building")


@dataclass
class Story:
    kind: str = "news"
    people: list = field(default_factory=list)
    organizations: list = field(default_factory=list)
    products: list = field(default_factory=list)
    action: str = ""
    event_name: str = ""
    event_location: str = ""
    event_date: str = ""            # ISO tarix, yalnız təsdiqlənibsə dolu
    event_confirmed: bool = False
    must_show: str = ""             # şəkil nəyi çatdırmalıdır
    irrelevant: list = field(default_factory=list)   # nə uyğun DEYİL
    source_urls: list = field(default_factory=list)  # məqalə/rəsmi mənbə

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_list(values) -> list:
    out: list = []
    for v in values or []:
        v = str(v or "").strip()
        if v and v.lower() not in {x.lower() for x in out}:
            out.append(v)
    return out


GENERIC_EVENT_WORDS = {"summit", "conference", "event", "forum", "expo", "keynote",
                       "meeting", "session", "congress", "festival", "day", "week"}


def _confirmed_in(text: str, needle: str) -> bool:
    """Tədbir adı mənbə mətnində keçirmi — fərqləndirici hissə ilə.

    Tədqiqat mətni azərbaycancadır: «All-In konfransında» — «Summit» sözü
    orada olmur. Ona görə ümumi sözlər («summit», «conference») atılır,
    qalan hissə («all-in») ifadə kimi axtarılır.
    """
    if not needle or not text:
        return False
    low = text.lower()
    core = " ".join(w for w in re.findall(r"[A-Za-z0-9\-]+", needle.lower())
                    if w not in GENERIC_EVENT_WORDS)
    if not core:
        return False

    def whole(word: str) -> bool:
        return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", low) is not None

    if whole(core):
        return True
    # Ehtiyat: adın hər fərqləndirici sözü (≥4 hərf) bütöv söz kimi keçsin.
    # «all» → «called» kimi alt-sətir uyğunluğu təsdiq sayılmır.
    words = [w for w in re.findall(r"[a-z0-9]+", core) if len(w) >= 4]
    return bool(words) and all(whole(w) for w in words)


def _source_text(research: dict | None) -> str:
    if not research:
        return ""
    parts = [research.get("headline", ""), research.get("summary", "")]
    for fact in research.get("facts", []) or []:
        parts.append(str(fact.get("claim", "")))
    for quote in research.get("quotes", []) or []:
        parts.append(str(quote.get("text", quote) if isinstance(quote, dict) else quote))
    return " ".join(p for p in parts if p)


def _source_urls(research: dict | None) -> list:
    if not research:
        return []
    urls = [research.get("primary_source_url", "")]
    for fact in research.get("facts", []) or []:
        urls.append(fact.get("source_url", ""))
    return _clean_list(u for u in urls if str(u).startswith("http"))


def from_director(director: dict, research: dict | None = None) -> Story:
    """Direktorun `story` blokunu Story-yə çevirir və mənbə ilə YOXLAYIR.

    Tədbir adı/tarixi yalnız tədqiqat mətnində keçəndə `event_confirmed`
    olur — model «All-In Summit» deyə bilər, mənbə isə deməyə bilər.
    """
    raw = director.get("story") or {}
    kind = str(raw.get("kind") or "news").lower()
    if kind not in KINDS:
        kind = "news"
    event = raw.get("event") or {}
    name = str(event.get("name") or "").strip()
    text = _source_text(research)
    confirmed = bool(name) and (_confirmed_in(text, name) if text else bool(event.get("confirmed")))
    date = str(event.get("date") or "").strip() if confirmed else ""
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        date = ""
    irrelevant = _clean_list(raw.get("irrelevant") or [])
    return Story(
        kind=kind,
        people=_clean_list(raw.get("people")),
        organizations=_clean_list(raw.get("organizations")),
        products=_clean_list(raw.get("products")),
        action=str(raw.get("action") or "").strip(),
        event_name=name if confirmed else "",
        event_location=str(event.get("location") or "").strip() if confirmed else "",
        event_date=date,
        event_confirmed=confirmed,
        must_show=str(raw.get("must_show") or "").strip(),
        irrelevant=irrelevant,
        source_urls=_source_urls(research),
    )


def peripheral_terms(story: Story) -> set[str]:
    """Sorğuya və sıralamaya düşməməli sözlər (kiçik hərflə)."""
    terms = {t.lower() for t in PERIPHERAL_DEFAULT}
    for phrase in story.irrelevant:
        for w in re.findall(r"[a-z]{3,}", phrase.lower()):
            terms.add(w)
    # Hekayənin öz subyektləri heç vaxt «kənar» sayılmır
    for name in story.people + story.organizations + story.products:
        for w in re.findall(r"[a-z]{3,}", name.lower()):
            terms.discard(w)
    return terms


def queries(story: Story, extra: list | None = None, limit: int = 8) -> list[str]:
    """Axtarış sorğuları — ƏHƏMİYYƏT sırası ilə, kənar obyektlərsiz.

    1) tədbir (yalnız təsdiqlənibsə) və iştirakçılar birlikdə
    2) hər iştirakçı ayrıca (+ kontekst)
    3) təşkilat/məhsul (+ kontekst)
    4) direktorun öz səhnə sorğuları — kənar obyekt daşımırsa
    """
    out: list[str] = []
    ctx = PERSON_CONTEXT.get(story.kind, PERSON_CONTEXT["news"])
    year = story.event_date[:4] if story.event_date else ""
    if story.event_confirmed and story.event_name:
        who = " ".join(story.people[:1])
        out.append(" ".join(x for x in (who, story.event_name, year) if x).strip())
    if len(story.people) >= 2:
        out.append(f"{story.people[0]} {story.people[1]}")
    # Portret hər şəxs üçün BİRİNCİ — kontekst fotosu və kollaj üçün lazımdır;
    # tanınmış şəxslərin portretləri Wikimedia-da demək olar həmişə var.
    for person in story.people[:3]:
        out.append(f"{person} portrait")
    for org in story.organizations[:2]:
        out.append(f"{org} {ORG_CONTEXT[0]}")
    for product in story.products[:1]:
        out.append(f"{product} product")
    for person in story.people[:2]:
        if ctx[0] != "portrait":
            out.append(f"{person} {ctx[0]}")
    banned = peripheral_terms(story)
    for q in extra or []:
        words = set(re.findall(r"[a-z]{3,}", q.lower()))
        if words & banned and not words & {w for n in story.people + story.organizations
                                            for w in re.findall(r"[a-z]{3,}", n.lower())}:
            continue                      # «man holding smartphone» — kənar obyekt
        out.append(q)
    return _clean_list(out)[:limit]


def brief_text(story: Story, post: str = "") -> str:
    """Müfəttiş üçün oxunaqlı brif."""
    lines = [f"Növ: {story.kind}"]
    if story.people:
        lines.append("Şəxslər: " + ", ".join(story.people))
    if story.organizations:
        lines.append("Təşkilatlar: " + ", ".join(story.organizations))
    if story.products:
        lines.append("Məhsul/model: " + ", ".join(story.products))
    if story.action:
        lines.append("Hadisə: " + story.action)
    if story.event_confirmed:
        lines.append(f"Tədbir (mənbə təsdiqləyir): {story.event_name} · "
                     f"{story.event_location or '?'} · {story.event_date or 'tarix yoxdur'}")
    else:
        lines.append("Tədbir: mənbə təsdiqləmir — tədbir adı ilə iddia YOXDUR")
    if story.must_show:
        lines.append("Şəkil çatdırmalıdır: " + story.must_show)
    if story.irrelevant:
        lines.append("Uyğun DEYİL: " + ", ".join(story.irrelevant))
    return "\n".join(lines)

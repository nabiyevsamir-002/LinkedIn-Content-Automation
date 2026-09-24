"""RSS/Atom mənbələri — paralel çəkilir, normallaşdırılır, süzülür.

Xarici asılılıq yoxdur: yalnız stdlib. Bütün feed-lər əl ilə test edilib.
`weight` çarpaz təsdiq balında istifadə olunur; `primary=True` olan mənbələr
şirkətin öz elanıdır, ona görə fakt etibarlılığı ən yüksəkdir.

Mənbələr iki yola bölünür: `region="global"` (dünya AI/texnologiya
mətbuatı) və `region="local"` (Azərbaycan və yaxın region). Scout-a gedən
pəncərə hər iki yol arasında bölünür — bax `pipeline._clusters_payload`.
"""
from __future__ import annotations

import concurrent.futures
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from . import config, net


@dataclass
class Feed:
    key: str
    name: str
    url: str
    weight: float = 0.8
    primary: bool = False      # şirkətin öz rəsmi elanı
    topic: str = "none"        # "none" | "ai" | "az_tech" — hansı açar söz filtri
    region: str = "global"     # "global" | "local" (Azərbaycan və yaxın region)


# --- Qlobal mətbuat ---------------------------------------------------
# 24.09.2026: siyahı 9-dan 18-ə qaldırıldı. Səbəb ölçülmüş idi — köhnə
# dəstin yarısı vendor bloqu və TechCrunch idi, ona görə Scout-a gələn
# namizədlərin əksəriyyəti «növbəti versiya çıxdı» tipində olurdu.
# Bunlar LinkedIn-də ölü mövzudur. Əlavə edilən mənbələr məhz sahibinin
# istədiyi xəbər növünü gətirir: münaqişə (404 Media, BBC), pul və
# sızma (The Information), istifadəçiyə toxunan dəyişiklik (Verge,
# WIRED), və inkişaf etməkdə olan bazarlar (Rest of World) — sonuncu
# Azərbaycan konteksti üçün ən yaxşı körpüdür.
GLOBAL_FEEDS: list[Feed] = [
    Feed("rundown", "The Rundown AI", "https://www.therundown.ai/feed", 1.0),
    Feed("techcrunch", "TechCrunch AI",
         "https://techcrunch.com/category/artificial-intelligence/feed/", 0.8),
    Feed("arstechnica", "Ars Technica AI", "https://arstechnica.com/ai/feed/", 0.85),
    Feed("mit_tr", "MIT Tech Review", "https://www.technologyreview.com/feed/",
         0.8, topic="ai"),
    Feed("verge", "The Verge AI",
         "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 0.85),
    Feed("wired", "WIRED AI", "https://www.wired.com/feed/tag/ai/latest/rss", 0.85),
    Feed("decoder", "The Decoder", "https://the-decoder.com/feed/", 0.8),
    # Skup mənbəyi: ödənişli, amma başlıq və anons açıqdır — Researcher
    # faktı onsuz da başqa nəşrdən təsdiqləyir.
    Feed("theinformation", "The Information", "https://www.theinformation.com/feed",
         0.9, topic="ai"),
    # Aqreqator: müstəqil nəşr deyil, amma «bu gün sahə nəyi danışır»
    # siqnalını verir və klasterləri gücləndirir.
    Feed("techmeme", "Techmeme", "https://www.techmeme.com/feed.xml", 0.75, topic="ai"),
    Feed("fourzerofour", "404 Media", "https://www.404media.co/rss/", 0.8, topic="ai"),
    Feed("restofworld", "Rest of World", "https://restofworld.org/feed/latest/",
         0.8, topic="ai"),
    Feed("bbc_tech", "BBC Technology",
         "https://feeds.bbci.co.uk/news/technology/rss.xml", 0.75, topic="ai"),
    Feed("githubblog", "GitHub Blog", "https://github.blog/feed/", 0.7, topic="ai"),
    Feed("openai", "OpenAI", "https://openai.com/news/rss.xml", 1.0, primary=True),
    Feed("googleai", "Google AI", "https://blog.google/technology/ai/rss/",
         0.95, primary=True),
    Feed("deepmind", "Google DeepMind", "https://deepmind.google/blog/rss.xml",
         0.95, primary=True),
    Feed("hn", "Hacker News", "https://hnrss.org/frontpage?points=150",
         0.7, topic="ai"),
    Feed("simonw", "Simon Willison", "https://simonwillison.net/atom/everything/",
         0.75, topic="ai"),
]

# --- Yerli və regional mətbuat ----------------------------------------
# Burada bir neçə şey qlobaldan fərqlidir və kod bunu bilməlidir:
#  1. Ümumi xəbər saytlarında texnologiya payı ~5%-dir → `az_tech` filtri.
#  2. Yerli nəşrlər bir-birini təkrar etmir → çarpaz təsdiq balı həmişə
#     aşağı olur; ona görə Scout pəncərəsində ayrıca kvota var.
#  3. InfoCity hər xəbəri həm azərbaycanca, həm rusca verir → kiril
#     nüsxələr atılır (bax `_is_cyrillic`), yoxsa siyahı ikiqat olur.
LOCAL_FEEDS: list[Feed] = [
    # Yeganə tam texnologiya yönümlü yerli nəşr — filtrə ehtiyacı yoxdur.
    Feed("infocity", "InfoCity", "https://infocity.az/feed/", 0.75, region="local"),
    Feed("report_az", "Report.az", "https://report.az/rss", 0.7,
         topic="az_tech", region="local"),
    Feed("apa_az", "APA", "https://apa.az/rss", 0.7, topic="az_tech", region="local"),
    Feed("trend_az", "Trend.az", "https://az.trend.az/feeds/index.rss", 0.7,
         topic="az_tech", region="local"),
    Feed("oxu_az", "Oxu.az", "https://oxu.az/feed", 0.6,
         topic="az_tech", region="local"),
    # Bank və fintex rəqəmsallaşması — auditoriyanın işlədiyi sahə.
    Feed("banker_az", "Banker.az", "https://banker.az/feed", 0.6,
         topic="az_tech", region="local"),
    Feed("azernews", "AzerNews", "https://www.azernews.az/rss/", 0.65,
         topic="az_tech", region="local"),
    # Türkiyə ekosistemi: yerli komandalar üçün ən yaxın müqayisə nöqtəsi.
    Feed("webrazzi", "Webrazzi (TR)", "https://webrazzi.com/kategori/yapay-zeka/feed",
         0.6, region="local"),
]

FEEDS: list[Feed] = GLOBAL_FEEDS + LOCAL_FEEDS

AI_KEYWORDS = (
    "ai", "artificial intelligence", "llm", "gpt", "claude", "gemini", "openai",
    "anthropic", "deepmind", "machine learning", "neural", "model", "agent",
    "chatbot", "transformer", "inference", "benchmark", "diffusion", "copilot",
    "mistral", "llama", "nvidia", "training", "dataset", "prompt",
)

# Azərbaycan mətnində axtarılan KÖKLƏR — şəkilçi sərbəstdir («startap» →
# «startaplara», «rəqəmsal» → «rəqəmsallaşma»), ona görə yalnız sözün
# əvvəli yoxlanılır.
#
# Qısa və çoxmənalı sözlər QƏSDƏN yoxdur. 24.09.2026-da yerli lentlər
# üzərində ölçüldü: «proqram» televiziya proqramını, «model» moda
# modelini, «meta» metallurgiyanı, «tətbiq» isə istənilən qərarın
# «tətbiq olunması»nı içəri buraxırdı — filtr işləmirmiş kimi görünürdü.
AZ_TECH_KEYWORDS = (
    # süni intellekt
    "süni intellekt", "süni zəka", "maşın öyrənmə", "neyron şəbəkə",
    "dil modeli", "generativ", "alqoritm",
    # sahə, peşə, ekosistem
    "texnologiya", "texnoloji", "rəqəmsal", "innovasiya", "startap",
    "texnopark", "proqram təminat", "proqramlaşdır", "proqramçı",
    "developer", "kodlaşdır", "it sahə", "it sektor", "it şirkət",
    "it mütəxəssis", "ikt sektor", "ikt sahə",
    # infrastruktur
    "kibertəhlükəsizlik", "kiberhücum", "kibercinayət", "kibermüdafiə",
    "data mərkəz", "məlumat mərkəzi", "telekommunikasiya", "internet",
    "server", "bulud xidmət", "bulud texnologiya", "yarımkeçirici",
    "prosessor", "avtomatlaşdır", "robot", "smartfon", "kompüter", "5g",
    # dövlət və pul
    "elektron xidmət", "e-xidmət", "elektron hökumət", "e-hökumət",
    "fintex", "fintech", "kriptovalyuta", "blokçeyn", "bitkoin",
    # qlobal adlar yerli mətndə olduğu kimi yazılır
    "openai", "chatgpt", "anthropic", "claude", "gemini", "deepmind",
    "deepseek", "nvidia", "microsoft", "google", "huawei", "qualcomm",
    "tiktok", "youtube", "starlink", "copilot", "grok",
    # ingiliscə yazan yerli nəşrlər (AzerNews) üçün
    "startup", "digital", "technology", "cyber", "software", "semiconductor",
)

# İngiliscə açar sözlərin hamısı azərbaycanca mətndə işlək deyil:
# «model» moda modelini, «agent» isə sığorta agentini tutur — ölçüldü
# 24.09.2026, «Məşhur model televizor ustasına ərə getməyə hazırdır»
# filtrdən keçirdi. Yerli lentlərdə yalnız birmənalı olanlar axtarılır.
# «ai» də buradadır, amma başqa səbəbdən — aşağıdakı `_AI_ACRONYM`-a bax.
_AZ_AMBIGUOUS_EN = ("model", "agent", "ai")
AZ_SAFE_EN_KEYWORDS = tuple(k for k in AI_KEYWORDS if k not in _AZ_AMBIGUOUS_EN)


@dataclass
class Item:
    source: str
    source_name: str
    weight: float
    primary: bool
    title: str
    link: str
    summary: str
    published: datetime | None
    categories: list[str] = field(default_factory=list)
    region: str = "global"

    def age_hours(self, now: datetime | None = None) -> float:
        if not self.published:
            return 999.0
        now = now or datetime.now(timezone.utc)
        return (now - self.published).total_seconds() / 3600.0


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _text(el) -> str:
    if el is None:
        return ""
    raw = "".join(el.itertext())
    raw = re.sub(r"(?s)<[^>]+>", " ", html.unescape(raw))
    return re.sub(r"\s+", " ", raw).strip()


def _parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fetch(url: str) -> bytes:
    return net.fetch(url)


def _parse_feed(feed: Feed, blob: bytes) -> list[Item]:
    root = ElementTree.fromstring(blob)
    items: list[Item] = []

    for node in root.iter():
        tag = _strip_ns(node.tag)
        if tag not in ("item", "entry"):
            continue

        title = link = summary = published_raw = ""
        categories: list[str] = []

        for child in node:
            ctag = _strip_ns(child.tag)
            if ctag == "title" and not title:
                title = _text(child)
            elif ctag == "link":
                # RSS: mətn içində; Atom: href atributunda
                href = child.get("href")
                rel = child.get("rel", "alternate")
                if href and rel == "alternate" and not link:
                    link = href
                elif not href and not link:
                    link = _text(child)
            elif ctag in ("description", "summary", "content") and not summary:
                summary = _text(child)[:600]
            elif ctag in ("pubDate", "published", "updated") and not published_raw:
                published_raw = (child.text or "").strip()
            elif ctag == "category":
                label = child.get("term") or _text(child)
                if label:
                    categories.append(label)

        if not title or not link:
            continue

        items.append(Item(
            source=feed.key, source_name=feed.name, weight=feed.weight,
            primary=feed.primary, title=title, link=link.strip(),
            summary=summary, published=_parse_date(published_raw),
            categories=categories[:6], region=feed.region,
        ))
    return items


# Söz sərhədi üçün hərf sinifləri. İngiliscə açar sözlər hər iki tərəfdən
# bağlıdır («model» → «models» tutmur); Azərbaycan kökləri isə yalnız
# soldan, çünki dil şəkilçi yığır.
_EN_EDGE = "a-z"
_AZ_EDGE = "a-z0-9əğıöüşç"

# Üç və daha çox ardıcıl kiril hərfi = rusdilli söz. Bir-iki hərf
# ingiliscə məhsul adının yanında təsadüfən düşə bilər.
_CYRILLIC_WORD = re.compile(r"[\u0400-\u04FF]{3,}")

# «AI» XAM mətndə, böyük hərflə axtarılır. Səbəb: azərbaycanca Avropa
# İttifaqı «Aİ» kimi yazılır və kiçiləndə hər ikisi «ai» olur — 24.09.2026
# «Baltik ölkələri dronlarla mübarizə üçün Aİ-dən 500 milyon avro istəyib»
# süni intellekt xəbəri kimi filtrdən keçirdi.
_AI_ACRONYM = re.compile(r"(?<![A-Za-zƏĞIİÖÜŞÇəğıiöüşç])AI(?![A-Za-zƏĞIİÖÜŞÇəğıiöüşç])")


def _fold(text: str) -> str:
    """Azərbaycan hərfləri üçün təhlükəsiz kiçiltmə.

    Python-da «İ».lower() hərfin altında birləşən nöqtə saxlayır
    («i» + U+0307), ona görə «İKT» heç vaxt «ikt» ilə uyğun gəlmir.
    Burada yalnız bu hərf düzəldilir.

    «I» hərfinə toxunmuruq: azərbaycanca onun kiçiyi «ı»dır, amma yerli
    lentlərdə ingiliscə adlar da var və «OpenAI» → «openaı» çevrilməsi
    ən vacib açar sözü sındırırdı (ölçüldü 24.09.2026).
    """
    return text.replace("İ", "i").lower()


def _haystack(item: Item) -> str:
    return _fold(f"{item.title} {item.summary} {' '.join(item.categories)}")


def _is_cyrillic(text: str) -> bool:
    """Başlıqda rusdilli söz varmı.

    InfoCity eyni xəbəri azərbaycanca və rusca ayrıca yayımlayır. Rus
    nüsxəsi başqa başlıqdır, ona görə klasterləşmə onu birləşdirmir və
    siyahı ikiqat görünür — sahibi isə azərbaycanca yazır.

    Pay hesablamırıq: «Motorola Signature 27 – первый флагман на базе
    Snapdragon» başlığında latın hərfləri çoxluqdadır, amma cümlə rusdur.
    """
    return bool(_CYRILLIC_WORD.search(text))


def _is_ai_related(item: Item) -> bool:
    haystack = _haystack(item)
    return any(
        re.search(rf"(?<![{_EN_EDGE}]){re.escape(kw)}(?![{_EN_EDGE}])", haystack)
        for kw in AI_KEYWORDS
    )


def _is_az_tech_related(item: Item) -> bool:
    """Yerli ümumi lentdə texnologiya xəbəri varmı.

    İngiliscə açar sözlərin birmənalı olanları da sayılır: yerli mətndə
    məhsul və şirkət adları («OpenAI», «ChatGPT») olduğu kimi yazılır.
    """
    if _AI_ACRONYM.search(f"{item.title} {item.summary}"):
        return True
    haystack = _haystack(item)
    if any(re.search(rf"(?<![{_EN_EDGE}]){re.escape(kw)}(?![{_EN_EDGE}])", haystack)
           for kw in AZ_SAFE_EN_KEYWORDS):
        return True
    return any(
        re.search(rf"(?<![{_AZ_EDGE}]){re.escape(_fold(kw))}", haystack)
        for kw in AZ_TECH_KEYWORDS
    )


_TOPIC_FILTERS = {"ai": _is_ai_related, "az_tech": _is_az_tech_related}


def passes_topic(item: Item) -> bool:
    """Xəbər öz mənbəsinin mövzu filtrindən keçirmi."""
    feed = _feed_by_key(item.source)
    if feed.region == "local" and _is_cyrillic(item.title):
        return False
    check = _TOPIC_FILTERS.get(feed.topic)
    return check(item) if check else True


def fetch_all(
    feeds: list[Feed] | None = None,
    max_age_hours: int | None = None,
    as_of: datetime | None = None,
) -> tuple[list[Item], list[tuple[str, str]]]:
    """Bütün feed-ləri paralel çəkir.

    Qaytarır: (xəbərlər, xətalar). Bir mənbə sınsa qalanları işləyir —
    tək nöqtəli asılılıq yoxdur.
    """
    feeds = feeds or FEEDS
    max_age_hours = max_age_hours or config.MAX_ITEM_AGE_HOURS
    now = as_of or datetime.now(timezone.utc)

    items: list[Item] = []
    errors: list[tuple[str, str]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        futures = {pool.submit(_fetch, f.url): f for f in feeds}
        for future in concurrent.futures.as_completed(futures):
            feed = futures[future]
            try:
                items.extend(_parse_feed(feed, future.result()))
            except Exception as exc:  # noqa: BLE001 - bir mənbə axını dayandırmır
                errors.append((feed.name, f"{type(exc).__name__}: {exc}"))

    fresh = [
        it for it in items
        if it.age_hours(now) <= max_age_hours and passes_topic(it)
    ]
    fresh.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
               reverse=True)
    return fresh, errors


_FEED_INDEX = {f.key: f for f in FEEDS}


def _feed_by_key(key: str) -> Feed:
    return _FEED_INDEX.get(key, Feed(key, key, "", 0.7))


def feeds_by_region(region: str) -> list[Feed]:
    return [f for f in FEEDS if f.region == region]

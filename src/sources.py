"""RSS/Atom mənbələri — paralel çəkilir, normallaşdırılır, süzülür.

Xarici asılılıq yoxdur: yalnız stdlib. Bütün feed-lər əl ilə test edilib.
`weight` çarpaz təsdiq balında istifadə olunur; `primary=True` olan mənbələr
şirkətin öz elanıdır, ona görə fakt etibarlılığı ən yüksəkdir.
"""
from __future__ import annotations

import concurrent.futures
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    ai_filter: bool = False    # feed AI-spesifik deyil → açar sözlə süzülür


FEEDS: list[Feed] = [
    Feed("rundown", "The Rundown AI", "https://www.therundown.ai/feed", 1.0),
    Feed("techcrunch", "TechCrunch AI",
         "https://techcrunch.com/category/artificial-intelligence/feed/", 0.8),
    Feed("arstechnica", "Ars Technica AI", "https://arstechnica.com/ai/feed/", 0.85),
    Feed("mit_tr", "MIT Tech Review", "https://www.technologyreview.com/feed/",
         0.8, ai_filter=True),
    Feed("openai", "OpenAI", "https://openai.com/news/rss.xml", 1.0, primary=True),
    Feed("googleai", "Google AI", "https://blog.google/technology/ai/rss/",
         0.95, primary=True),
    Feed("deepmind", "Google DeepMind", "https://deepmind.google/blog/rss.xml",
         0.95, primary=True),
    Feed("hn", "Hacker News", "https://hnrss.org/frontpage?points=150",
         0.7, ai_filter=True),
    Feed("simonw", "Simon Willison", "https://simonwillison.net/atom/everything/",
         0.75, ai_filter=True),
]

AI_KEYWORDS = (
    "ai", "artificial intelligence", "llm", "gpt", "claude", "gemini", "openai",
    "anthropic", "deepmind", "machine learning", "neural", "model", "agent",
    "chatbot", "transformer", "inference", "benchmark", "diffusion", "copilot",
    "mistral", "llama", "nvidia", "training", "dataset", "prompt",
)


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
            categories=categories[:6],
        ))
    return items


def _is_ai_related(item: Item) -> bool:
    haystack = f"{item.title} {item.summary} {' '.join(item.categories)}".lower()
    return any(
        re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", haystack)
        for kw in AI_KEYWORDS
    )


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
        if it.age_hours(now) <= max_age_hours
        and (not _feed_by_key(it.source).ai_filter or _is_ai_related(it))
    ]
    fresh.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
               reverse=True)
    return fresh, errors


_FEED_INDEX = {f.key: f for f in FEEDS}


def _feed_by_key(key: str) -> Feed:
    return _FEED_INDEX.get(key, Feed(key, key, "", 0.7))

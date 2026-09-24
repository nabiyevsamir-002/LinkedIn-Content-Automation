"""Çarpaz mənbə təsdiqi.

Eyni hadisəni bir neçə mənbə yazıbsa, o hadisə obyektiv olaraq daha
önəmlidir — bu, LLM-in "maraqlıdır" hökmündən daha etibarlı siqnaldır.
Şirkətin öz elanı (primary) klasterdə varsa, faktlar ilk mənbədən
təsdiqlənə bilər deməkdir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .sources import Item

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with", "from", "into", "onto",
    "its", "it", "is", "are", "was", "were", "be", "been", "being", "to", "of",
    "in", "on", "at", "by", "as", "that", "this", "these", "those", "new", "now",
    "how", "why", "what", "who", "will", "can", "may", "says", "said", "your",
    "you", "his", "her", "their", "our", "more", "most", "than", "then", "just",
    "about", "after", "before", "over", "under", "out", "up", "down", "not",
    # Azərbaycanca köməkçi sözlər. Bunlarsız yerli başlıqlar məzmuna görə
    # yox, «üçün olub edib» kimi sözlərə görə birləşirdi.
    "üçün", "ilə", "olan", "olub", "olur", "olacaq", "olaraq", "edib", "edir",
    "edilib", "edəcək", "verib", "alıb", "görə", "kimi", "deyil", "var",
    "yox", "sonra", "əvvəl", "haqqında", "arasında", "barədə", "qeyd",
    "hansı", "niyə", "necə", "artıq", "yeni", "ilk", "son", "çox", "bütün",
    "həm", "amma", "isə", "daha", "bir", "bəzi", "özü", "onun", "bunu",
    "məlum", "xəbər", "açıqlama", "bildirib", "deyib", "təsdiqləyib",
}

KNOWN_ENTITIES = {
    "openai", "anthropic", "google", "deepmind", "meta", "microsoft", "nvidia",
    "apple", "amazon", "mistral", "cohere", "perplexity", "xai", "tesla",
    "claude", "gpt", "gemini", "llama", "grok", "sora", "copilot", "chatgpt",
    "huggingface", "stability", "midjourney", "figure", "waymo", "databricks",
}

# Press-reliz/CSR başlıqlarının tipik izləri
PR_MARKERS = (
    "supporting", "partnership", "partnering", "we're excited", "introducing our",
    "our commitment", "initiative", "celebrating", "announcing our", "welcome to",
    "joins forces", "collaboration with", "empowering", "investing in",
    "expands access", "brings ai to", "for good", "pledge",
)

# Azərbaycan hərfləri də daxildir: onlarsız «Rəqəmsallaşma» sözü «q»
# hərfindən kəsilib mənasız parçalara düşürdü və yerli başlıqlar
# təsadüfi şəkildə bir-birinə oxşayırdı.
_AZ_UPPER = "ƏĞIİÖÜŞÇ"
_AZ_LOWER = "əğıiöüşç"
_WORD = re.compile(rf"[a-zA-Z{_AZ_UPPER}{_AZ_LOWER}][a-zA-Z0-9{_AZ_UPPER}{_AZ_LOWER}\-']+")


def _tokens(text: str) -> set[str]:
    return {
        w.lower() for w in _WORD.findall(text)
        if len(w) >= 3 and w.lower() not in STOPWORDS
    }


def _entities(text: str) -> set[str]:
    found = {w.lower() for w in _WORD.findall(text) if w[:1].isupper() and len(w) > 2}
    found |= {w for w in _tokens(text) if w in KNOWN_ENTITIES}
    return found - STOPWORDS


def _similarity(a: Item, b: Item) -> float:
    ta, tb = _tokens(a.title), _tokens(b.title)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    shared_entities = len(_entities(a.title) & _entities(b.title))
    if shared_entities >= 2 and jaccard >= 0.18:
        return max(jaccard, 0.34)
    return jaccard + (0.06 * shared_entities)


@dataclass
class Cluster:
    items: list[Item] = field(default_factory=list)

    @property
    def lead(self) -> Item:
        """Klasteri təmsil edən xəbər — əvvəlcə rəsmi mənbə, sonra çəki."""
        return sorted(
            self.items, key=lambda i: (i.primary, i.weight, -i.age_hours()), reverse=True
        )[0]

    @property
    def sources(self) -> list[str]:
        seen, out = set(), []
        for it in self.items:
            if it.source not in seen:
                seen.add(it.source)
                out.append(it.source_name)
        return out

    @property
    def looks_like_pr(self) -> bool:
        """Korporativ elan/CSR mətni — xəbər deyil, press-reliz."""
        title = self.lead.title.lower()
        return any(k in title for k in PR_MARKERS)

    @property
    def has_primary(self) -> bool:
        return any(i.primary for i in self.items)

    @property
    def region(self) -> str:
        """Yalnız yerli mənbələr yazıbsa — yerli hadisə.

        Qlobal nəşr də yazıbsa hadisə qlobaldır: yerli lent sadəcə onu
        tərcümə edib. Bu fərq Scout pəncərəsindəki kvota üçün lazımdır.
        """
        return ("local" if self.items and all(i.region == "local" for i in self.items)
                else "global")

    @property
    def local_coverage(self) -> bool:
        """Yerli mətbuat da bu hadisəni yazıbmı.

        Qlobal xəbər üçün güclü siqnaldır: mövzunun yerli oxucuya maraqlı
        olduğu artıq sübut olunub.
        """
        return any(i.region == "local" for i in self.items)

    @property
    def score(self) -> float:
        """Çarpaz təsdiq balı — mənbə sayı, çəkisi, rəsmiliyi, təzəliyi."""
        by_source: dict[str, float] = {}
        for it in self.items:
            by_source[it.source] = max(by_source.get(it.source, 0.0), it.weight)
        base = sum(by_source.values())
        if len(by_source) >= 3:
            base += 1.2          # üç müstəqil mənbə = güclü siqnal
        elif len(by_source) == 2:
            base += 0.5
        if self.has_primary:
            # Rəsmi mənbə yalnız jurnalist əhatəsi ilə birlikdə güclü siqnaldır.
            # Tək başına vendor bloqu məhsul marketinqidir — jurnalist yazana
            # qədər xəbər deyil. 15.09.2026: Google bloqunun «DevFest is back»
            # və astronavt videosu siyahının başında idi (1.53), günün əsl
            # xəbərləri (0.8-0.85 çəkili nəşrlər) onların altında.
            base += 0.8 if len(by_source) >= 2 else -0.3
        if self.looks_like_pr and len(by_source) < 2:
            base -= 0.9          # heç kim yazmayıbsa, yəqin xəbər dəyəri yoxdur
        base += max(0.0, 1.0 - self.lead.age_hours() / 48.0) * 0.5
        return round(base, 3)


def build(items: list[Item], threshold: float = 0.32) -> list[Cluster]:
    """Xəbərləri hadisələr üzrə qruplaşdırır (acgöz klasterləşdirmə)."""
    clusters: list[Cluster] = []
    for item in items:
        placed = False
        for cluster in clusters:
            if any(_similarity(item, member) >= threshold for member in cluster.items):
                cluster.items.append(item)
                placed = True
                break
        if not placed:
            clusters.append(Cluster(items=[item]))
    clusters.sort(key=lambda c: c.score, reverse=True)
    return clusters

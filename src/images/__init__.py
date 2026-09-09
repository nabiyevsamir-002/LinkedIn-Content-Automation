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

from .. import config, llm
from . import aigen, render, stock
from . import schemas as vschemas


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
            "duration_ms": result.duration_ms, "error": result.error,
        })
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(f"Visual Director uğursuz: {result.error}")
    return enforce_unit_safety(recover_tagged_fields(result.data))


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
            "duration_ms": result.duration_ms, "error": result.error,
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


def plan(director: dict) -> list[tuple[str, object]]:
    """Vizual növünə görə pillə sırasını qurur."""
    kind = (director.get("visual_type") or "card").lower()
    claude_rungs = [("claude", VARIANT_PRIMARY), ("claude", VARIANT_ALT)]
    photo_count = 6 if kind == "photo" else 4
    photo_rungs = [("pexels", i) for i in range(photo_count)] if stock.available() else []
    ai_rungs = [("aigen", None)] if aigen.available() else []

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


def photo_queries(director: dict) -> list:
    """Direktorun foto sorğuları — 3 səviyyə, ehtiyat variantları ilə."""
    queries = [q for q in (director.get("photo_queries") or []) if q]
    if not queries and director.get("pexels_query"):
        queries = [director["pexels_query"]]          # köhnə formatla uyğunluq
    if not queries and director.get("_fallback_query"):
        queries = [director["_fallback_query"]]
    return queries or ["technology abstract"]


def _photo_cache(query, post: str = "", agents: list | None = None) -> list:
    """Axtarır və modelə ən uyğunları seçdirir.

    Söz üst-üstə düşməsi zəif göstəricidir — əşya metaforaları etiket
    sıx olduğu üçün insanlı səhnələri sıxışdırır. Model isə şəklin
    hekayəyə yaraşıb-yaraşmadığını həqiqətən qiymətləndirir.
    """
    key = " | ".join(query) if isinstance(query, list) else query
    if key in _PHOTO_MEMO:
        return _PHOTO_MEMO[key]

    found = stock.search(query, limit=14)
    if post and len(found) > 3:
        try:
            ranked = stock.pick_best(found, post, count=6, agents=agents)
            # Seçilməyənlər sıranın sonuna qalır — «başqa şəkil» üçün
            rest = [p for p in found if p not in ranked]
            found = ranked + rest
        except Exception:  # noqa: BLE001 — seçim sınsa sıralama qalır
            pass
    _PHOTO_MEMO[key] = found
    return found


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

"""Boru kəməri: Scout → Researcher → Writer → Reviewer → Reviser.

Hər addımın telemetriyası (token, xərc, müddət) toplanır və qaçış
faylına yazılır — kvota istifadəsini təxmin etmirik, ölçürük.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import cluster, config, filters, llm, schemas, sources, state


def _prompt(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _enforce_primary_source(comment: str, primary_url: str, fallback_url: str) -> str:
    """Birinci şərh mütləq ilkin mənbəyə istinad etməlidir.

    Model bəzən aggregator/scraper saytı seçir. Bu, həm etibarlılığı,
    həm də istinad etikasını zədələyir — ona görə deterministik düzəldilir.
    """
    import re as _re

    target = (primary_url or fallback_url or "").strip()
    if not target:
        return comment
    urls = _re.findall(r"https?://\S+", comment or "")
    if not urls:
        return f"{(comment or '').strip()} {target}".strip()
    if any(u.rstrip(".,)").rstrip("/") == target.rstrip("/") for u in urls):
        return comment
    for u in urls:
        comment = comment.replace(u, target)
    return comment


def _performance_hint() -> dict:
    """Keçmiş postların real nəticəsi — Writer üçün siqnal.

    LinkedIn API statistikanı vermir; rəqəmləri istifadəçi özü yazır.
    Üç postdan az məlumat varsa siqnal göndərmirik — təsadüfi nəticəyə
    əsaslanıb üslubu dəyişmək zərərlidir.
    """
    try:
        from . import publisher

        report = publisher.performance_report()
    except Exception:  # noqa: BLE001
        return {}
    if report.get("samples", 0) < 3:
        return {}
    return {
        "note": ("Bunlar müəllifin öz postlarının REAL nəticəsidir. "
                 "Yaxşı işləyən rakursa üstünlük ver, amma mövzuya "
                 "uyğun gəlmirsə məcbur etmə."),
        "best_angles": report["by_angle"][:3],
        "best_pillars": report["by_pillar"][:3],
    }


def _positioning() -> str:
    """Müəllifin mövqe sənədi — yerli bağlantının həqiqi olması üçün."""
    path = config.PROMPTS_DIR / "positioning.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _voice_guide(style: str | None = None) -> str:
    guide = _prompt("voice_guide")
    if style:
        path = config.PROMPTS_DIR / "styles" / f"{style}.md"
        if path.exists():
            guide += "\n\n" + path.read_text(encoding="utf-8")
    return guide


@dataclass
class RunResult:
    run_id: str
    ok: bool
    post: str = ""
    first_comment: str = ""
    hashtags: list = field(default_factory=list)
    angles: list = field(default_factory=list)
    chosen_angle_id: int | None = None
    scores: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)
    research: dict = field(default_factory=dict)
    chosen: dict = field(default_factory=dict)
    cliche_draft: list = field(default_factory=list)
    cliche_final: list = field(default_factory=list)
    agents: list = field(default_factory=list)
    error: str = ""
    style: str | None = None

    @property
    def total_tokens(self) -> int:
        return sum(a.get("total_tokens", 0) for a in self.agents)

    @property
    def total_cost(self) -> float:
        return round(sum(a.get("cost_usd", 0.0) for a in self.agents), 4)


# Klasterlər ingiliscə gəlir və Scout bəzən həmin dildə cavab verir —
# istifadəçi Telegram-da ingiliscə namizədlər görür. Ölçüldü (15.09.2026):
# 6 təklif dəstindən 4-ü ingiliscə idi, promptda dil qaydası yox idi.
# Bu hərflər ingiliscədə olmur; 1-2 cümləlik azərbaycanca mətndə isə
# demək olar həmişə var.
_AZ_LETTERS = re.compile(r"[əğıöüşçƏĞİÖÜŞÇ]")
SCOUT_LANG_WARNING = ("Scout ingiliscə cavab verdi — promptdakı dil qaydasına "
                      "əməl etmədi")


def candidates_in_azerbaijani(candidates: list) -> bool:
    """Hər namizədin `why` sahəsi azərbaycancadırmı.

    `title` yoxlanmır — o, məhsul adlarından ibarət ola bilər
    («GPT-6 Astra»). `why` isə həmişə tam cümlədir.
    """
    texts = [str(c.get("why") or "") for c in candidates]
    return bool(texts) and all(_AZ_LETTERS.search(t) for t in texts)


def _track(result: llm.AgentResult, bucket: list) -> llm.AgentResult:
    if result.total_tokens > config.TOKEN_WARN_THRESHOLD:
        print(f"  ⚠ «{result.name}» {result.total_tokens:,} token yedi "
              f"(hədd {config.TOKEN_WARN_THRESHOLD:,}) — büdcəni yoxlayın", flush=True)
    bucket.append({
        "name": result.name, "model": result.model, "ok": result.ok,
        "total_tokens": result.total_tokens, "cost_usd": result.cost_usd,
        "duration_ms": result.duration_ms, "usage": result.usage,
        "error": result.error,
    })
    return result


def collect(max_age_hours: int | None = None) -> tuple[list[sources.Item], list, list]:
    """Xəbərləri çəkir, görülmüşləri atır, hadisələr üzrə klasterləşdirir."""
    items, errors = sources.fetch_all(max_age_hours=max_age_hours)
    fresh = [i for i in items if not state.is_seen(i.link)]
    return fresh, cluster.build(fresh), errors


_STUB_MARKERS = ("test claim", "n/a", "placeholder", "example claim",
                 "məlum deyil", "nümunə")


def _research_quality_issue(data: dict) -> str:
    """Tədqiqat nəticəsinin real olub-olmadığını yoxlayır.

    Agent tur həddinə çatanda sxemi doldurmaq üçün süni fakt yaza bilir.
    Belə nəticə ilə yazılan post uydurma olur — ona görə axını dayandırırıq.
    """
    facts = data.get("facts") or []
    if not facts:
        return "heç bir fakt tapılmadı"
    stubs = [f for f in facts
             if any(m in str(f.get("claim", "")).lower() for m in _STUB_MARKERS)]
    if stubs:
        return f"doldurucu fakt aşkarlandı («{stubs[0].get('claim', '')[:40]}»)"
    if len(facts) < 2 and not data.get("numbers"):
        return f"yalnız {len(facts)} fakt, rəqəm yoxdur"
    if not str(data.get("primary_source_url") or "").startswith("http"):
        return "ilkin mənbə tapılmadı"
    return ""


# Scout yalnız bu qədər klaster görür. 12 idi — 15.09.2026-da 28 klasterin
# ən maraqlıları (agentlər həmkarlarını ələ verdi, Microsoft-un AI davranış
# kodeksi, RubyGems boşluğu) 12-dən kənarda qaldı və heç vaxt seçilə
# bilmədi. Hər klaster ~120 token — 24 klaster ~3k token, post 90k-dır.
SCOUT_WINDOW = 24


def _clusters_payload(clusters: list[cluster.Cluster],
                      limit: int = SCOUT_WINDOW) -> list[dict]:
    payload = []
    for idx, c in enumerate(clusters[:limit]):
        lead = c.lead
        payload.append({
            "cluster_id": idx,
            "title": lead.title,
            "summary": lead.summary[:280],
            "link": lead.link,
            "sources": c.sources,
            "has_official_source": c.has_primary,
            "cross_source_score": c.score,
            "looks_like_pr": c.looks_like_pr,
            "age_hours": round(lead.age_hours(), 1),
        })
    return payload


def run(
    *,
    style: str | None = None,
    max_age_hours: int | None = None,
    cluster_override: int | None = None,
    preloaded: tuple | None = None,
    verbose: bool = True,
    chosen_candidate: dict | None = None,
) -> RunResult:
    """Tam axın.

    `chosen_candidate` verilibsə Scout addımı ATLANIR — mövzu artıq
    seçilib (istifadəçi Telegram-dan seçib). Bu, qaçış başına ~20k
    token qənaət edir.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    agents: list = []
    started = datetime.now(timezone.utc)

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    # --- 0. Xəbərlər ---------------------------------------------------
    if preloaded:
        items, clusters, errors = preloaded
    else:
        log("→ 9 mənbədən xəbərlər çəkilir…")
        items, clusters, errors = collect(max_age_hours)
    for name, err in errors:
        log(f"  ⚠ {name}: {err[:70]}")
    log(f"  {len(items)} yeni xəbər → {len(clusters)} hadisə klasteri")

    def snapshot(err: str = "") -> None:
        """Xəbərləri diskə yazır ki, axın yarıda sınsa belə `replay` işləsin."""
        state.record_run(run_id, {
            "run_id": run_id, "started_at": started.isoformat(),
            "prompt_version": config.PROMPT_VERSION, "style": style,
            "feed_errors": errors, "partial": True, "error": err,
            "items": [
                {"source": i.source, "title": i.title, "link": i.link,
                 "summary": i.summary,
                 "published": i.published.isoformat() if i.published else None}
                for i in items
            ],
            "agents": agents,
        })

    if not clusters:
        snapshot("Yeni xəbər tapılmadı")
        return RunResult(run_id=run_id, ok=False, error="Yeni xəbər tapılmadı")

    snapshot()
    result = RunResult(run_id=run_id, ok=False, style=style, agents=agents)

    # --- 1. Scout (mövzu artıq seçilibsə atlanır) ----------------------
    if chosen_candidate:
        log(f"→ Scout atlandı — mövzu seçilib: «{chosen_candidate.get('title','')[:50]}»")
        candidates = [chosen_candidate]
        scout = llm.AgentResult(name="scout", ok=True, model="(atlandı)",
                                data={"candidates": candidates})
    else:
        candidates = None
    if candidates is None:
        log(f"→ Scout ({config.MODEL_SCOUT}): {len(clusters)} klasterdən 3 namizəd seçir…")
        scout_input = {
            "clusters": _clusters_payload(clusters),
            "pillars": config.PILLARS,
            "pillar_balance_last_14_days": state.pillar_balance(),
            "recent_theses": [t["thesis"] for t in state.theses(12)],
            "author_positioning": _positioning(),
        }
        scout = _track(llm.call_agent(
            "scout", _prompt("scout"),
            json.dumps(scout_input, ensure_ascii=False, indent=2),
            model=config.MODEL_SCOUT, schema=schemas.SCOUT,
        ), agents)
        if not scout.ok or not isinstance(scout.data, dict):
            result.error = f"Scout uğursuz: {scout.error}"
            snapshot(result.error)
            return result
        candidates = scout.data.get("candidates") or []
        if candidates and not candidates_in_azerbaijani(candidates):
            log(f"  ⚠ {SCOUT_LANG_WARNING}")
    if not candidates:
        result.error = f"Scout uyğun mövzu tapmadı: {scout.data.get('skip_reason')}"
        snapshot(result.error)
        return result

    chosen = candidates[0]
    if cluster_override is not None:
        match = next((c for c in candidates if c.get("cluster_id") == cluster_override), None)
        chosen = match or {"cluster_id": cluster_override, "pillar": "tooling",
                           "title": clusters[cluster_override].lead.title, "why": "əl ilə seçildi"}
    cid = int(chosen.get("cluster_id", 0))
    cid = cid if 0 <= cid < len(clusters) else 0
    lead = clusters[cid].lead
    result.chosen = {**chosen, "link": lead.link, "sources": clusters[cid].sources}
    log(f"  ✓ «{chosen.get('title', lead.title)[:60]}» [{chosen.get('pillar')}]")

    # --- 2. Researcher (web alətləri ilə) ------------------------------
    log(f"→ Researcher ({config.MODEL_MAIN}): ilkin mənbə axtarılır…")
    research_input = json.dumps({
        "title": lead.title,
        "link": lead.link,
        "summary": lead.summary,
        "sources_covering_it": clusters[cid].sources,
        "official_source_in_cluster": clusters[cid].has_primary,
        "why_selected": chosen.get("why", ""),
    }, ensure_ascii=False, indent=2)
    research = _track(llm.call_agent(
        "researcher", _prompt("researcher"), research_input,
        tools="WebSearch,WebFetch", timeout=900, schema=schemas.RESEARCHER,
        budget_usd=config.RESEARCH_BUDGET_USD, max_turns=config.RESEARCH_MAX_TURNS,
    ), agents)
    if not research.ok or not isinstance(research.data, dict):
        result.error = f"Researcher uğursuz: {research.error}"
        snapshot(result.error)
        return result
    result.research = research.data      # snapshot-a düşsün — uğursuzluq da izlənilsin
    problem = _research_quality_issue(research.data)
    if problem:
        # Faktsız post yazmaq faktla yazmamaqdan pisdir — burada dayanırıq.
        # 16.09.2026: «ilkin mənbə tapılmadı» — amma snapshot-da tədqiqat
        # boş idi, səbəbi sonradan görmək mümkün olmadı (dərs 11).
        result.error = f"Tədqiqat keyfiyyətsizdir: {problem}"
        log(f"  ✗ {result.error}")
        snapshot(result.error)
        return result
    log(f"  ✓ {len(research.data.get('facts', []))} fakt, "
        f"{len(research.data.get('numbers', []))} rəqəm, "
        f"ilkin mənbə: {str(research.data.get('primary_source_url', ''))[:50]}")

    # --- 3. Writer -----------------------------------------------------
    log(f"→ Writer ({config.MODEL_MAIN}): 5 rakurs + post…")
    writer_input = json.dumps({
        "research": research.data,
        "pillar": chosen.get("pillar"),
        "local_angle_hint": chosen.get("local_angle_potential", ""),
        "source_link": lead.link,
        "recent_theses_do_not_repeat": [t["thesis"] for t in state.theses(15)],
        "voice_guide": _voice_guide(style),
        "positioning": _positioning(),
        "what_worked_before": _performance_hint(),
    }, ensure_ascii=False, indent=2)
    draft = _track(llm.call_agent(
        "writer", _prompt("writer"), writer_input, timeout=600, schema=schemas.WRITER,
    ), agents)
    if not draft.ok or not isinstance(draft.data, dict):
        result.error = f"Writer uğursuz: {draft.error}"
        snapshot(result.error)
        return result

    post = draft.data.get("post", "")
    result.angles = draft.data.get("angles", [])
    result.chosen_angle_id = draft.data.get("chosen_angle_id")
    result.first_comment = draft.data.get("first_comment", "")
    # Hashtag siyahısı post mətnindən götürülür — iki yerdə fərqli
    # siyahı olması LinkedIn-də uyğunsuzluq yaradır.
    import re as _re
    in_post = _re.findall(r"(?<!\w)#\w+", post)
    result.hashtags = in_post or draft.data.get("hashtags", [])
    result.cliche_draft = [asdict(f) for f in filters.check(post)]
    log(f"  ✓ {len(result.angles)} rakurs, seçilən #{result.chosen_angle_id}, "
        f"{len(post)} simvol, klişe: {filters.summary(filters.check(post))}")

    # --- 4. Reviewer ---------------------------------------------------
    log(f"→ Reviewer ({config.MODEL_MAIN}): fakt + skeptik + risk…")
    review_input = json.dumps({
        "post": post,
        "first_comment": result.first_comment,
        "research": research.data,
        "deterministic_cliche_flags": result.cliche_draft,
    }, ensure_ascii=False, indent=2)
    review = _track(llm.call_agent(
        "reviewer", _prompt("reviewer"), review_input, timeout=600, schema=schemas.REVIEWER,
    ), agents)
    if review.ok and isinstance(review.data, dict):
        result.review = review.data
        result.scores = review.data.get("scores", {})
        must_fix = review.data.get("must_fix") or []
        log(f"  ✓ ümumi bal {result.scores.get('overall', '?')}/10, "
            f"tövsiyə: {review.data.get('publish_recommendation')}, "
            f"{len(must_fix)} düzəliş")
    else:
        must_fix = []
        log(f"  ⚠ Reviewer uğursuz ({review.error}) — qaralama saxlanılır")

    # --- 5. Reviser (yalnız lazım olduqda) -----------------------------
    # Deterministik bayraqlar müzakirə mövzusu deyil — məcburi düzəlişlərə çevrilir.
    mandatory = [
        f"[{f['kind']}] {f['detail']}" for f in result.cliche_draft
    ]
    must_fix = list(must_fix) + mandatory
    needs_revision = bool(must_fix)
    if needs_revision:
        log(f"→ Reviser ({config.MODEL_MAIN}): {len(must_fix)} düzəliş + səs qoruyucusu…")
        revise_input = json.dumps({
            "post": post,
            "first_comment": result.first_comment,
            "must_fix": must_fix,
            "reviewer_report": result.review,
            "deterministic_cliche_flags": result.cliche_draft,
            "voice_guide": _voice_guide(style),
        }, ensure_ascii=False, indent=2)
        revised = _track(llm.call_agent(
            "reviser", _prompt("reviser"), revise_input, timeout=600, schema=schemas.REVISER,
        ), agents)
        if revised.ok and isinstance(revised.data, dict) and revised.data.get("post"):
            post = revised.data["post"]
            result.first_comment = revised.data.get("first_comment") or result.first_comment
            result.review["revision"] = {
                "changes": revised.data.get("changes", []),
                "rejected_fixes": revised.data.get("rejected_fixes", []),
                "voice_preserved": revised.data.get("voice_preserved"),
                "voice_note": revised.data.get("voice_note", ""),
            }
            log(f"  ✓ {len(revised.data.get('changes', []))} dəyişiklik, "
                f"səs qorunub: {revised.data.get('voice_preserved')}")
        else:
            log(f"  ⚠ Reviser uğursuz ({revised.error}) — qaralama saxlanılır")
    else:
        log("→ Reviser: atlandı (düzəliş tələb olunmur) — bir çağırış qənaət")

    result.post = post
    result.first_comment = _enforce_primary_source(
        result.first_comment,
        (result.research or {}).get("primary_source_url", ""),
        lead.link,
    )
    result.cliche_final = [asdict(f) for f in filters.check(post)]
    result.ok = bool(post)
    if result.cliche_final:
        log(f"  ⚠ düzəlişdən sonra qalan bayraqlar: "
            f"{filters.summary([filters.Flag(**f) for f in result.cliche_final])}")

    # --- Qeydiyyat -----------------------------------------------------
    state.record_run(run_id, {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "prompt_version": config.PROMPT_VERSION,
        "style": style,
        "feed_errors": errors,
        "items": [
            {"source": i.source, "title": i.title, "link": i.link,
             "summary": i.summary, "published": i.published.isoformat() if i.published else None}
            for i in items
        ],
        "chosen": result.chosen,
        "scout": scout.data,
        "research": result.research,
        "angles": result.angles,
        "chosen_angle_id": result.chosen_angle_id,
        "post": result.post,
        "first_comment": result.first_comment,
        "hashtags": result.hashtags,
        "review": result.review,
        "cliche_draft": result.cliche_draft,
        "cliche_final": result.cliche_final,
        "agents": agents,
    })
    return result


def commit(result: RunResult) -> None:
    """Postu təsdiqləndikdən sonra yaddaşa yazır (təkrar seçilməsin)."""
    link = result.chosen.get("link", "")
    if link:
        state.mark_seen(link, result.chosen.get("title", ""))
    thesis = ""
    for angle in result.angles:
        if angle.get("id") == result.chosen_angle_id:
            thesis = angle.get("thesis", "")
    state.add_thesis(
        thesis=thesis or result.chosen.get("title", ""),
        topic=result.chosen.get("title", ""),
        pillar=result.chosen.get("pillar", "tooling"),
        url=link,
    )


def preload_from_run(run_id: str | None = None) -> tuple:
    """`replay` üçün: köhnə qaçışın xəbərlərini yenidən yükləyir.

    Prompt-u dəyişdikdən sonra sabahı gözləməyə ehtiyac qalmır —
    eyni xəbərlərlə dərhal yenidən qaçırırsınız.
    """
    import json as _json
    from datetime import datetime as _dt

    files = sorted(config.RUNS_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError("Heç bir keçmiş qaçış tapılmadı — əvvəlcə `make run` işlədin.")
    path = (config.RUNS_DIR / f"{run_id}.json") if run_id else files[-1]
    if not path.exists():
        raise FileNotFoundError(f"Qaçış tapılmadı: {path.name}")

    data = _json.loads(path.read_text(encoding="utf-8"))
    items = []
    for row in data.get("items", []):
        feed = sources._feed_by_key(row["source"])
        published = None
        if row.get("published"):
            try:
                published = _dt.fromisoformat(row["published"])
            except ValueError:
                published = None
        items.append(sources.Item(
            source=feed.key, source_name=feed.name, weight=feed.weight,
            primary=feed.primary, title=row["title"], link=row["link"],
            summary=row.get("summary", ""), published=published,
        ))
    return items, cluster.build(items), []


def load_run(run_id: str | None = None) -> dict:
    """Qaçış faylını olduğu kimi qaytarır (şəkil mərhələsi üçün)."""
    import json as _json

    files = sorted(config.RUNS_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError("Heç bir qaçış tapılmadı — əvvəlcə `make run` işlədin.")
    path = (config.RUNS_DIR / f"{run_id}.json") if run_id else files[-1]
    if not path.exists():
        raise FileNotFoundError(f"Qaçış tapılmadı: {path.name}")
    data = _json.loads(path.read_text(encoding="utf-8"))
    if not data.get("post"):
        raise FileNotFoundError(
            f"«{path.stem}» yarımçıq qaçışdır (post yoxdur). "
            "Tam qaçış üçün: make run"
        )
    return data


# --- İstifadəçinin verdiyi linkdən post ------------------------------

def _page_meta(url: str) -> dict:
    """Səhifədən başlıq və qısa təsvir çıxarır (LLM-siz, ucuz)."""
    import html as _html
    import re as _re

    from . import net

    try:
        raw = net.fetch(url, timeout=25).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Səhifə açılmadı: {exc}") from exc

    def meta(prop: str) -> str:
        pattern = (rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]*'
                   rf'content=["\']([^"\']+)["\']')
        m = _re.search(pattern, raw, _re.I)
        if not m:
            pattern = (rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*'
                       rf'(?:property|name)=["\']{prop}["\']')
            m = _re.search(pattern, raw, _re.I)
        return _html.unescape(m.group(1)).strip() if m else ""

    title = meta("og:title")
    if not title:
        m = _re.search(r"<title[^>]*>(.*?)</title>", raw, _re.I | _re.S)
        title = _html.unescape(m.group(1)).strip() if m else url
    return {
        "title": _re.sub(r"\s+", " ", title)[:200],
        "summary": _re.sub(r"\s+", " ", meta("og:description"))[:400],
    }


def run_from_url(url: str, *, style: str | None = None,
                 verbose: bool = True) -> RunResult:
    """İstifadəçinin verdiyi konkret linkdən post hazırlayır.

    Scout addımı atlanır — mövzu artıq seçilib. Qalan agentlər
    (Researcher → Writer → Reviewer → Reviser) adi qaydada işləyir.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    agents: list = []
    started = datetime.now(timezone.utc)
    result = RunResult(run_id=run_id, ok=False, style=style, agents=agents)

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    meta = _page_meta(url)
    log(f"→ Mövzu: «{meta['title'][:60]}»")
    result.chosen = {
        "title": meta["title"], "link": url, "sources": ["əl ilə verilib"],
        "pillar": "tooling", "why": "istifadəçi göndərib",
    }

    log(f"→ Researcher ({config.MODEL_MAIN}): ilkin mənbə axtarılır…")
    research = _track(llm.call_agent(
        "researcher", _prompt("researcher"),
        json.dumps({"title": meta["title"], "link": url,
                    "summary": meta["summary"],
                    "sources_covering_it": [], "official_source_in_cluster": False,
                    "why_selected": "istifadəçi bu linki göndərdi"},
                   ensure_ascii=False, indent=2),
        tools="WebSearch,WebFetch", timeout=900, schema=schemas.RESEARCHER,
        budget_usd=config.RESEARCH_BUDGET_USD, max_turns=config.RESEARCH_MAX_TURNS,
    ), agents)
    if not research.ok or not isinstance(research.data, dict):
        result.error = f"Researcher uğursuz: {research.error}"
        return result
    problem = _research_quality_issue(research.data)
    if problem:
        result.error = f"Tədqiqat keyfiyyətsizdir: {problem}"
        return result
    result.research = research.data

    log(f"→ Writer ({config.MODEL_MAIN}): 5 rakurs + post…")
    draft = _track(llm.call_agent(
        "writer", _prompt("writer"),
        json.dumps({"research": research.data, "pillar": "tooling",
                    "local_angle_hint": "", "source_link": url,
                    "recent_theses_do_not_repeat":
                        [t["thesis"] for t in state.theses(15)],
                    "voice_guide": _voice_guide(style),
                    "positioning": _positioning()},
                   ensure_ascii=False, indent=2),
        timeout=600, schema=schemas.WRITER,
    ), agents)
    if not draft.ok or not isinstance(draft.data, dict):
        result.error = f"Writer uğursuz: {draft.error}"
        return result

    post = draft.data.get("post", "")
    result.angles = draft.data.get("angles", [])
    result.chosen_angle_id = draft.data.get("chosen_angle_id")
    result.first_comment = draft.data.get("first_comment", "")
    result.cliche_draft = [asdict(f) for f in filters.check(post)]

    log(f"→ Reviewer ({config.MODEL_MAIN})…")
    review = _track(llm.call_agent(
        "reviewer", _prompt("reviewer"),
        json.dumps({"post": post, "first_comment": result.first_comment,
                    "research": research.data,
                    "deterministic_cliche_flags": result.cliche_draft},
                   ensure_ascii=False, indent=2),
        timeout=600, schema=schemas.REVIEWER,
    ), agents)
    must_fix = []
    if review.ok and isinstance(review.data, dict):
        result.review = review.data
        result.scores = review.data.get("scores", {})
        must_fix = review.data.get("must_fix") or []

    must_fix = list(must_fix) + [f"[{f['kind']}] {f['detail']}"
                                 for f in result.cliche_draft]
    if must_fix:
        log(f"→ Reviser: {len(must_fix)} düzəliş…")
        revised = _track(llm.call_agent(
            "reviser", _prompt("reviser"),
            json.dumps({"post": post, "first_comment": result.first_comment,
                        "must_fix": must_fix, "reviewer_report": result.review,
                        "deterministic_cliche_flags": result.cliche_draft,
                        "voice_guide": _voice_guide(style)},
                       ensure_ascii=False, indent=2),
            timeout=600, schema=schemas.REVISER,
        ), agents)
        if revised.ok and isinstance(revised.data, dict) and revised.data.get("post"):
            post = revised.data["post"]
            result.first_comment = (revised.data.get("first_comment")
                                    or result.first_comment)

    result.post = post
    result.first_comment = _enforce_primary_source(
        result.first_comment, research.data.get("primary_source_url", ""), url)
    import re as _re
    result.hashtags = _re.findall(r"(?<!\w)#\w+", post)
    result.cliche_final = [asdict(f) for f in filters.check(post)]
    result.ok = bool(post)

    state.record_run(run_id, {
        "run_id": run_id, "started_at": started.isoformat(),
        "prompt_version": config.PROMPT_VERSION, "style": style,
        "source": "manual_topic", "items": [],
        "chosen": result.chosen, "research": result.research,
        "angles": result.angles, "chosen_angle_id": result.chosen_angle_id,
        "post": result.post, "first_comment": result.first_comment,
        "hashtags": result.hashtags, "review": result.review,
        "cliche_draft": result.cliche_draft, "cliche_final": result.cliche_final,
        "agents": agents,
    })
    return result


# --- Mövzu təklifi (post yazılmazdan əvvəl seçim) ---------------------

def propose(max_age_hours: int | None = None, verbose: bool = True) -> dict:
    """Xəbərləri toplayır, Scout-dan 3 namizəd alır və təklif yaradır.

    Post YAZILMIR — bu, ən ucuz mərhələdir (~20k token). Yazı yalnız
    istifadəçi mövzunu seçəndən sonra başlayır.
    """
    from . import proposals

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    log("→ 9 mənbədən xəbərlər çəkilir…")
    items, clusters, errors = collect(max_age_hours)
    for name, err in errors:
        log(f"  ⚠ {name}: {err[:70]}")
    log(f"  {len(items)} yeni xəbər → {len(clusters)} hadisə klasteri")
    if not clusters:
        return {"ok": False, "error": "Yeni xəbər tapılmadı"}

    log(f"→ Scout ({config.MODEL_SCOUT}): 3 namizəd seçir…")
    agents: list = []
    scout = _track(llm.call_agent(
        "scout", _prompt("scout"),
        json.dumps({
            "clusters": _clusters_payload(clusters),
            "pillars": config.PILLARS,
            "pillar_balance_last_14_days": state.pillar_balance(),
            "recent_theses": [t["thesis"] for t in state.theses(12)],
            "author_positioning": _positioning(),
        }, ensure_ascii=False, indent=2),
        model=config.MODEL_SCOUT, schema=schemas.SCOUT,
    ), agents)

    if not scout.ok or not isinstance(scout.data, dict):
        return {"ok": False, "error": f"Scout uğursuz: {scout.error}"}
    candidates = scout.data.get("candidates") or []
    if not candidates:
        return {"ok": False,
                "error": f"Scout uyğun mövzu tapmadı: {scout.data.get('skip_reason')}"}
    # Ehtiyat görünən olmalıdır (dərs 11): dil səhvi səssiz keçməsin —
    # həm konsolda, həm Telegram mesajının özündə görünür.
    warnings = []
    if not candidates_in_azerbaijani(candidates):
        warnings.append(SCOUT_LANG_WARNING)
        log(f"  ⚠ {SCOUT_LANG_WARNING}")

    enriched = _enrich(candidates[:proposals.MAX_CANDIDATES], clusters)

    proposal = proposals.create(enriched, [
        {"source": i.source, "title": i.title, "link": i.link,
         "summary": i.summary,
         "published": i.published.isoformat() if i.published else None}
        for i in items
    ], warnings=warnings)
    log(f"  ✓ {len(enriched)} namizəd · təklif {proposal.id}")
    return {"ok": True, "proposal": proposal, "agents": agents,
            "tokens": sum(a.get("total_tokens", 0) for a in agents)}


def _enrich(candidates: list, clusters: list) -> list:
    """Hər namizədə klasterin linkini və mənbələrini əlavə edir."""
    enriched = []
    for cand in candidates:
        cid = int(cand.get("cluster_id", 0))
        cid = cid if 0 <= cid < len(clusters) else 0
        lead = clusters[cid].lead
        enriched.append({**cand, "link": lead.link,
                         "sources": clusters[cid].sources,
                         "cross_source_score": clusters[cid].score})
    return enriched


def _items_from_proposal(proposal) -> list:
    """Təklifdə saxlanmış xam xəbərləri bərpa edir.

    Klaster indeksləri (`cluster_id`) məhz bu siyahıdan qurulur — ona görə
    təklifə aid HƏR iş (yazı, ehtiyat namizəd) eyni siyahını işlətməlidir;
    təzə RSS çəkilsə indekslər sürüşər və başqa xəbər yazılar.
    """
    from . import sources as _sources

    items = []
    for row in proposal.items:
        feed = _sources._feed_by_key(row["source"])
        published = None
        if row.get("published"):
            try:
                published = datetime.fromisoformat(row["published"])
            except ValueError:
                published = None
        items.append(_sources.Item(
            source=feed.key, source_name=feed.name, weight=feed.weight,
            primary=feed.primary, title=row["title"], link=row["link"],
            summary=row.get("summary", ""), published=published,
        ))
    return items


def propose_more(proposal, agents: list | None = None) -> int:
    """«Başqa xəbər»: ehtiyat bitəndə Scout QALAN klasterlərə baxır.

    Artıq göstərilmiş klasterlər siyahıdan çıxarılır; bu dəfə pəncərə
    məhdud deyil — məqsəd məhz dərinə getməkdir. Yeni namizədlər təklifin
    sonuna əlavə olunur. Qaytarır: neçə namizəd əlavə olundu.
    """
    from . import proposals

    agents = agents if agents is not None else []
    clusters = cluster.build(_items_from_proposal(proposal))
    shown = {cluster_index_for(c, clusters) for c in proposal.candidates}
    payload = [c for c in _clusters_payload(clusters, limit=len(clusters))
               if c["cluster_id"] not in shown]
    if not payload:
        return 0
    scout = _track(llm.call_agent(
        "scout", _prompt("scout"),
        json.dumps({
            "clusters": payload,
            "pillars": config.PILLARS,
            "pillar_balance_last_14_days": state.pillar_balance(),
            "recent_theses": [t["thesis"] for t in state.theses(12)],
            "author_positioning": _positioning(),
            "note": "Bu klasterlər artıq rədd edilənlərdən QALANLARDIR — "
                    "sahibi əvvəlkiləri bəyənmədi, fərqli mövzu axtarır.",
        }, ensure_ascii=False, indent=2),
        model=config.MODEL_SCOUT, schema=schemas.SCOUT,
    ), agents)
    if not scout.ok or not isinstance(scout.data, dict):
        raise RuntimeError(f"Scout uğursuz: {scout.error}")
    fresh = [c for c in (scout.data.get("candidates") or [])
             if int(c.get("cluster_id", -1)) not in shown]
    if not fresh:
        return 0
    if not candidates_in_azerbaijani(fresh) and SCOUT_LANG_WARNING not in proposal.warnings:
        proposal.warnings.append(SCOUT_LANG_WARNING)
    proposal.candidates.extend(_enrich(fresh[:proposals.MAX_CANDIDATES], clusters))
    proposals.save(proposal)
    return len(fresh[:proposals.MAX_CANDIDATES])


def cluster_index_for(candidate: dict, clusters: list) -> int:
    """Namizədin klasterini LİNKLƏ tapır; indeks yalnız ehtiyatdır.

    `cluster_id` mövqe indeksidir və SABİT DEYİL: klaster balı 3 rəqəmə
    yuvarlaqlanır, təzəlik balı isə hər dəqiqə azalır — iki yaxın ballı
    klaster sonradan yerini dəyişə bilir. 15.09.2026: istifadəçi «AI
    botlar» xəbərini seçdi (indeks 1), 23 dəqiqə sonra indeks 1-də
    «Tramp/Huang» dururdu — sistem BAŞQA xəbər yazdı və heç kim görmədi.
    """
    link = (candidate.get("link") or "").strip()
    if link:
        for idx, c in enumerate(clusters):
            if any(item.link == link for item in c.items):
                return idx
    fallback = int(candidate.get("cluster_id", 0))
    return fallback if 0 <= fallback < len(clusters) else 0


def write_from_proposal(proposal, index: int, *, style: str | None = None,
                        verbose: bool = True) -> RunResult:
    """Seçilmiş namizəddən postu yazır (Scout təkrar çağırılmır)."""
    items = _items_from_proposal(proposal)
    clusters = cluster.build(items)
    candidate = dict(proposal.candidates[index])
    cid = cluster_index_for(candidate, clusters)
    candidate["cluster_id"] = cid            # `run` eyni indeksi işlətsin
    return run(style=style, verbose=verbose,
               preloaded=(items, clusters, []),
               cluster_override=cid, chosen_candidate=candidate)

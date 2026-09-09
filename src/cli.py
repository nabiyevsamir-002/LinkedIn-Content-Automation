"""Komanda sətri interfeysi."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

from . import approval, archive, calibration, config, filters, images, linkedin, llm, notify, notion, pipeline, preview, proposals, publisher, smoke, timefmt
from . import queue as pqueue
from . import sources, state, telegram

BOLD, DIM, GREEN, YELLOW, RED, CYAN, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[0m"
)


def _rule(title: str = "") -> str:
    return f"{DIM}{'─' * 4} {title} {'─' * max(0, 66 - len(title))}{RESET}"


def render(result: pipeline.RunResult) -> str:
    if not result.ok:
        return f"{RED}✗ {result.error}{RESET}"

    out = [""]
    label = f"POST{f'  ·  üslub: {result.style}' if result.style else ''}"
    out.append(_rule(label))
    out.append("")
    out.append(preview.render(result.post))
    out.append("")
    if result.first_comment:
        out.append(f"{CYAN}Birinci şərh:{RESET} {result.first_comment}")
    if result.hashtags:
        out.append(f"{CYAN}Hashtag:{RESET} {' '.join(result.hashtags)}")

    stats = preview.stats(result.post)
    out.append("")
    out.append(_rule("ÖLÇÜLƏR"))
    hook_ok = GREEN + "✓" + RESET if stats["hook_chars"] <= config.LINKEDIN_FOLD_CHARS else YELLOW + "!" + RESET
    out.append(f"  uzunluq: {stats['chars']} simvol · {stats['words']} söz    "
               f"hook: {stats['hook_chars']} simvol {hook_ok}")

    if result.scores:
        parts = [f"{k}:{v}" for k, v in result.scores.items()]
        out.append(f"  ballar: {'  '.join(parts)}")
    rec = (result.review or {}).get("publish_recommendation")
    if rec:
        color = GREEN if rec == "publish" else (YELLOW if rec == "revise" else RED)
        out.append(f"  tövsiyə: {color}{rec}{RESET}")

    clich = filters.summary([filters.Flag(**f) for f in result.cliche_final])
    color = GREEN if clich == "təmiz" else YELLOW
    out.append(f"  klişe filtri: {color}{clich}{RESET}")

    skeptic = (result.review or {}).get("skeptic") or {}
    if skeptic:
        out.append(f"  skeptik: dayanma {skeptic.get('stop_scroll')}/10 · "
                   f"şərh yazardı: {skeptic.get('would_comment')}")
        for item in (skeptic.get("cringe") or [])[:3]:
            out.append(f"    {DIM}– {item}{RESET}")

    fc = (result.review or {}).get("fact_check") or {}
    issues = fc.get("issues") or []
    if issues:
        out.append("")
        out.append(f"  {YELLOW}fakt problemləri:{RESET}")
        for issue in issues[:4]:
            out.append(f"    [{issue.get('severity')}] {issue.get('problem', '')[:80]}")

    rev = (result.review or {}).get("revision") or {}
    if rev:
        out.append(f"  səs qorunub: {rev.get('voice_preserved')} — {rev.get('voice_note', '')[:70]}")
        for rejected in (rev.get("rejected_fixes") or [])[:2]:
            out.append(f"    {DIM}rədd edilən düzəliş: {rejected.get('why_rejected', '')[:70]}{RESET}")

    if result.angles:
        out.append("")
        out.append(_rule("RAKURSLAR (Notion-da başqasını seçə biləcəksiniz)"))
        for angle in result.angles:
            mark = f"{GREEN}●{RESET}" if angle.get("id") == result.chosen_angle_id else f"{DIM}○{RESET}"
            out.append(f"  {mark} [{angle.get('strength')}/10] {angle.get('type', ''):12s} "
                       f"{angle.get('headline', '')[:58]}")

    out.append("")
    out.append(_rule("MƏNBƏ"))
    out.append(f"  {result.chosen.get('title', '')[:70]}")
    out.append(f"  {DIM}mənbələr: {', '.join(result.chosen.get('sources', []))}{RESET}")
    primary = result.research.get("primary_source_url", "")
    if primary:
        out.append(f"  {DIM}ilkin mənbə: {primary}{RESET}")

    out.append("")
    out.append(_rule("KVOTA TELEMETRİYASI"))
    for agent in result.agents:
        status = GREEN + "✓" + RESET if agent.get("ok") else RED + "✗" + RESET
        out.append(f"  {status} {agent['name']:11s} {agent.get('model', ''):8s} "
                   f"{agent.get('total_tokens', 0):>8,} token  "
                   f"{agent.get('duration_ms', 0) / 1000:>5.1f}s")
    out.append(f"  {BOLD}CƏMİ: {result.total_tokens:,} token · "
               f"≈${result.total_cost:.4f} API-ekvivalent{RESET}")
    return "\n".join(out)


def save_markdown(result: pipeline.RunResult) -> str:
    path = config.OUT_DIR / f"{result.run_id}{'-' + result.style if result.style else ''}.md"
    lines = [
        f"# {result.chosen.get('title', 'Post')}",
        "",
        f"- Sütun: `{result.chosen.get('pillar')}`",
        f"- Mənbələr: {', '.join(result.chosen.get('sources', []))}",
        f"- İlkin mənbə: {result.research.get('primary_source_url', '—')}",
        f"- Prompt versiyası: `{config.PROMPT_VERSION}`" + (f" · üslub: `{result.style}`" if result.style else ""),
        f"- Token: {result.total_tokens:,} · ≈${result.total_cost:.4f}",
        "",
        "## Post",
        "",
        "```",
        result.post,
        "```",
        "",
        "## Birinci şərh",
        "",
        result.first_comment or "—",
        "",
        "## Rakurslar",
        "",
    ]
    for angle in result.angles:
        mark = "**→**" if angle.get("id") == result.chosen_angle_id else "  "
        lines.append(f"- {mark} `{angle.get('type')}` ({angle.get('strength')}/10) "
                     f"{angle.get('headline')}")
    lines += ["", "## Nəzarətçi hesabatı", "", "```json",
              json.dumps(result.review, ensure_ascii=False, indent=2), "```"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# --- əmrlər -----------------------------------------------------------

def cmd_doctor(_args) -> int:
    ok = True
    print(f"\n{BOLD}Sistem yoxlaması{RESET}\n")
    print(f"  {GREEN}✓{RESET} Python {sys.version.split()[0]}")

    try:
        from . import net
        net.fetch("https://www.therundown.ai/feed", timeout=15)
        print(f"  {GREEN}✓{RESET} HTTPS/SSL sertifikatları")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  {RED}✗{RESET} HTTPS/SSL: {exc}")

    print(f"\n{BOLD}Mənbələr{RESET}\n")
    items, errors = sources.fetch_all(max_age_hours=72)
    from collections import Counter
    counts = Counter(i.source_name for i in items)
    for feed in sources.FEEDS:
        failed = next((e for n, e in errors if n == feed.name), None)
        if failed:
            # Bir mənbənin keçici kəsilməsi sistemi sındırmır — 9 mənbədən
            # ibarət olmasının səbəbi məhz budur. Yalnız yarısı düşsə problemdir.
            print(f"  {YELLOW}✗{RESET} {feed.name:20s} {failed[:50]}")
        else:
            n = counts.get(feed.name, 0)
            mark = GREEN + "✓" + RESET if n else YELLOW + "○" + RESET
            print(f"  {mark} {feed.name:20s} {n:3d} xəbər (72 saat)")

    if len(errors) >= len(sources.FEEDS) / 2:
        ok = False
        print(f"  {RED}✗ mənbələrin yarısından çoxu əlçatmazdır{RESET}")
    elif errors:
        print(f"  {DIM}({len(errors)} mənbə müvəqqəti əlçatmazdır — axın işləyir){RESET}")
    if not items:
        ok = False
        print(f"  {RED}✗ heç bir xəbər alınmadı{RESET}")

    print(f"\n{BOLD}Claude Code (abunəlik){RESET}\n")
    try:
        probe = llm.call_agent(
            "doctor",
            "Sən test agentisən.", "Qısa təsdiq qaytar.",
            model=config.MODEL_SCOUT, expect_json=True, retries=1, timeout=180,
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"]},
        )
        if probe.ok:
            print(f"  {GREEN}✓{RESET} başsız çağırış işləyir ({probe.total_tokens:,} token, "
                  f"{probe.duration_ms / 1000:.1f}s)")
            print(f"  {GREEN}✓{RESET} --system-prompt · --tools \"\" · --json-schema qəbul edilir")
        else:
            ok = False
            print(f"  {RED}✗{RESET} çağırış uğursuz: {probe.error}")
    except llm.NotLoggedIn as exc:
        ok = False
        print(f"  {RED}✗{RESET} {exc}")
        print(f"\n  {YELLOW}Həll:{RESET} terminalda işlədin →  claude setup-token\n")
    except llm.QuotaExhausted as exc:
        ok = False
        print(f"  {YELLOW}!{RESET} kvota limiti: {exc}")

    print(f"\n{BOLD}Şəkil zənciri{RESET}\n")
    from .images import aigen as _aigen, render as _render, stock as _stock
    try:
        chrome = _render.find_chrome()
        print(f"  {GREEN}✓{RESET} Chrome: {pathlib.Path(chrome).name}")
    except _render.RenderError as exc:
        ok = False
        print(f"  {RED}✗{RESET} {exc}")
    fonts = sorted(_render.FONTS_DIR.glob("Inter-*.woff2"))
    if fonts:
        size = sum(f.stat().st_size for f in fonts) / 1024
        print(f"  {GREEN}✓{RESET} Azərbaycan şriftləri: {len(fonts)} çəki ({size:.0f} KB)")
    else:
        ok = False
        print(f"  {RED}✗{RESET} assets/fonts/ boşdur — hərflər kvadrat çıxacaq")
    _active = _stock.active_providers()
    print(f"  {GREEN}✓{RESET} Foto mənbələri: {', '.join(_active)}")
    _missing = [n for n in _stock.KEY_ENV if n not in _active]
    if _missing:
        print(f"  {DIM}  əlavə edilə bilər: {', '.join(_missing)} "
              f"(pulsuz açar){RESET}")
    print(f"  {GREEN + '✓' + RESET if _aigen.available() else YELLOW + '○' + RESET} "
          f"AI generasiya {'aktiv' if _aigen.available() else 'söndürülüb (opsional, ödənişli)'}")

    print(f"\n{BOLD}Telegram{RESET}\n")
    if not config.TELEGRAM_TOKEN:
        print(f"  {YELLOW}○{RESET} TELEGRAM_BOT_TOKEN yoxdur "
              f"{DIM}(@BotFather → /newbot){RESET}")
    else:
        try:
            me = telegram.HttpTransport(config.TELEGRAM_TOKEN).call("getMe", {})
            print(f"  {GREEN}✓{RESET} bot: @{me.get('username')}")
            if config.TELEGRAM_CHAT_ID:
                registered = telegram.Bot().set_commands(approval.COMMAND_CATALOG)
                print(f"  {GREEN + '✓' + RESET if registered else YELLOW + '○' + RESET} "
                      f"{len(approval.COMMAND_CATALOG)} əmr qeydiyyatda "
                      f"{DIM}(«/» yazanda siyahı çıxır){RESET}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  {RED}✗{RESET} token qəbul edilmədi: {str(exc)[:60]}")
    print(f"  {GREEN + '✓' + RESET if config.TELEGRAM_CHAT_ID else YELLOW + '○' + RESET} "
          f"TELEGRAM_CHAT_ID {'var' if config.TELEGRAM_CHAT_ID else 'yoxdur (make tg-chatid)'}")
    _qst = pqueue.stats()
    print(f"  növbə: bank {_qst['bank_size']} · açıq {_qst['open']}")

    print(f"\n{BOLD}Notion{RESET}\n")
    if not notion.token():
        print(f"  {YELLOW}○{RESET} NOTION_TOKEN yoxdur {DIM}(opsional){RESET}")
    else:
        try:
            _pages = notion.accessible_pages(5)
            if not _pages:
                print(f"  {YELLOW}○{RESET} inteqrasiya heç bir səhifə görmür "
                      f"{DIM}(Notion-da: ··· → Connections){RESET}")
            elif notion.available():
                print(f"  {GREEN}✓{RESET} {len(_pages)} obyekt görünür · baza təyin edilib")
            else:
                print(f"  {YELLOW}○{RESET} NOTION_DATABASE_ID yoxdur "
                      f"{DIM}(make notion-setup){RESET}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {YELLOW}○{RESET} Notion əlçatmazdır: {str(exc)[:60]}")

    print(f"\n{BOLD}LinkedIn{RESET}\n")
    _token = linkedin.load_token()
    if not _token:
        print(f"  {YELLOW}○{RESET} giriş edilməyib {DIM}(make li-auth){RESET}")
        if not config.LINKEDIN_CLIENT_ID:
            print(f"  {DIM}  əvvəlcə LinkedIn app yaradın — təlimat: make li-auth{RESET}")
    elif _token.expired:
        ok = False
        print(f"  {RED}✗{RESET} token BİTİB ({_token.expires_dt:%d.%m.%Y}) — make li-auth")
    elif _token.expiring_soon:
        print(f"  {YELLOW}⚠{RESET} token {_token.days_left:.0f} gün sonra bitir "
              f"({_token.expires_dt:%d.%m.%Y}) — make li-auth")
    else:
        print(f"  {GREEN}✓{RESET} {_token.name or 'profil'} · "
              f"token {_token.days_left:.0f} gün qalır")
    if _token and not _token.expired:
        try:
            _ver = linkedin.version_status()
            if not _ver["current_ok"]:
                ok = False
                print(f"  {RED}✗{RESET} API versiyası {_ver['current']} SIRADAN ÇIXIB "
                      f"→ avtomatik {_ver['newest']} işlədiləcək")
            elif _ver["upgrade_available"]:
                print(f"  {YELLOW}⚠{RESET} API versiyası {_ver['current']} işləyir, "
                      f"amma {_ver['newest']} mövcuddur")
            else:
                print(f"  {GREEN}✓{RESET} API versiyası {_ver['current']} (ən yenisi)")
        except Exception as exc:  # noqa: BLE001
            print(f"  {DIM}  versiya yoxlanmadı: {str(exc)[:50]}{RESET}")

    _stuck = publisher.stuck_items()
    if _stuck:
        ok = False
        print(f"  {RED}✗{RESET} {len(_stuck)} yarımçıq yayım — əl ilə yoxlayın")

    print(f"\n{BOLD}Sağlamlıq monitorinqi{RESET}\n")
    if config.HEALTHCHECK_URL:
        if notify.healthcheck():
            print(f"  {GREEN}✓{RESET} healthcheck siqnalı göndərildi")
        else:
            print(f"  {RED}✗{RESET} HEALTHCHECK_URL cavab vermir — URL-i yoxlayın")
    else:
        print(f"  {YELLOW}○{RESET} HEALTHCHECK_URL yoxdur "
              f"{DIM}(healthchecks.io — pulsuz, sistem dayansa xəbər verir){RESET}")
    print(f"  {GREEN + '✓' + RESET if telegram.available() else YELLOW + '○' + RESET} "
          f"Telegram xəta bildirişləri")

    print(f"\n{BOLD}Üslub kalibrləməsi{RESET}\n")
    _cal = calibration.status()
    if _cal["complete"]:
        print(f"  {GREEN}✓{RESET} positioning.md və voice_guide.md doldurulub")
    else:
        for line in calibration.reminder_lines():
            print(f"  {YELLOW}○{RESET} {line}")
        print(f"  {DIM}  bunlarsız voice və local_relevance balları 2-6 arasında qalır{RESET}")

    print(f"\n{BOLD}Yaddaş{RESET}\n")
    print(f"  görülmüş xəbər: {len(state.seen_urls())}")
    print(f"  saxlanan tezis: {len(state.theses(999))}")
    print(f"  sütun balansı (14 gün): {state.pillar_balance()}")
    print(f"\n{GREEN + 'Hər şey hazırdır.' if ok else YELLOW + 'Bəzi problemlər var (yuxarıda).'}{RESET}\n")
    return 0 if ok else 1


def cmd_sources(args) -> int:
    items, errors = sources.fetch_all(max_age_hours=args.age)
    from . import cluster as cl
    clusters = cl.build([i for i in items if not state.is_seen(i.link)])
    print(f"\n{len(items)} xəbər ({args.age} saat) → {len(clusters)} hadisə\n")
    for idx, c in enumerate(clusters[:15]):
        star = f" {GREEN}★rəsmi{RESET}" if c.has_primary else ""
        print(f"  {idx:2d}  {c.score:5.2f}  [{len(c.sources)} mənbə{star}]  {c.lead.title[:58]}")
        if len(c.sources) > 1:
            print(f"      {DIM}└ {', '.join(c.sources)}{RESET}")
    for name, err in errors:
        print(f"  {RED}✗{RESET} {name}: {err[:60]}")
    print()
    return 0


NO_NEWS_EXIT = 5
# Bu əmrlərin uğursuzluğu barədə Telegram-a bildiriş gedir
NOTIFY_COMMANDS = {"run", "send", "poll", "publish", "image", "notion-sync"}


def config_no_news() -> int:
    return NO_NEWS_EXIT
_NO_NEWS_MARKERS = ("Yeni xəbər tapılmadı", "uyğun mövzu tapmadı")


def _execute(preloaded, args, style=None):
    result = pipeline.run(
        style=style or args.style, max_age_hours=getattr(args, "age", None),
        cluster_override=getattr(args, "cluster", None), preloaded=preloaded,
    )
    print(render(result))
    if result.ok:
        _nudge = calibration.reminder_lines()
        if _nudge:
            scores = result.scores or {}
            print(f"\n  {YELLOW}↑ Bu ballar sizin məlumatınız olmadan qalxmır:{RESET} "
                  f"voice {scores.get('voice', '?')}/10 · "
                  f"yerli uyğunluq {scores.get('local_relevance', '?')}/10")
            for line in _nudge:
                print(f"    {DIM}• {line}{RESET}")
        print(f"\n  {DIM}saxlanıldı: {save_markdown(result)}{RESET}")
        if getattr(args, "image", False):
            print()
            _run_image_chain(result)
        if getattr(args, "commit", False):
            pipeline.commit(result)
            print(f"  {GREEN}✓ yaddaşa yazıldı (bu xəbər bir daha seçilməyəcək){RESET}")
        else:
            print(f"  {DIM}qeyd: --commit verilmədi, xəbər yaddaşa yazılmadı{RESET}")
    print()
    if result.ok:
        return 0
    # «Bu gün yaxşı xəbər yoxdur» nasazlıq deyil — bankdan yayımlanacaq.
    if any(marker in (result.error or "") for marker in _NO_NEWS_MARKERS):
        if getattr(args, "notify_empty", False) and telegram.available():
            try:
                telegram.Bot().send_message(
                    "🔕 <b>Bu gün uyğun xəbər tapılmadı.</b>\n"
                    f"<i>{result.error}</i>\n"
                    f"Bankda <b>{len(pqueue.bank())}</b> post var — "
                    "yayım oradan olacaq."
                )
            except Exception:  # noqa: BLE001
                pass
        return NO_NEWS_EXIT
    return 1


def _run_image_chain(result) -> None:
    """Post hazır olandan sonra şəkil zəncirinin birinci pilləsi."""
    agents: list = []
    try:
        director = images.direct(result.post, result.research, agents)
    except Exception as exc:  # noqa: BLE001 — şəkil postu bloklamamalıdır
        print(f"  {YELLOW}! şəkil mərhələsi atlandı: {exc}{RESET}")
        return
    rungs = images.plan(director)
    print(f"  {DIM}vizual: {director.get('visual_type')}"
          f"{'/' + director['chart_style'] if director.get('chart_style') else ''}"
          f" · zəncir: {' → '.join(k for k, _ in rungs)}{RESET}")
    cand = images.produce(director, 0, rungs, result.run_id, agents)
    plan_obj = images.VisualPlan(director=director, rungs=rungs,
                                 candidates=[cand], agents=agents)
    images.save_manifest(result.run_id, plan_obj)
    if cand.error:
        print(f"  {YELLOW}✗ şəkil: {cand.error[:80]}{RESET}")
    else:
        print(f"  {GREEN}✓{RESET} şəkil: {cand.path}")
        print(f"  {DIM}alt-text: {director.get('alt_text', '')[:90]}{RESET}")


def cmd_run(args) -> int:
    return _execute(None, args)


def cmd_replay(args) -> int:
    preloaded = pipeline.preload_from_run(args.run)
    print(f"{DIM}replay: {len(preloaded[0])} saxlanmış xəbər yenidən istifadə olunur{RESET}")
    return _execute(preloaded, args)


def cmd_styles(args) -> int:
    """Eyni xəbəri 3 üslubda yazır — üslub kalibrləməsi üçün."""
    preloaded = pipeline.preload_from_run(args.run) if args.run else pipeline.collect(args.age)
    print(f"{DIM}Eyni xəbər 3 üslubda yazılır — bəyəndiyinizi voice_guide.md-ə köçürün{RESET}")
    for style in ("analyst", "practitioner", "provocateur"):
        print(f"\n\n{BOLD}{'=' * 74}\n  ÜSLUB: {style.upper()}\n{'=' * 74}{RESET}")
        args.style = style
        _execute(preloaded, args, style=style)
    return 0


def cmd_image(args) -> int:
    from .images import aigen as _aigen, stock as _stock

    data = pipeline.load_run(args.run)
    run_id = data["run_id"]
    print(f"\n{DIM}qaçış: {run_id} · «{data.get('chosen', {}).get('title', '')[:50]}»{RESET}")

    print(f"  {DIM}foto mənbələri: {', '.join(_stock.active_providers())}{RESET}")
    if not _aigen.available():
        print(f"  {YELLOW}○{RESET} AI generasiya pilləsi söndürülüb "
              f"{DIM}(OPENAI_API_KEY təyin edilməyib){RESET}")

    agents: list = []
    print(f"\n→ Visual Director: vizual növü seçilir…")
    director = images.direct(data["post"], data.get("research", {}), agents)
    print(f"  ✓ {BOLD}{director.get('visual_type')}{RESET} — {director.get('reasoning', '')[:70]}")
    print(f"  başlıq: «{director.get('headline', '')}»")
    if director.get("data_points"):
        pts = "  ".join(f"{d.get('label')}={d.get('value')}" for d in director["data_points"][:4])
        print(f"  {DIM}rəqəmlər: {pts}{RESET}")
    queries = images.photo_queries(director)
    print(f"  {DIM}foto sorğuları: {' · '.join(f'«{q}»' for q in queries)}{RESET}")
    if images.queries_are_generic(director):
        print(f"  {YELLOW}⚠{RESET}  Direktor foto sorğusu vermədi — ümumi ehtiyata "
              f"düşüldü. {DIM}Şəkillər mövzudan kənar olacaq.{RESET}")
    if director.get("_tag_recovered"):
        print(f"  {DIM}bərpa olunan sahələr: "
              f"{', '.join(director['_tag_recovered'])}{RESET}")

    # Telegram axını (approval.py) burada postu director-a qoyur — model
    # seçimi və təkrar filtri yalnız o zaman işə düşür. `make image` bunu
    # etmirdi, ona görə sınaq real axından fərqli nəticə verirdi:
    # təkrar şəkillər süzülmür, «niyə seçildi» etiketi boş qalırdı.
    director["_post"] = data["post"]

    for a in agents:
        if a.get("stalled"):
            wait = (a["wall_ms"] - a["duration_ms"]) / 1000
            print(f"  {YELLOW}⚠{RESET}  {a['name']}: model {a['duration_ms']/1000:.0f}s "
                  f"işlədi, real vaxt {a['wall_ms']/1000:.0f}s — "
                  f"{DIM}{wait/60:.0f} dəq gözləmə (kvota pəncərəsi?){RESET}")

    rungs = images.plan(director)
    plan_obj = images.VisualPlan(director=director, rungs=rungs, agents=agents)
    print(f"\n{DIM}zəncir: {' → '.join(k for k, _ in rungs)}{RESET}\n")

    if args.rung is not None:
        targets = [args.rung]
    elif args.all:
        targets = list(range(len(rungs)))
    else:
        targets = [0]

    for index in targets:
        if index >= len(rungs):
            continue
        kind = rungs[index][0]
        print(f"→ pillə {index} ({kind}) hazırlanır…")
        cand = images.produce(director, index, rungs, run_id, agents)
        plan_obj.candidates.append(cand)
        if cand.error:
            print(f"  {YELLOW}✗{RESET} {cand.error[:90]}")
        else:
            print(f"  {GREEN}✓{RESET} {cand.label}")
            print(f"    {cand.path}")
            if cand.credit:
                print(f"    {DIM}{cand.credit}{RESET}")

    manifest = images.save_manifest(run_id, plan_obj)
    print(f"\n{_rule('ALT-TEXT (əlçatanlıq)')}")
    print(f"  {director.get('alt_text', '—')}")

    tokens = sum(a.get("total_tokens", 0) for a in agents)
    cost = sum(a.get("cost_usd", 0.0) for a in agents)
    print(f"\n{_rule('TELEMETRİYA')}")
    for a in agents:
        print(f"  {a['name']:16s} {a.get('total_tokens', 0):>7,} token  "
              f"{a.get('duration_ms', 0) / 1000:>5.1f}s")
    print(f"  {BOLD}CƏMİ: {tokens:,} token · ≈${cost:.4f}{RESET}")
    print(f"  {DIM}manifest: {manifest}{RESET}\n")
    return 0


def _bot() -> "telegram.Bot":
    return telegram.Bot()


def cmd_propose(args) -> int:
    """3 namizəd hazırlayıb Telegram-a göndərir — post YAZILMIR."""
    result = pipeline.propose(max_age_hours=args.age)
    if not result["ok"]:
        print(f"\n{YELLOW}! {result['error']}{RESET}\n")
        if telegram.available() and args.notify_empty:
            notify.send(f"🔕 <b>Bu gün namizəd tapılmadı</b>\n<i>{result['error']}</i>")
        return NO_NEWS_EXIT

    proposal = result["proposal"]
    print(f"\n{_rule('NAMİZƏDLƏR')}")
    for index, cand in enumerate(proposal.candidates):
        print(f"  {index + 1}. [{cand.get('score', '?')}/10] "
              f"{cand.get('title', '')[:56]}")
        print(f"     {DIM}{', '.join(cand.get('sources', []))} · "
              f"{cand.get('pillar')}{RESET}")
    print(f"\n  {DIM}{result['tokens']:,} token{RESET}")

    if args.dry_run or not telegram.available():
        print(f"  {DIM}(göndərilmədi){RESET}\n")
        return 0
    approval.send_proposal(proposal, _bot())
    print(f"\n  {GREEN}✓{RESET} Telegram-a göndərildi — seçiminizi gözləyir")
    print(f"  {DIM}cavab gəlməsə {proposals.AUTO_PICK_HOURS:.0f} saat sonra "
          f"sistem özü seçəcək{RESET}\n")
    return 0


def cmd_send(args) -> int:
    """Son qaçışı növbəyə salıb Telegram-a təsdiq üçün göndərir."""
    data = pipeline.load_run(args.run)
    run_id = data["run_id"]

    image_path = image_label = alt_text = ""
    rung, director = 0, {}
    try:
        manifest = images.load_manifest(run_id)
        director = manifest.get("director", {})
        cands = [c for c in manifest.get("candidates", []) if not c.get("error")]
        if cands:
            best = cands[0]
            image_path, image_label = best.get("path", ""), best.get("label", "")
            rung = best.get("rung", 0)
        alt_text = director.get("alt_text", "")
    except FileNotFoundError:
        print(f"  {YELLOW}○{RESET} şəkil hazırlanmayıb — əvvəlcə: make image")

    item = pqueue.enqueue(
        item_id=run_id, post=data["post"],
        first_comment=data.get("first_comment", ""),
        hashtags=data.get("hashtags", []), chosen=data.get("chosen", {}),
        scores=(data.get("review") or {}).get("scores", {}),
        image_path=image_path, image_rung=rung, image_label=image_label,
        alt_text=alt_text, research=data.get("research", {}),
        angles=data.get("angles", []), chosen_angle_id=data.get("chosen_angle_id"),
        director=director,
    )
    if item.status not in pqueue.OPEN_STATES:
        print(f"  {YELLOW}!{RESET} «{run_id}» artıq emal olunub (status: {item.status})")
        return 0

    if args.dry_run or not telegram.available():
        if not telegram.available():
            print(f"  {YELLOW}○{RESET} Telegram açarları yoxdur — quru rejim")
        print(f"\n{_rule('TELEGRAM MESAJI (önizləmə)')}")
        print(approval.render_post(item).replace("<b>", "").replace("</b>", "")
              .replace("<i>", "").replace("</i>", ""))
        print(f"\n  düymələr: {' | '.join(approval.ACTIONS.values())}")
        if image_path:
            print(f"  şəkil: {image_path}")
        print()
        return 0

    bot = _bot()
    approval.send_for_approval(item, bot)
    print(f"  {GREEN}✓{RESET} Telegram-a göndərildi (mesaj {item.telegram_message_id})")
    print(f"  {DIM}cavabı tutmaq üçün: make poll{RESET}\n")
    return 0


def cmd_poll(args) -> int:
    """Telegram cavablarını emal edir. --watch ilə adaptiv izləmə."""
    import time as _time

    if not telegram.available():
        print(f"\n{YELLOW}! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID boşdur.{RESET}")
        print(f"{DIM}  1) @BotFather-də bot yaradın{RESET}")
        print(f"{DIM}  2) bota bir mesaj yazın{RESET}")
        print(f"{DIM}  3) make tg-chatid{RESET}\n")
        return 2

    bot = _bot()
    agents: list = []
    deadline = _time.time() + args.watch * 60 if args.watch else 0
    started = _time.time()

    while True:
        log = approval.process(bot, agents)
        for line in log:
            print(f"  {GREEN}·{RESET} {line}")
        if not args.watch:
            break
        if _time.time() >= deadline:
            break
        # Adaptiv: ilk 2 saat sıx (5 dəq), sonra seyrək (30 dəq).
        elapsed_min = (_time.time() - started) / 60
        interval = args.interval or (300 if elapsed_min < 120 else 1800)
        _time.sleep(min(interval, max(5, deadline - _time.time())))

    if agents:
        tokens = sum(a.get("total_tokens", 0) for a in agents)
        print(f"  {DIM}{len(agents)} LLM çağırışı · {tokens:,} token{RESET}")
    st = pqueue.stats()
    print(f"\n  bank: {st['bank_size']} · açıq: {st['open']}\n")
    return 0


def cmd_watch(args) -> int:
    """Daimi dinləyici — düymələrə saniyələr içində cavab verir.

    Uzun polling işlədir: Telegram yeniləmə gələnə qədər bağlantını
    açıq saxlayır. GitHub Actions cron-undan fərqli olaraq gecikmə yoxdur.
    """
    import time as _time

    if not telegram.available():
        print(f"\n{YELLOW}! Telegram açarları yoxdur.{RESET}\n")
        return 2

    bot = _bot()
    # «/» yazanda siyahı çıxsın deyə əmrləri qeydiyyatdan keçiririk
    if bot.set_commands(approval.COMMAND_CATALOG):
        print(f"{DIM}  {len(approval.COMMAND_CATALOG)} əmr Telegram-da "
              f"qeydiyyatdan keçdi{RESET}")
    agents: list = []
    print(f"\n{BOLD}Dinləyici işə düşdü{RESET} {DIM}(dayandırmaq: Ctrl+C){RESET}", flush=True)
    print(f"{DIM}Telegram düymələrinə saniyələr içində cavab verilir.{RESET}\n", flush=True)
    notify.healthcheck("start")

    idle = 0
    try:
        while True:
            try:
                log = approval.process(bot, agents, poll_timeout=25)
            except telegram.TelegramUnreachable as exc:
                # Telegram-a çıxış yoxdur — bildirişi Telegram-la GÖNDƏRMƏK
                # mənasızdır. Healthcheck ayrı kanaldır, o işləyir.
                print(f"\n  {RED}✗ Telegram API əlçatmazdır{RESET}", flush=True)
                print(f"  {DIM}{exc}{RESET}", flush=True)
                print(f"  {YELLOW}Düymələr İŞLƏMİR.{RESET} {DIM}Şəbəkəni/VPN-i "
                      f"yoxlayın — DNS həll olunur, TCP 443 bağlanmır."
                      f"{RESET}\n", flush=True)
                notify.healthcheck("fail")
                _time.sleep(60)
                continue
            except Exception as exc:  # noqa: BLE001
                notify.error("Dinləyicidə xəta", exc, command="make watch")
                print(f"  {RED}✗ {exc}{RESET}", flush=True)
                _time.sleep(10)
                continue
            if log:
                idle = 0
                stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                for line in log:
                    print(f"  {DIM}{stamp}{RESET} {GREEN}·{RESET} {line}", flush=True)
            else:
                idle += 1
                if idle % 20 == 0:
                    print(f"  {DIM}{datetime.now(timezone.utc):%H:%M} gözləyir…{RESET}",
                          flush=True)
                    notify.healthcheck()
    except KeyboardInterrupt:
        print(f"\n{DIM}dayandırıldı{RESET}\n")
    return 0


def cmd_queue(args) -> int:
    items = pqueue.all_items()
    if not items:
        print(f"\n{DIM}Növbə boşdur.{RESET}\n")
        return 0
    print(f"\n{BOLD}Növbə{RESET}\n")
    colors = {pqueue.PENDING: YELLOW, pqueue.EDITING: CYAN, pqueue.APPROVED: GREEN,
              pqueue.SCHEDULED: GREEN, pqueue.PUBLISHED: DIM, pqueue.SKIPPED: DIM}
    for item in sorted(items, key=lambda i: i.created_at, reverse=True)[:15]:
        color = colors.get(item.status, "")
        when = f" · {timefmt.short(item.scheduled_for)}" if item.scheduled_for else ""
        print(f"  {color}{item.status:10s}{RESET} {item.chosen.get('title', item.id)[:46]:46s}{when}")
    st = pqueue.stats()
    print(f"\n  bank: {st['bank_size']} · açıq: {st['open']} · ümumi: {st['total']}")
    print(f"  rejim: {'dayandırılıb' if approval.settings().get('paused') else 'aktiv'}\n")
    return 0


def cmd_tgid(_args) -> int:
    """Bota yazılan mesajdan chat ID-ni tapır."""
    if not config.TELEGRAM_TOKEN:
        print(f"\n{RED}✗ TELEGRAM_BOT_TOKEN boşdur.{RESET}")
        print(f"{DIM}  @BotFather → /newbot → tokeni .env-ə yazın{RESET}\n")
        return 2
    transport = telegram.HttpTransport(config.TELEGRAM_TOKEN)
    me = transport.call("getMe", {})
    print(f"\n  bot: @{me.get('username')} ({me.get('first_name')})")
    updates = transport.call("getUpdates", {"timeout": 0}) or []
    chats = {}
    for upd in updates:
        msg = upd.get("message") or upd.get("callback_query", {}).get("message") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or "?"
    if not chats:
        print(f"\n  {YELLOW}Mesaj tapılmadı.{RESET} Telegram-da bota "
              f"@{me.get('username')} bir söz yazın, sonra bu əmri təkrarlayın.\n")
        return 1
    print()
    for chat_id, name in chats.items():
        print(f"  {GREEN}✓{RESET} TELEGRAM_CHAT_ID={chat_id}   {DIM}({name}){RESET}")
    print(f"\n  {DIM}Bunu .env faylına yazın.{RESET}\n")
    return 0


def cmd_publish(args) -> int:
    """Vaxtı çatmış postları LinkedIn-ə yayımlayır."""
    stuck = publisher.stuck_items()
    if stuck:
        print(f"\n{RED}✗ Yarımçıq yayım aşkarlandı — avtomatik davam edilmir:{RESET}")
        for item in stuck:
            print(f"    {item.id} — «{item.chosen.get('title', '')[:40]}»")
        print(f"{DIM}  LinkedIn profilinizi yoxlayın. Post varsa `make queue` ilə{RESET}")
        print(f"{DIM}  vəziyyəti aydınlaşdırın; yoxdursa state/queue.json-da{RESET}")
        print(f"{DIM}  statusu «approved» edin.{RESET}\n")
        return 4

    token = linkedin.load_token()
    if not args.dry_run:
        if not token:
            print(f"\n{RED}✗ LinkedIn tokeni yoxdur.{RESET} {DIM}make li-auth{RESET}\n")
            return 2
        if token.expired:
            print(f"\n{RED}✗ Token bitib ({token.expires_dt:%d.%m.%Y}).{RESET} "
                  f"{DIM}make li-auth{RESET}\n")
            return 3

    if args.draft:
        # Qaralama sınağı üçün təsdiq gözləyən postu da götürürük —
        # heç nə ictimai olmadığı üçün təsdiq qapısı pozulmur.
        items = ([pqueue.get(args.item)] if args.item
                 else publisher.pick_due(from_bank=True) or pqueue.open_items()[-1:])
        items = [i for i in items if i]
    else:
        items = publisher.pick_due(from_bank=args.from_bank)
    if not items:
        limited = publisher.rate_limit_block()
        if limited:
            # Vaxtı çatmış postları növbəti pəncərəyə keçiririk ki,
            # cədvəldəki vaxt yalan olmasın.
            moved = []
            for item in pqueue.due():
                pqueue.schedule(item)
                moved.append(item)
            print(f"\n{YELLOW}⏸ Sürət həddi:{RESET} {limited}")
            for item in moved:
                print(f"  {DIM}→ «{item.chosen.get('title', '')[:40]}» "
                      f"{timefmt.fmt(item.scheduled_for)}-a keçirildi{RESET}")
            if moved and telegram.available():
                notify.warn(
                    "Sürət həddi — post təxirə salındı",
                    f"{limited}\n\n"
                    + "\n".join(f"→ {i.chosen.get('title','')[:50]}: "
                                 f"{timefmt.fmt(i.scheduled_for)}" for i in moved))
            print()
            return 0
        bank_size = len(queue_bank())
        print(f"\n{DIM}Yayımlanacaq post yoxdur. Bankda: {bank_size}{RESET}")
        print(f"{DIM}Bankdan yayımlamaq üçün: make publish ARGS='--from-bank'{RESET}\n")
        return 0

    bot = None
    if telegram.available() and not args.dry_run:
        try:
            bot = telegram.Bot()
        except telegram.TelegramError:
            bot = None

    code = 0
    with publisher.Lock():
        for item in items[: args.limit]:
            title = item.chosen.get("title", item.id)[:50]
            print(f"\n→ «{title}»")
            _blocked = publisher.score_block(item)
            if _blocked and not args.force and not args.draft:
                print(f"  {YELLOW}⚠ bloklandı:{RESET} {_blocked}")
                continue
            if args.dry_run:
                print(f"  {YELLOW}○ quru rejim{RESET} · {len(item.post)} simvol · "
                      f"şəkil: {'var' if item.image_path else 'yox'}")
                print(f"  {DIM}birinci şərh: {item.first_comment[:70]}{RESET}")
                continue
            try:
                result = publisher.publish_item(item, token, draft=args.draft,
                                                force=args.force)
                if result.get("draft"):
                    print(f"  {GREEN}✓ QARALAMA yaradıldı{RESET} — {result['urn']}")
                    print(f"  {DIM}LinkedIn → sizin profil → «Posts» → «Drafts»{RESET}")
                else:
                    print(f"  {GREEN}✓{RESET} {result['url']}")
                for warning in result["warnings"]:
                    print(f"  {YELLOW}⚠{RESET} {warning[:100]}")
                if bot and not result.get("draft"):
                    approval.notify_published(item, result, bot)
            except Exception as exc:  # noqa: BLE001
                code = 1
                print(f"  {RED}✗ {exc}{RESET}")
                if bot:
                    bot.send_message(f"⚠️ Yayım alınmadı: {str(exc)[:200]}")
    cleaned = (pqueue.prune_images() + pqueue.prune_workdir()
               + pqueue.prune_runs() + pqueue.compact())
    if cleaned:
        print(f"  {DIM}{cleaned} köhnə fayl/element təmizləndi{RESET}")
    print()
    return code


def queue_bank():
    return pqueue.bank()


def cmd_li_export(_args) -> int:
    """LinkedIn tokenini GitHub Secrets üçün göstərir."""
    token = linkedin.load_token()
    if not token:
        print(f"\n{RED}✗ Token yoxdur.{RESET} {DIM}make li-auth{RESET}\n")
        return 2
    print(f"\n{BOLD}GitHub Secrets{RESET} {DIM}(Settings → Secrets and variables → Actions){RESET}\n")
    rows = [
        ("LINKEDIN_ACCESS_TOKEN", token.access_token),
        ("LINKEDIN_PERSON_URN", token.person_urn),
        ("LINKEDIN_EXPIRES_AT", token.expires_at),
        ("LINKEDIN_PROFILE_NAME", token.name),
    ]
    for name, value in rows:
        print(f"  {CYAN}{name}{RESET}")
        print(f"  {value}\n")
    print(f"  {YELLOW}⚠ Token {token.days_left:.0f} gün sonra bitir "
          f"({token.expires_dt:%d.%m.%Y}).{RESET}")
    print(f"  {DIM}Yenilədikdən sonra bu əmri təkrarlayıb secret-ləri yeniləyin.{RESET}\n")
    return 0


def cmd_remind(_args) -> int:
    if not telegram.available():
        print(f"\n{YELLOW}! Telegram açarları yoxdur.{RESET}\n")
        return 2

    # Token xəbərdarlığı — gündə bir dəfədən çox göndərilmir
    warning = linkedin.expiry_warning()
    if warning:
        sent = notify.send(warning) if not notify._throttled("linkedin-expiry") else False
        if sent:
            print(f"  {YELLOW}·{RESET} token xəbərdarlığı göndərildi")

    bot = telegram.Bot()
    # Cavabsız qalmış mövzu təklifləri — sistem özü seçir
    log = approval.auto_pick_due(bot)
    log += approval.send_reminders(bot)
    for line in log:
        print(f"  {GREEN}·{RESET} {line}")
    if not log:
        print(f"  {DIM}göndəriləcək xatırlatma yoxdur{RESET}")
    print()
    return 0


def cmd_notion_setup(_args) -> int:
    """Notion bazasını tapır və ya yaradır."""
    if not notion.token():
        print(f"\n{RED}✗ NOTION_TOKEN boşdur.{RESET}")
        print(f"{DIM}  notion.so/my-integrations → yeni inteqrasiya → Internal Secret{RESET}\n")
        return 2
    try:
        pages = notion.accessible_pages()
    except notion.NotionError as exc:
        print(f"\n{RED}✗ {exc}{RESET}\n")
        return 3

    if not pages:
        print(f"\n{YELLOW}İnteqrasiya heç bir səhifə görmür.{RESET}\n")
        print("  Notion-da bir səhifə açın (və ya yaradın), sonra:")
        print(f"    {BOLD}··· (sağ yuxarı) → Connections → inteqrasiyanı seçin{RESET}")
        print(f"\n  Sonra bu əmri təkrarlayın: {BOLD}make notion-setup{RESET}\n")
        return 4

    print(f"\n{BOLD}İnteqrasiyanın gördükləri{RESET}\n")
    for page in pages:
        print(f"  {page['object']:9s} {page['id']}  {page['title'][:44]}")

    existing = [p for p in pages if p["object"] == "database"]
    if notion.database_id():
        current = next((p for p in existing
                        if p["id"].replace("-", "") == notion.database_id().replace("-", "")),
                       None)
        if current:
            print(f"\n  {GREEN}✓{RESET} NOTION_DATABASE_ID düzgündür — «{current['title']}»")
            print(f"  {DIM}sinxronizasiya: make notion-sync{RESET}\n")
            return 0
        print(f"\n  {YELLOW}!{RESET} .env-dəki NOTION_DATABASE_ID bu inteqrasiyaya görünmür.")

    if existing:
        print(f"\n  Mövcud baza tapıldı. .env faylına yazın:")
        print(f"    {CYAN}NOTION_DATABASE_ID={existing[0]['id'].replace('-', '')}{RESET}\n")
        return 0

    parent = next((p for p in pages if p["object"] == "page"), None)
    if not parent:
        print(f"\n  {YELLOW}Baza yaratmaq üçün paylaşılmış adi səhifə lazımdır.{RESET}\n")
        return 5
    print(f"\n  «{parent['title']}» səhifəsində baza yaradılır…")
    db_id = notion.create_database(parent["id"])
    print(f"  {GREEN}✓{RESET} yaradıldı. .env faylına yazın:")
    print(f"    {CYAN}NOTION_DATABASE_ID={db_id.replace('-', '')}{RESET}\n")
    return 0


def cmd_notion_sync(_args) -> int:
    if not notion.available():
        print(f"\n{YELLOW}! NOTION_TOKEN / NOTION_DATABASE_ID boşdur.{RESET} "
              f"{DIM}make notion-setup{RESET}\n")
        return 2
    try:
        result = notion.sync()
    except notion.NotionError as exc:
        print(f"\n{RED}✗ {exc}{RESET}\n")
        return 3
    for line in result["pulled"]:
        print(f"  {CYAN}←{RESET} {line}")
    errors = [x for x in result["pushed"] if "XƏTA" in x]
    print(f"  {GREEN}→{RESET} {len(result['pushed']) - len(errors)} kart yeniləndi")
    for err in errors:
        print(f"  {RED}✗{RESET} {err[:110]}")
    if not result["pulled"]:
        print(f"  {DIM}Notion-dan yeni dəyişiklik yoxdur{RESET}")
    print()
    return 0


def cmd_archive(_args) -> int:
    """Yayımlanmış postları arxivə yazır və indeksi yeniləyir."""
    count = archive.sync_all()
    print(f"\n  {GREEN}✓{RESET} {count} post arxivləndi")
    print(f"  {DIM}{archive.INDEX}{RESET}\n")
    return 0


def cmd_heartbeat(_args) -> int:
    """GitHub Actions-ın sağ olduğunu qeyd edir.

    Lokal cron buna baxıb yayıma qarışıb-qarışmayacağını qərar verir.
    Vəziyyət commit-lərinə baxmaq etibarsızdır: sağlam CI heç nə
    dəyişməsə commit də etmir.
    """
    from . import store

    path = config.STATE_DIR / "ci_heartbeat.json"
    store.write_json(path, {
        "at": datetime.now(timezone.utc).isoformat(),
        "run": os.environ.get("GITHUB_RUN_ID", "local"),
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
    }, indent=None)
    print(f"  ürək döyüntüsü: {path.name}")
    return 0


def cmd_smoke(args) -> int:
    """Real API-larla inteqrasiya sınağı — heç nə yayımlanmır."""
    print(f"\n{BOLD}İnteqrasiya sınağı{RESET} "
          f"{DIM}(real API-lar · heç nə ictimai olmur){RESET}\n")
    result = smoke.run(skip_linkedin=args.no_linkedin)
    for check in result.checks:
        mark = f"{GREEN}✓{RESET}" if check.ok else f"{RED}✗{RESET}"
        print(f"  {mark} {check.name:26s} {check.seconds:5.1f}s  "
              f"{DIM}{check.detail[:60]}{RESET}")

    if result.ok:
        print(f"\n  {GREEN}Bütün inteqrasiyalar işləyir.{RESET}\n")
    else:
        print(f"\n  {RED}{len(result.failed)} problem:{RESET}")
        for check in result.failed:
            print(f"    • {check.name}: {check.detail[:120]}")
        print()

    if args.send and telegram.available():
        lines = ["🩺 <b>İnteqrasiya sınağı</b>", ""]
        for check in result.checks:
            lines.append(f"{'✅' if check.ok else '🔴'} {check.name}"
                         + (f" — <i>{check.detail[:70]}</i>" if not check.ok else ""))
        if not result.ok:
            lines += ["", "<i>Yuxarıdakılar yayımı dayandıra bilər.</i>"]
        notify.send("\n".join(lines))
    return 0 if result.ok else 1


def cmd_report(args) -> int:
    """Həftəlik yekun: kvota, növbə, token müddəti, mənbə sağlamlığı."""
    usage = state.usage_report(7)
    qst = pqueue.stats()
    token = linkedin.load_token()
    _, feed_errors = sources.fetch_all(max_age_hours=72)

    lines = ["📊 <b>Həftəlik hesabat</b>", ""]
    published = len([i for i in pqueue.all_items()
                     if i.status == pqueue.PUBLISHED])
    lines += [
        f"🚀 Yayımlanıb (ümumi): <b>{published}</b>",
        f"🏦 Bankda: <b>{qst['bank_size']}</b>",
        f"⏳ Açıq: {qst['open']}",
        "",
        f"🔢 Son 7 gün: <b>{usage['runs']}</b> qaçış · "
        f"{usage['tokens']:,} token · ≈${usage['cost_usd']}",
    ]
    if usage["runs"]:
        lines.append(f"   <i>post başına ≈${usage['cost_usd'] / usage['runs']:.3f} "
                     f"ekvivalent</i>")

    balance = state.pillar_balance()
    if any(balance.values()):
        lines += ["", "📚 Sütun balansı (14 gün):"]
        lines += [f"   {k}: {v}" for k, v in balance.items()]

    if token:
        if token.expired:
            lines += ["", "🔴 <b>LinkedIn tokeni BİTİB</b> — make li-auth"]
        elif token.expiring_soon:
            lines += ["", f"🟡 <b>LinkedIn tokeni {token.days_left:.0f} gün sonra bitir</b>",
                      "   <i>make li-auth → make li-export → GitHub Secrets</i>"]
        else:
            lines += ["", f"🟢 LinkedIn tokeni: {token.days_left:.0f} gün qalır"]
    else:
        lines += ["", "⚪️ LinkedIn girişi yoxdur"]

    if feed_errors:
        lines += ["", f"⚠️ Əlçatmaz mənbə: {len(feed_errors)}"]
        lines += [f"   • {name}" for name, _ in feed_errors[:4]]

    stuck = publisher.stuck_items()
    if stuck:
        lines += ["", f"🔴 <b>{len(stuck)} yarımçıq yayım</b> — əl ilə yoxlayın"]

    cal = calibration.reminder_lines()
    if cal:
        lines += ["", "📝 <b>Doldurulmamış kalibrləmə</b> "
                      "<i>(voice və yerli uyğunluq ballarını saxlayır)</i>"]
        lines += [f"   • {line}" for line in cal]

    text = "\n".join(lines)
    if args.send and telegram.available():
        telegram.Bot().send_message(text)
        print("  hesabat Telegram-a göndərildi")
    print("\n" + text.replace("<b>", "").replace("</b>", "")
          .replace("<i>", "").replace("</i>", "") + "\n")
    return 0


def cmd_stats(args) -> int:
    report = state.usage_report(args.days)
    print(f"\n{BOLD}Son {report['days']} gün{RESET}\n")
    print(f"  qaçış: {report['runs']}")
    print(f"  token: {report['tokens']:,}")
    print(f"  API-ekvivalent: ≈${report['cost_usd']}")
    if report["runs"]:
        print(f"  post başına: {report['tokens'] // report['runs']:,} token · "
              f"≈${report['cost_usd'] / report['runs']:.4f}")
    print(f"  sütun balansı: {state.pillar_balance()}\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="avtopost", description="LinkedIn avto-post — M1")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="tam axını işə sal")
    p.add_argument("--style", default=None, help="analyst | practitioner | provocateur")
    p.add_argument("--age", type=int, default=None, help="maksimum xəbər yaşı (saat)")
    p.add_argument("--cluster", type=int, default=None, help="konkret klasteri seç")
    p.add_argument("--commit", action="store_true", help="yaddaşa yaz")
    p.add_argument("--image", action="store_true", help="şəkli də hazırla")
    p.add_argument("--notify-empty", action="store_true",
                   help="xəbər tapılmasa Telegram-a bildir")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("replay", help="köhnə xəbərlərlə yenidən qaç (prompt sınağı)")
    p.add_argument("--run", default=None, help="qaçış ID (default: sonuncu)")
    p.add_argument("--style", default=None)
    p.add_argument("--cluster", type=int, default=None)
    p.add_argument("--commit", action="store_true")
    p.add_argument("--image", action="store_true", help="şəkli də hazırla")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("styles", help="eyni xəbəri 3 üslubda yaz")
    p.add_argument("--run", default=None)
    p.add_argument("--age", type=int, default=None)
    p.add_argument("--cluster", type=int, default=None)
    p.set_defaults(func=cmd_styles, style=None, commit=False)

    p = sub.add_parser("image", help="son post üçün şəkil zəncirini işə sal")
    p.add_argument("--run", default=None, help="qaçış ID (default: sonuncu)")
    p.add_argument("--all", action="store_true", help="bütün pillələri hazırla")
    p.add_argument("--rung", type=int, default=None, help="yalnız bu pilləni hazırla")
    p.set_defaults(func=cmd_image)

    p = sub.add_parser("propose", help="3 namizəd göndər — post yazılmır")
    p.add_argument("--age", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--notify-empty", action="store_true")
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("send", help="son postu Telegram-a təsdiq üçün göndər")
    p.add_argument("--run", default=None)
    p.add_argument("--dry-run", action="store_true", help="göndərmə, yalnız göstər")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("poll", help="Telegram cavablarını emal et")
    p.add_argument("--watch", type=int, default=0, help="neçə dəqiqə izləsin")
    p.add_argument("--interval", type=int, default=0, help="saniyə (default: adaptiv)")
    p.set_defaults(func=cmd_poll)

    p = sub.add_parser("watch", help="daimi dinləyici — düymələrə ani cavab")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("queue", help="növbənin vəziyyəti")
    p.set_defaults(func=cmd_queue)

    p = sub.add_parser("tg-chatid", help="Telegram chat ID-ni tap")
    p.set_defaults(func=cmd_tgid)

    p = sub.add_parser("publish", help="vaxtı çatmış postları LinkedIn-ə yayımla")
    p.add_argument("--dry-run", action="store_true", help="göndərmə, yalnız göstər")
    p.add_argument("--from-bank", action="store_true",
                   help="cədvəldə post yoxdursa bankdan götür")
    p.add_argument("--limit", type=int, default=1, help="maksimum post sayı")
    p.add_argument("--draft", action="store_true",
                   help="LinkedIn-də QARALAMA yarat — ictimai olmur, status dəyişmir")
    p.add_argument("--item", default=None, help="konkret post ID")
    p.add_argument("--force", action="store_true",
                   help="aşağı ballı postu da yayımla")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("notion-setup", help="Notion bazasını tap/yarat")
    p.set_defaults(func=cmd_notion_setup)

    p = sub.add_parser("notion-sync", help="Notion ↔ növbə sinxronizasiyası")
    p.set_defaults(func=cmd_notion_sync)

    p = sub.add_parser("archive", help="yayımlanmış postları arxivə yaz")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("heartbeat", help="CI-nin sağ olduğunu qeyd et")
    p.set_defaults(func=cmd_heartbeat)

    p = sub.add_parser("smoke", help="real API inteqrasiya sınağı")
    p.add_argument("--send", action="store_true", help="nəticəni Telegram-a göndər")
    p.add_argument("--no-linkedin", action="store_true",
                   help="LinkedIn qaralama sınağını atla")
    p.set_defaults(func=cmd_smoke)

    p = sub.add_parser("report", help="həftəlik yekun hesabat")
    p.add_argument("--send", action="store_true", help="Telegram-a göndər")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("li-export", help="LinkedIn tokenini GitHub Secrets üçün göstər")
    p.set_defaults(func=cmd_li_export)

    p = sub.add_parser("remind", help="yayımdan sonrakı şərh xatırlatmaları")
    p.set_defaults(func=cmd_remind)

    p = sub.add_parser("sources", help="mənbələri və klasterləri göstər")
    p.add_argument("--age", type=int, default=48)
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("doctor", help="bütün inteqrasiyaları yoxla")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("stats", help="kvota/xərc hesabatı")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    command = f"{args.cmd}"
    try:
        code = args.func(args)
        if code not in (0, config_no_news()) and args.cmd in NOTIFY_COMMANDS:
            notify.warn(f"«{command}» uğursuz bitdi",
                        f"çıxış kodu: {code}")
        return code
    except llm.NotLoggedIn as exc:
        notify.error("Claude Code girişi yoxdur", exc, command=f"make {command}")
        print(f"\n{RED}✗ {exc}{RESET}\n")
        return 2
    except llm.QuotaExhausted as exc:
        notify.warn("Abunəlik limiti bitib",
                    "Sistem bir saat sonra yenidən cəhd edəcək. "
                    "Yayım varsa bankdan ediləcək.")
        print(f"\n{YELLOW}! Abunəlik limiti bitib: {exc}{RESET}")
        print(f"{DIM}  Bir saat sonra yenidən cəhd edin.{RESET}\n")
        return 3
    except FileNotFoundError as exc:
        print(f"\n{YELLOW}! {exc}{RESET}\n")
        return 4
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 — səssiz sınmaq qadağandır
        notify.error("Gözlənilməz xəta", exc, command=f"make {command}")
        print(f"\n{RED}✗ {type(exc).__name__}: {exc}{RESET}\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

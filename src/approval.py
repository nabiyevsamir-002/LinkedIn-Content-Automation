"""Telegram təsdiq döngəsi: mesaj, düymələr, cavabların emalı.

Axın: post hazır → Telegram-a şəkil + mətn + düymələr → siz basırsınız →
poll bunu tutur → status dəyişir (bank / cədvəl / keçildi).
"""
from __future__ import annotations

import html
import json
import pathlib

from . import config, editor, images, linkedin, pipeline, preview, publisher, queue, telegram, timefmt

SETTINGS = config.STATE_DIR / "settings.json"

ACTIONS = {
    "ok": "✅ Yayımla",
    "bank": "🏦 Banka at",
    "img": "🖼 Başqa dizayn",
    "photo": "📷 Real foto",
    "rw": "🔄 Yenidən yaz",
    "ed": "✏️ Mətni dəyiş",
    "skip": "❌ Keç",
}


# --- parametrlər ------------------------------------------------------

def settings() -> dict:
    if not SETTINGS.exists():
        return {"paused": False}
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"paused": False}


def set_setting(key: str, value) -> dict:
    data = settings()
    data[key] = value
    SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


# --- mesaj qurulması --------------------------------------------------

def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def keyboard(item: queue.Item) -> list:
    return [
        [{"text": ACTIONS["ok"], "callback_data": f"a|{item.id}|ok"},
         {"text": ACTIONS["bank"], "callback_data": f"a|{item.id}|bank"}],
        [{"text": ACTIONS["img"], "callback_data": f"a|{item.id}|img"},
         {"text": ACTIONS["photo"], "callback_data": f"a|{item.id}|photo"}],
        [{"text": ACTIONS["rw"], "callback_data": f"a|{item.id}|rw"},
         {"text": ACTIONS["ed"], "callback_data": f"a|{item.id}|ed"}],
        [{"text": ACTIONS["skip"], "callback_data": f"a|{item.id}|skip"}],
    ]


def render_post(item: queue.Item) -> str:
    """Postu LinkedIn kəsilmə xətti ilə birlikdə göstərir."""
    cut = preview.fold_index(item.post)
    head, tail = item.post[:cut].rstrip(), item.post[cut:].lstrip()
    scores = item.scores or {}
    score_line = " · ".join(
        f"{k}:{v}" for k, v in scores.items() if k != "overall"
    )
    parts = [
        f"📝 <b>{_esc(item.chosen.get('title', 'Post'))}</b>",
        f"<i>{_esc(item.chosen.get('pillar', ''))} · "
        f"{_esc(', '.join(item.chosen.get('sources', [])))}</i>",
        "",
        _esc(head),
        "— — — — — <i>…daha çox</i> — — — — —",
    ]
    if tail:
        parts.append(_esc(tail))
    parts += [
        "",
        f"🔗 <i>{_esc(item.first_comment)}</i>",
        "",
        f"📊 <b>{scores.get('overall', '?')}/10</b>  <i>{_esc(score_line)}</i>",
        f"📐 {len(item.post)} simvol · hook {cut}",
    ]
    if item.image_label:
        parts.append(f"🖼 {_esc(item.image_label)}")
    overall = scores.get("overall")
    if overall is not None and overall < config.MIN_PUBLISH_SCORE:
        parts += ["", f"⚠️ <b>Aşağı bal ({overall}/10)</b> — nəzarətçi bu postda "
                      "ciddi problem görüb. Yayım bloklanıb; «🔄 Yenidən yaz» "
                      "və ya «❌ Keç» tövsiyə olunur."]
    return "\n".join(parts)


def send_for_approval(item: queue.Item, bot: telegram.Bot) -> queue.Item:
    """Şəkli və postu düymələrlə birlikdə göndərir."""
    if item.image_path:
        try:
            bot.send_photo(item.image_path, f"🖼 {_esc(item.image_label)}")
        except Exception as exc:  # noqa: BLE001 — şəkil postu bloklamamalıdır
            bot.send_message(f"⚠️ Şəkil göndərilə bilmədi: {_esc(str(exc))[:120]}")
    message_id = bot.send_message(render_post(item), keyboard(item))
    item.telegram_message_id = message_id
    item.note("sent_to_telegram", str(message_id))
    return queue.save(item)


# --- cavabların emalı -------------------------------------------------

def handle_callback(update: dict, bot: telegram.Bot, agents: list) -> str:
    cq = update["callback_query"]
    data = cq.get("data", "")
    parts = data.split("|")
    if len(parts) != 3 or parts[0] != "a":
        bot.answer_callback(cq["id"], "Naməlum əmr")
        return f"naməlum callback: {data}"

    _, item_id, action = parts

    # Ani geri əlaqə: uzun sürən əməliyyatlarda istifadəçi düymənin
    # işlədiyini dərhal görməlidir, yoxsa «heç nə olmur» hissi yaranır.
    WAIT_MESSAGES = {
        "img": "⏳ <b>Yeni dizayn hazırlanır…</b>\n<i>təxminən 40 saniyə</i>",
        "photo": "⏳ <b>Foto axtarılır…</b>\n<i>təxminən 10 saniyə</i>",
        "rw": "⏳ <b>Post yenidən yazılır…</b>\n<i>təxminən 1 dəqiqə</i>",
        "ok": "⏳ <b>Təsdiqlənir…</b>",
        "bank": "⏳ <b>Banka atılır…</b>",
    }
    item = queue.get(item_id)
    if action in WAIT_MESSAGES and item and item.status not in queue.TERMINAL_STATES:
        try:
            bot.send_message(WAIT_MESSAGES[action])
        except Exception:  # noqa: BLE001 — bildiriş əməliyyatı bloklamamalıdır
            pass
    if not item:
        bot.answer_callback(cq["id"], "Post tapılmadı")
        return f"post tapılmadı: {item_id}"

    # Köhnə mesajlarda düymələr qalır. Bitmiş posta təkrar basılsa,
    # əməliyyatı yenidən icra etmirik — sadəcə vəziyyəti xatırladırıq.
    if item.status in queue.TERMINAL_STATES and action not in ("del",):
        labels = {queue.PUBLISHED: "artıq yayımlanıb", queue.SKIPPED: "artıq keçilib"}
        bot.answer_callback(cq["id"], labels.get(item.status, item.status))
        bot.edit_markup(item.telegram_message_id, None)
        return f"{item_id}: {labels.get(item.status, item.status)} — təkrar əməliyyat edilmədi"

    if action == "ok":
        queue.schedule(item)
        bot.answer_callback(cq["id"], "Cədvələ salındı")
        bot.edit_markup(item.telegram_message_id, None)
        bot.send_message(
            f"✅ <b>Təsdiqləndi</b>\n\n"
            f"🕐 Yayım: <b>{timefmt.fmt(item.scheduled_for)}</b> "
            f"<i>({timefmt.label()})</i>\n"
            f"<i>Yayımlandıqdan sonra sizə bildiriş gələcək.</i>"
        )
        return f"{item_id}: cədvələ salındı → {item.scheduled_for}"

    if action == "bank":
        queue.set_status(item, queue.APPROVED, "banka atıldı")
        bot.answer_callback(cq["id"], "Banka atıldı")
        bot.edit_markup(item.telegram_message_id, None)
        bot.send_message(f"🏦 Banka atıldı. Bankda <b>{len(queue.bank())}</b> post var.")
        return f"{item_id}: banka atıldı"

    if action == "skip":
        queue.set_status(item, queue.SKIPPED, "istifadəçi keçdi")
        bot.answer_callback(cq["id"], "Keçildi")
        bot.edit_markup(item.telegram_message_id, None)
        bot.send_message("❌ Bu post keçildi.")
        return f"{item_id}: keçildi"

    if action == "ed":
        queue.set_status(item, queue.EDITING, "redaktə gözlənilir")
        bot.answer_callback(cq["id"], "Düzəlişi yazın")
        bot.send_message(
            "✏️ <b>Düzəlişi yazın</b> — adi cümlə ilə.\n"
            "<i>məsələn: «tonu yumşalt, ikinci bəndi at, sondakı sual "
            "daha konkret olsun»</i>"
        )
        return f"{item_id}: redaktə rejimi"

    if action == "img":
        return _next_image(item, cq, bot, agents)

    if action == "photo":
        return _next_image(item, cq, bot, agents, kind="pexels")

    if action == "rw":
        return _rewrite(item, cq, bot, agents)

    if action == "del":
        return _undo_publish(item, cq, bot)

    bot.answer_callback(cq["id"], "Naməlum əmr")
    return f"naməlum əməliyyat: {action}"


def _next_image(item: queue.Item, cq: dict, bot: telegram.Bot, agents: list,
                kind: str | None = None) -> str:
    """Növbəti şəkil variantı. `kind` verilsə birbaşa həmin növə keçir."""
    bot.answer_callback(
        cq["id"], "Foto axtarılır…" if kind == "pexels" else "Növbəti dizayn hazırlanır…"
    )
    try:
        director = item.director or images.load_manifest(item.id)["director"]
        rungs = images.plan(director)
        if kind:
            # Həmin növün hələ göstərilməmiş ilk pilləsinə tullanırıq
            nxt = next((i for i, (k, _) in enumerate(rungs)
                        if k == kind and i > item.image_rung), None)
            if nxt is None:
                nxt = next((i for i, (k, _) in enumerate(rungs) if k == kind), None)
            if nxt is None:
                bot.send_message(
                    "📷 Foto variantı yoxdur.\n"
                    "<i>PEXELS_API_KEY təyin edilməyibsə foto pillələri "
                    "zəncirdə olmur.</i>"
                )
                return f"{item.id}: foto pilləsi yoxdur"
        else:
            nxt = item.image_rung + 1
        if nxt >= len(rungs):
            bot.send_message("🖼 Zəncirin sonu — başqa variant qalmadı.")
            return f"{item.id}: şəkil zənciri bitdi"
        cand = images.produce(director, nxt, rungs, item.id, agents)
        if cand.error:
            bot.send_message(f"⚠️ Şəkil alınmadı: {_esc(cand.error)[:150]}")
            return f"{item.id}: şəkil xətası — {cand.error}"
        item.image_path = queue._persist_image(item.id, cand.path) or cand.path
        item.image_rung, item.image_label = nxt, cand.label
        item.note("image_advanced", cand.label)
        queue.save(item)
        bot.send_photo(cand.path, f"🖼 {_esc(cand.label)} ({nxt + 1}/{len(rungs)})")
        bot.send_message("Bu şəkil necədir?", keyboard(item))
        return f"{item.id}: şəkil pilləsi {nxt} — {cand.label}"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Şəkil zənciri xətası: {_esc(str(exc))[:150]}")
        return f"{item.id}: şəkil xətası — {exc}"


def _rewrite(item: queue.Item, cq: dict, bot: telegram.Bot, agents: list) -> str:
    bot.answer_callback(cq["id"], "Yenidən yazılır…")
    try:
        run_data = {
            "research": item.research, "angles": item.angles,
            "chosen": item.chosen, "chosen_angle_id": item.chosen_angle_id,
        }
        if not run_data["research"]:          # köhnə elementlər üçün ehtiyat yol
            run_data = pipeline.load_run(item.id)
        data = editor.rewrite(run_data, run_data.get("chosen_angle_id"), agents)
        item.post = data.get("post", item.post)
        item.first_comment = data.get("first_comment") or item.first_comment
        item.status = queue.PENDING
        item.note("rewritten", f"rakurs #{data.get('chosen_angle_id')}")
        queue.save(item)
        bot.send_message("🔄 <b>Yenidən yazıldı</b> (başqa rakursla):")
        item.telegram_message_id = bot.send_message(render_post(item), keyboard(item))
        queue.save(item)
        return f"{item.id}: yenidən yazıldı"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Yenidən yazma alınmadı: {_esc(str(exc))[:150]}")
        return f"{item.id}: yenidən yazma xətası — {exc}"


def _undo_publish(item: queue.Item, cq: dict, bot: telegram.Bot) -> str:
    bot.answer_callback(cq["id"], "Silinir…")
    token = linkedin.load_token()
    if not token or token.expired:
        bot.send_message("⚠️ LinkedIn tokeni yoxdur/bitib — post silinə bilmədi.")
        return f"{item.id}: silmə üçün token yoxdur"
    try:
        publisher.undo(item, token)
        bot.edit_markup(item.telegram_message_id, None)
        bot.send_message("🗑 <b>Post LinkedIn-dən silindi.</b>")
        return f"{item.id}: LinkedIn-dən silindi"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Silinmədi: {_esc(str(exc))[:200]}")
        return f"{item.id}: silmə xətası — {exc}"


def notify_published(item: queue.Item, result: dict, bot: telegram.Bot) -> None:
    """Yayımdan sonra: təsdiq, link və 10 dəqiqəlik geri-al düyməsi."""
    lines = [
        "🚀 <b>POST LINKEDIN-Ə YAYIMLANDI</b>",
        "",
        f"📄 <i>{_esc(item.chosen.get('title', '')[:70])}</i>",
        f"🕐 {timefmt.fmt(item.published_at)} ({timefmt.label()})",
        "",
        f'🔗 <a href="{result["url"]}">Postu aç</a>',
    ]
    if not result.get("comment_ok"):
        lines.append("\n⚠️ Birinci şərh əlavə edilmədi — əl ilə yazın.")
    for warning in result.get("warnings", []):
        lines.append(f"⚠️ <i>{_esc(warning)[:150]}</i>")
    lines.append(f"\n<i>{publisher.UNDO_WINDOW_MINUTES} dəqiqə ərzində geri ala bilərsiniz.</i>")
    keyboard = [[{"text": "🗑 Postu sil", "callback_data": f"a|{item.id}|del"}]]
    message_id = bot.send_message("\n".join(lines), keyboard)
    item.telegram_message_id = message_id
    queue.save(item)


def send_reminders(bot: telegram.Bot) -> list[str]:
    """İlk saatların çatımı şərhlərdən asılıdır — vaxtında xəbər veririk."""
    log = []
    for item, label in publisher.due_reminders():
        bot.send_message(
            f"💬 Post <b>{label}</b> əvvəl yayımlandı — şərhlərə baxın.\n"
            f'<a href="{item.linkedin_url}">{_esc(item.linkedin_url)}</a>\n'
            f"<i>İlk saatların reaksiyası çatımı müəyyən edir.</i>"
        )
        publisher.mark_reminded(item, label)
        log.append(f"{item.id}: xatırlatma {label}")
    return log


def handle_message(update: dict, bot: telegram.Bot, agents: list) -> str:
    text = (update.get("message", {}).get("text") or "").strip()
    if not text:
        return "boş mesaj"
    if text.startswith("/"):
        return handle_command(text, bot)

    editing = queue.by_status(queue.EDITING)
    if not editing:
        bot.send_message(
            "Hazırda redaktə gözləyən post yoxdur.\n"
            "Əmrlər üçün: /help"
        )
        return "redaktə rejimində post yoxdur"

    item = editing[-1]
    bot.send_message("✏️ Düzəliş tətbiq olunur…")
    try:
        data = editor.apply_instruction(item.post, item.first_comment, text, agents)
        item.post = data.get("post", item.post)
        item.first_comment = data.get("first_comment") or item.first_comment
        item.status = queue.PENDING
        item.note("edited", text[:120])
        queue.save(item)
        changes = "\n".join(f"• {_esc(c)}" for c in data.get("changes", [])[:4])
        warning = data.get("warning") or ""
        msg = f"✏️ <b>Düzəliş edildi</b>\n{changes}"
        if warning:
            msg += f"\n\n⚠️ <i>{_esc(warning)}</i>"
        bot.send_message(msg)
        item.telegram_message_id = bot.send_message(render_post(item), keyboard(item))
        queue.save(item)
        return f"{item.id}: redaktə tətbiq edildi"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Redaktə alınmadı: {_esc(str(exc))[:150]}")
        return f"{item.id}: redaktə xətası — {exc}"


HELP = """<b>Əmrlər</b>

/topic &lt;link&gt; — <b>öz tapdığınız linkdən post yaz</b>
/preview — növbəti yayımlanacaq postu göstər
/status — bank, növbəti yayım, rejim
/bank — bankdakı postların siyahısı
/pause · /resume — məzuniyyət rejimi
/skip — gözləyən postu keç
/help — bu siyahı

<b>Düzəliş</b>: «✏️ Mətni dəyiş» düyməsini basıb adi cümlə ilə yazın."""


def _topic_command(text: str, bot: telegram.Bot) -> str:
    """/topic <link> — istifadəçinin göndərdiyi linkdən post hazırlayır."""
    import re

    match = re.search(r"https?://\S+", text)
    if not match:
        bot.send_message(
            "🔗 Link göndərin:\n<code>/topic https://example.com/article</code>\n\n"
            "<i>Sistem həmin məqaləni oxuyub ondan post hazırlayacaq.</i>"
        )
        return "topic: link yoxdur"

    url = match.group(0).rstrip(".,;)")
    bot.send_message(
        "⏳ <b>Post hazırlanır…</b>\n"
        f"<i>{_esc(url[:80])}</i>\n\n"
        "Tədqiqat, yazı, yoxlama və şəkil — <b>təxminən 3 dəqiqə</b>."
    )
    try:
        result = pipeline.run_from_url(url, verbose=False)
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Alınmadı: {_esc(str(exc))[:250]}")
        return f"topic: xəta — {exc}"

    if not result.ok:
        bot.send_message(f"⚠️ Post hazırlanmadı:\n<i>{_esc(result.error)[:250]}</i>")
        return f"topic: {result.error}"

    image_path = image_label = alt_text = ""
    director: dict = {}
    try:
        agents: list = []
        director = images.direct(result.post, result.research, agents)
        rungs = images.plan(director)
        cand = images.produce(director, 0, rungs, result.run_id, agents,
                              fallback_query=director.get("pexels_query", ""))
        if not cand.error:
            image_path, image_label = cand.path, cand.label
            alt_text = director.get("alt_text", "")
    except Exception:  # noqa: BLE001 — şəkil postu bloklamamalıdır
        pass

    item = queue.enqueue(
        item_id=result.run_id, post=result.post,
        first_comment=result.first_comment, hashtags=result.hashtags,
        chosen=result.chosen, scores=result.scores,
        image_path=image_path, image_label=image_label, alt_text=alt_text,
        research=result.research, angles=result.angles,
        chosen_angle_id=result.chosen_angle_id, director=director,
    )
    send_for_approval(item, bot)
    return f"topic: {result.run_id} hazırlandı ({result.scores.get('overall')}/10)"


def handle_command(text: str, bot: telegram.Bot) -> str:
    cmd = text.split()[0].lower().lstrip("/").split("@")[0]

    if cmd in ("help", "start"):
        bot.send_message(HELP)
        return "help"

    if cmd == "status":
        st = queue.stats()
        paused = settings().get("paused")
        lines = [
            f"🏦 Bankda: <b>{st['bank_size']}</b>",
            f"⏳ Açıq: <b>{st['open']}</b>",
            f"📦 Ümumi: {st['total']}",
            f"⏸ Rejim: {'<b>dayandırılıb</b>' if paused else 'aktiv'}",
        ]
        upcoming = sorted(queue.by_status(queue.SCHEDULED),
                          key=lambda i: i.scheduled_for or "")
        if upcoming:
            lines.append(f"🕐 Növbəti yayım: "
                         f"<b>{timefmt.fmt(upcoming[0].scheduled_for)}</b>")
        bot.send_message("\n".join(lines))
        return "status"

    if cmd == "bank":
        items = queue.bank()
        if not items:
            bot.send_message("🏦 Bank boşdur.")
            return "bank boş"
        lines = ["🏦 <b>Bankdakı postlar</b>", ""]
        for item in items[:10]:
            when = f" · {timefmt.short(item.scheduled_for)}" if item.scheduled_for else ""
            lines.append(f"• {_esc(item.chosen.get('title', item.id)[:48])}{when}")
        bot.send_message("\n".join(lines))
        return "bank siyahısı"

    if cmd in ("pause", "resume"):
        paused = cmd == "pause"
        set_setting("paused", paused)
        bot.send_message("⏸ Dayandırıldı." if paused else "▶️ Davam edir.")
        return cmd

    if cmd == "topic":
        return _topic_command(text, bot)

    if cmd == "preview":
        scheduled = sorted(queue.by_status(queue.SCHEDULED, queue.APPROVED),
                           key=lambda i: i.scheduled_for or "9")
        if not scheduled:
            bot.send_message("Cədvəldə və bankda post yoxdur.")
            return "preview: boş"
        item = scheduled[0]
        if item.image_path and pathlib.Path(item.image_path).exists():
            try:
                bot.send_photo(item.image_path, f"🖼 {_esc(item.image_label)}")
            except Exception:  # noqa: BLE001
                pass
        bot.send_message(render_post(item), keyboard(item))
        return f"preview: {item.id}"

    if cmd == "skip":
        open_items = queue.open_items()
        if not open_items:
            bot.send_message("Gözləyən post yoxdur.")
            return "keçiləcək post yoxdur"
        item = open_items[-1]
        queue.set_status(item, queue.SKIPPED, "/skip əmri")
        bot.send_message("❌ Keçildi.")
        return f"{item.id}: /skip"

    bot.send_message(f"Naməlum əmr: {_esc(cmd)}\n{HELP}")
    return f"naməlum əmr: {cmd}"


def process(bot: telegram.Bot, agents: list | None = None,
            poll_timeout: int = 0) -> list[str]:
    """Bütün gözləyən yeniləmələri emal edir.

    `poll_timeout > 0` — uzun polling: Telegram yeniləmə gələnə qədər
    gözləyir, ona görə cavab dərhal olur.
    """
    agents = agents if agents is not None else []
    log: list[str] = []
    for update in bot.get_updates(timeout=poll_timeout):
        try:
            if "callback_query" in update:
                log.append(handle_callback(update, bot, agents))
            elif "message" in update:
                log.append(handle_message(update, bot, agents))
        except Exception as exc:  # noqa: BLE001 — bir yeniləmə döngəni sındırmır
            log.append(f"xəta: {type(exc).__name__}: {exc}")
    return log

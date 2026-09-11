"""Telegram təsdiq döngəsi: mesaj, düymələr, cavabların emalı.

Axın: post hazır → Telegram-a şəkil + mətn + düymələr → siz basırsınız →
poll bunu tutur → status dəyişir (bank / cədvəl / keçildi).
"""
from __future__ import annotations

import html
import json
import pathlib

from . import config, editor, images, linkedin, pipeline, preview, proposals, publisher, queue, store, telegram, timefmt

SETTINGS = config.STATE_DIR / "settings.json"

ACTIONS = {
    "ok": "✅ Yayımla",
    "now": "⚡ İndi yayımla",
    "bank": "🏦 Banka at",
    "img": "🔄 Başqa şəkil",
    "photo": "📷 Real foto",
    "rw": "🔄 Yenidən yaz",
    "ed": "✏️ Mətni dəyiş",
    "skip": "❌ Keç",
}


# --- parametrlər ------------------------------------------------------

def settings() -> dict:
    return store.read_json(SETTINGS, {"paused": False}) or {"paused": False}


def set_setting(key: str, value) -> dict:
    data = settings()
    data[key] = value
    store.write_json(SETTINGS, data)
    return data


# --- mesaj qurulması --------------------------------------------------

def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def keyboard(item: queue.Item) -> list:
    return [
        [{"text": ACTIONS["ok"], "callback_data": f"a|{item.id}|ok"},
         {"text": ACTIONS["bank"], "callback_data": f"a|{item.id}|bank"}],
        [{"text": ACTIONS["now"], "callback_data": f"a|{item.id}|now"}],
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
        "photo": ("⏳ <b>Foto variantları hazırlanır…</b>\n"
                  "<i>axtarış + seçim — təxminən 1-2 dəqiqə</i>"),
        "rw": "⏳ <b>Post yenidən yazılır…</b>\n<i>təxminən 1 dəqiqə</i>",
        "ok": "⏳ <b>Təsdiqlənir…</b>",
        "bank": "⏳ <b>Banka atılır…</b>",
    }
    # Bələdçili əmrlərin təsdiqi
    if action == "cancelask":
        clear_pending()
        bot.answer_callback(cq["id"], "Ləğv edildi")
        try:
            bot.edit_markup(cq["message"]["message_id"], None)
        except Exception:  # noqa: BLE001
            pass
        bot.send_message("↩️ Ləğv edildi.")
        return "ləğv edildi"

    if action in ("donow", "doundo", "doskip"):
        target = queue.get(item_id)
        if not target:
            bot.answer_callback(cq["id"], "Post tapılmadı")
            return f"post tapılmadı: {item_id}"
        bot.answer_callback(cq["id"], "İcra olunur…")
        try:
            bot.edit_markup(cq["message"]["message_id"], None)
        except Exception:  # noqa: BLE001
            pass
        if action == "donow":
            return _now_command(bot)
        if action == "doundo":
            return _undo_command(bot)
        queue.set_status(target, queue.SKIPPED, "/skip təsdiqi")
        bot.send_message("❌ Keçildi.")
        return f"{item_id}: keçildi"

    # Mövzu seçimi — bu, növbə elementi deyil
    if action.startswith("pick"):
        return _handle_pick(item_id, action, cq, bot)

    # Link təklifinə cavab — bu, növbə elementi deyil
    if action == "mktopic":
        url = _recall_url(item_id)
        bot.answer_callback(cq["id"], "Başladım…")
        if not url:
            bot.send_message("⚠️ Link yaddaşdan silinib, yenidən göndərin.")
            return "link tapılmadı"
        return _topic_command(f"/topic {url}", bot)

    if action == "dropurl":
        bot.answer_callback(cq["id"], "Ləğv edildi")
        bot.edit_markup(cq["message"]["message_id"], None)
        return "link ləğv edildi"

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

    if action in ("now", "nowf"):
        return _publish_now(item, cq, bot, force=(action == "nowf"))

    if action == "nowx":
        bot.answer_callback(cq["id"], "Ləğv edildi")
        bot.send_message("❌ Dərhal yayım ləğv edildi — post növbədə qalır.")
        return f"{item_id}: dərhal yayım ləğv edildi"

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
        return _photo_album(item, cq, bot, agents)

    if action.startswith("useimg"):
        return _use_image(item, int(action.replace("useimg", "")), cq, bot)

    if action == "rw":
        return _rewrite(item, cq, bot, agents)

    if action == "del":
        return _undo_publish(item, cq, bot)

    bot.answer_callback(cq["id"], "Naməlum əmr")
    return f"naməlum əməliyyat: {action}"


def _photo_album(item: queue.Item, cq: dict, bot: telegram.Bot,
                 agents: list) -> str:
    """Üç fotonu BİR mesajda göndərir — təkrar düymə basmağa ehtiyac yoxdur."""
    bot.answer_callback(cq["id"], "Üç variant hazırlanır…")
    try:
        director = dict(item.director or images.load_manifest(item.id)["director"])
        director["_post"] = item.post          # model seçimi üçün kontekst
        rungs = images.plan(director)
        photo_rungs = [i for i, (kind, _) in enumerate(rungs) if kind == "pexels"]
        if not photo_rungs:
            bot.send_message("📷 Foto variantı yoxdur "
                             "<i>(foto mənbələri konfiqurasiya olunmayıb)</i>")
            return f"{item.id}: foto pilləsi yoxdur"

        made, paths = [], []
        for rung in photo_rungs[:3]:
            cand = images.produce(director, rung, rungs, item.id, agents)
            if not cand.error and cand.path:
                made.append((rung, cand))
                paths.append(cand.path)
        if not paths:
            bot.send_message("📷 Uyğun foto tapılmadı.")
            return f"{item.id}: foto tapılmadı"

        caption = ["📷 <b>Foto variantları</b>", ""]
        for i, (_, cand) in enumerate(made):
            caption.append(f"{NUMERALS[i]} <i>{_esc(cand.label[:70])}</i>")
        bot.send_media_group(paths, "\n".join(caption))
        row = [{"text": NUMERALS[i], "callback_data": f"a|{item.id}|useimg{rung}"}
               for i, (rung, _) in enumerate(made)]
        # Seçimləri yaddaşda saxlayırıq ki, «useimg» hansı fayl olduğunu bilsin
        _remember_choices(item.id, {str(r): c.path for r, c in made})
        bot.send_message("Hansını işlədək?", [row, [
            {"text": "🖼 Claude dizaynı", "callback_data": f"a|{item.id}|img"},
        ]])
        return f"{item.id}: {len(paths)} foto albom kimi göndərildi"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Foto axtarışı alınmadı: {_esc(str(exc))[:150]}")
        return f"{item.id}: foto xətası — {exc}"


CHOICE_STORE = config.STATE_DIR / "image_choices.json"


def _remember_choices(item_id: str, mapping: dict) -> None:
    data = store.read_json(CHOICE_STORE, {}) or {}
    data[item_id] = mapping
    store.write_json(CHOICE_STORE, dict(list(data.items())[-20:]), indent=None)


def _use_image(item: queue.Item, rung: int, cq: dict, bot: telegram.Bot) -> str:
    """Albomdan seçilmiş fotonu posta təyin edir."""
    bot.answer_callback(cq["id"], "Seçildi")
    data = (store.read_json(CHOICE_STORE, {}) or {}).get(item.id, {})
    path = data.get(str(rung), "")
    if not path or not pathlib.Path(path).exists():
        bot.send_message("⚠️ Şəkil tapılmadı, yenidən axtarın.")
        return f"{item.id}: şəkil tapılmadı"

    item.image_path = queue._persist_image(item.id, path) or path
    item.image_rung, item.image_label = rung, f"Foto #{rung}"
    item.note("image_chosen", f"albomdan #{rung}")
    queue.save(item)
    bot.send_message(f"✅ <b>Şəkil seçildi.</b>")
    item.telegram_message_id = bot.send_message(render_post(item), keyboard(item))
    queue.save(item)
    return f"{item.id}: albomdan şəkil seçildi (#{rung})"


def _next_image(item: queue.Item, cq: dict, bot: telegram.Bot, agents: list,
                kind: str | None = None) -> str:
    """Növbəti şəkil variantı. `kind` verilsə birbaşa həmin növə keçir."""
    bot.answer_callback(
        cq["id"], "Foto axtarılır…" if kind == "pexels" else "Başqa şəkil hazırlanır…"
    )
    try:
        director = dict(item.director or images.load_manifest(item.id)["director"])
        director["_post"] = item.post
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


def _publish_now(item: queue.Item, cq: dict, bot: telegram.Bot, *,
                 force: bool = False) -> str:
    """Postu cədvəli gözləmədən DƏRHAL yayımlayır.

    Sürət həddi burada BLOKLAMIR, amma xəbərdarlıq edib təsdiq istəyir:
    düyməni basan istifadəçi öz niyyətini bildirir, avtomatik bank isə
    həddə tabe qalır (bax `pick_due`). İkinci basış (`nowf`) həddi keçir.
    """
    if item.status == queue.PUBLISHED:
        bot.answer_callback(cq["id"], "Artıq yayımlanıb")
        bot.send_message("ℹ️ Bu post artıq yayımlanıb.")
        return f"{item.id}: artıq yayımlanıb"

    token = linkedin.load_token()
    if not token or token.expired:
        bot.answer_callback(cq["id"], "Token yoxdur")
        bot.send_message("⚠️ LinkedIn tokeni yoxdur/bitib.\n"
                         "<code>make li-renew</code>")
        return f"{item.id}: token yoxdur"

    blocked = publisher.score_block(item)
    if blocked:
        bot.answer_callback(cq["id"], "Bal aşağıdır")
        bot.send_message(f"⚠️ {_esc(blocked)}")
        return f"{item.id}: bal bloku — {blocked}"

    limit = publisher.rate_limit_block()
    if limit and not force:
        bot.answer_callback(cq["id"], "Hədd pozulur")
        bot.send_message(
            f"⚠️ <b>Sürət həddi</b>\n<i>{_esc(limit)}</i>\n\n"
            "Bu, təsadüfi çoxlu yayımın qarşısını alan qorumadır.\n"
            "<b>Yenə də indi yayımlamaq istəyirsiniz?</b>",
            [[{"text": "⚡ Bəli, yayımla", "callback_data": f"a|{item.id}|nowf"},
              {"text": "❌ Ləğv", "callback_data": f"a|{item.id}|nowx"}]])
        return f"{item.id}: hədd təsdiqi gözlənilir — {limit}"

    bot.answer_callback(cq["id"], "Yayımlanır…")
    if item.telegram_message_id:
        bot.edit_markup(item.telegram_message_id, None)
    bot.send_message(f"⏳ <b>Yayımlanır…</b>\n"
                     f"<i>{_esc(item.chosen.get('title', '')[:60])}</i>")
    try:
        with publisher.Lock():
            result = publisher.publish_item(item, token)
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Yayım alınmadı: {_esc(str(exc))[:200]}")
        return f"{item.id}: yayım xətası — {exc}"
    notify_published(queue.get(item.id) or item, result, bot)
    return f"{item.id}: düymə ilə dərhal yayımlandı"


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
        if label == "24saat":
            bot.send_message(
                "📊 <b>Dünənki post necə keçdi?</b>\n"
                f"<i>{_esc(item.chosen.get('title', '')[:60])}</i>\n\n"
                "LinkedIn statistikasına baxıb <b>baxış sayını</b> yazın "
                "(sadəcə rəqəm, məs. <code>340</code>).\n\n"
                "<i>Sistem bunu yığır və zamanla hansı mövzu/rakursun "
                "işlədiyini öyrənir. LinkedIn API bu məlumatı vermir — "
                "yalnız siz verə bilərsiniz.</i>"
            )
        else:
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
    # Gözləyən əmr varsa cavab ona aiddir (əmr yazılmayıbsa)
    pending = get_pending()
    if pending and not text.startswith("/"):
        action = pending["action"]
        clear_pending()
        if action == "edit":
            return _apply_edit(text, bot)
        if action == "topic":
            return _topic_command(f"/topic {text}", bot)

    if text.startswith("/"):
        return handle_command(text, bot)

    # Nəticə gözlənilirsə və mesaj rəqəmdirsə — göstərici kimi yazırıq
    import re as _re

    numeric = _re.fullmatch(r"[\s]*(\d[\d\s.,]{0,8})[\s]*", text)
    if numeric:
        target = publisher.awaiting_metrics()
        if target:
            views = int(_re.sub(r"[^\d]", "", numeric.group(1)))
            target.metrics = {"views": views,
                              "recorded_at": timefmt.now().isoformat()}
            target.note("metrics", f"{views} baxış")
            queue.save(target)
            report = publisher.performance_report()
            lines = [f"📊 <b>{views} baxış</b> yadda saxlanıldı."]
            if report["samples"] >= 3 and report["by_angle"]:
                best = report["by_angle"][0]
                lines += ["", f"<i>Ən yaxşı rakurs: <b>{best['key']}</b> — "
                              f"orta {best['avg']} baxış ({best['n']} post)</i>"]
            elif report["samples"] < 3:
                lines += ["", f"<i>{3 - report['samples']} post daha lazımdır ki, "
                              "hansı rakursun işlədiyini deyə bilim.</i>"]
            bot.send_message("\n".join(lines))
            return f"{target.id}: {views} baxış qeyd edildi"

    editing = queue.by_status(queue.EDITING)
    if editing:
        return _apply_edit(text, bot)

    # Redaktə gözləmirsə və mesajda link varsa — post təklif edirik.
    # Əmr yazmağa ehtiyac yoxdur: linki bota atmaq kifayətdir.
    if not editing:
        import re

        match = re.search(r"https?://\S+", text)
        if match:
            url = match.group(0).rstrip(".,;)")
            token = _remember_url(url)
            bot.send_message(
                f"🔗 <b>Link gördüm</b>\n<i>{_esc(url[:90])}</i>\n\n"
                "Bundan post yazım?",
                [[{"text": "✍️ Bəli, yaz", "callback_data": f"a|{token}|mktopic"},
                  {"text": "❌ Yox", "callback_data": f"a|{token}|dropurl"}]],
            )
            return f"link təklifi: {url[:60]}"

        bot.send_message(
            "Hazırda redaktə gözləyən post yoxdur.\n\n"
            "💡 <b>Link atsanız</b>, ondan post yaza bilərəm.\n"
            "Əmrlər üçün: /help"
        )
        return "redaktə rejimində post yoxdur"

    return _apply_edit(text, bot)


def _apply_edit(text: str, bot: telegram.Bot, agents: list | None = None) -> str:
    """Sərbəst mətnlə postu düzəldir."""
    agents = agents if agents is not None else []
    candidates = queue.by_status(queue.EDITING) or queue.open_items()
    if not candidates:
        bot.send_message("Düzəldiləcək post yoxdur.")
        return "redaktə: post yoxdur"

    item = candidates[-1]
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


# Telegram-da qeydiyyatdan keçən əmrlər — «/» yazanda siyahı çıxır.
# Sıra əhəmiyyətlidir: ən çox işlədilənlər yuxarıda.
COMMAND_CATALOG = [
    ("topic", "🔗 Linkdən post yaz"),
    ("edit", "✏️ Gözləyən postu düzəlt"),
    ("preview", "👁 Növbəti postu göstər"),
    ("now", "🚀 Bankdan indi yayımla"),
    ("undo", "🗑 Son postu sil"),
    ("skip", "❌ Gözləyən postu keç"),
    ("status", "📊 Bank və növbəti yayım"),
    ("bank", "🏦 Bankdakı postlar"),
    ("health", "🩺 Sistem yoxlaması"),
    ("pause", "⏸ Dayandır"),
    ("resume", "▶️ Davam et"),
    ("help", "❓ Kömək"),
]

# Giriş gözləyən əmrlər: «/edit» yazılsa sual verilir, cavab gözlənilir.
PENDING_FILE = config.STATE_DIR / "pending_action.json"
PENDING_TTL_MINUTES = 20

PROMPTS = {
    "edit": ("✏️ <b>Nə dəyişsin?</b>\n\n"
             "<i>Adi cümlə ilə yazın:</i>\n"
             "<i>«tonu yumşalt, ikinci bəndi at, sondakı sual daha konkret olsun»</i>"),
    "topic": ("🔗 <b>Linki göndərin</b>\n\n"
              "<i>Həmin məqaləni oxuyub ondan post hazırlayacağam.</i>"),
}


def set_pending(action: str, **context) -> None:
    store.write_json(PENDING_FILE, {
        "action": action, "asked_at": timefmt.now().isoformat(), **context})


def get_pending() -> dict:
    data = store.read_json(PENDING_FILE, {}) or {}
    if not data.get("action"):
        return {}
    try:
        asked = timefmt.local(data["asked_at"])
        if asked and (timefmt.now() - asked).total_seconds() > PENDING_TTL_MINUTES * 60:
            clear_pending()
            return {}
    except Exception:  # noqa: BLE001
        pass
    return data


def clear_pending() -> None:
    PENDING_FILE.unlink(missing_ok=True)


def ask_for(action: str, bot: telegram.Bot) -> str:
    """Əmr giriş tələb edirsə soruşur və cavabı gözləyir."""
    set_pending(action)
    bot.send_message(
        PROMPTS.get(action, "Nə yazmaq istəyirsiniz?"),
        [[{"text": "❌ Ləğv et", "callback_data": f"a|-|cancelask"}]])
    return f"{action}: giriş gözlənilir"


HELP = ("<b>Əmrlər</b>\n\n"
        + "\n".join(f"/{c} — {d}" for c, d in COMMAND_CATALOG)
        + "\n\n💡 <i>«/» yazsanız siyahı avtomatik çıxır.</i>"
        + "\n💡 <i>Arqument yazmasanız soruşacağam — sadəcə cavab verin.</i>"
        + "\n💡 <i>Link atsanız, ondan post yaza bilərəm.</i>"
        + "\n💡 <i>Yayımdan sonra rəqəm yazsanız, baxış sayı kimi saxlayıram.</i>")


URL_STORE = config.STATE_DIR / "pending_urls.json"


def _remember_url(url: str) -> str:
    """Linki qısa açarla saxlayır — callback_data 64 bayt həddindədir."""
    import hashlib

    token = "u" + hashlib.sha1(url.encode()).hexdigest()[:10]
    data = store.read_json(URL_STORE, {}) or {}
    data[token] = url
    store.write_json(URL_STORE, dict(list(data.items())[-40:]), indent=None)
    return token


def _recall_url(token: str) -> str:
    return (store.read_json(URL_STORE, {}) or {}).get(token, "")


NUMERALS = ("1️⃣", "2️⃣", "3️⃣")


def _finish_and_send(result, bot: telegram.Bot) -> str:
    """Hazır postdan şəkil düzəldib növbəyə salır və təsdiqə göndərir."""
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
    return f"{result.run_id}: hazırlandı ({result.scores.get('overall')}/10)"


# --- Mövzu təklifi ----------------------------------------------------

def send_proposal(proposal, bot: telegram.Bot) -> None:
    """3 namizədi düymələrlə göndərir."""
    lines = ["📰 <b>Bu gün üçün namizədlər</b>", ""]
    row = []
    for index, cand in enumerate(proposal.candidates[:3]):
        sources_txt = ", ".join(cand.get("sources", [])[:3])
        lines += [
            f"{NUMERALS[index]} <b>{_esc(cand.get('title', '')[:80])}</b>",
            f"    <i>{_esc(sources_txt)} · {_esc(cand.get('pillar', ''))}</i>",
            f"    {_esc(cand.get('why', '')[:110])}",
            "",
        ]
        row.append({"text": NUMERALS[index],
                    "callback_data": f"a|{proposal.id}|pick{index}"})
    lines.append(f"<i>Cavab verməsəniz {proposals.AUTO_PICK_HOURS:.0f} saat sonra "
                 f"sistem özü seçəcək.</i>")

    keyboard = [row, [
        {"text": "🎲 Sən seç", "callback_data": f"a|{proposal.id}|pickauto"},
        {"text": "❌ Bu gün keç", "callback_data": f"a|{proposal.id}|picknone"},
    ]]
    proposal.telegram_message_id = bot.send_message("\n".join(lines), keyboard)
    proposals.save(proposal)


def _handle_pick(pid: str, action: str, cq: dict, bot: telegram.Bot) -> str:
    proposal = proposals.get(pid)
    if not proposal:
        bot.answer_callback(cq["id"], "Təklif tapılmadı")
        return f"təklif tapılmadı: {pid}"
    if proposal.status != proposals.OPEN:
        bot.answer_callback(cq["id"], "Bu təklif artıq bağlanıb")
        bot.edit_markup(proposal.telegram_message_id, None)
        return f"{pid}: artıq bağlanıb"

    if action == "picknone":
        proposals.expire(proposal)
        bot.answer_callback(cq["id"], "Keçildi")
        bot.edit_markup(proposal.telegram_message_id, None)
        bot.send_message("❌ Bu gün post hazırlanmayacaq.")
        return f"{pid}: keçildi"

    index = 0 if action == "pickauto" else int(action.replace("pick", ""))
    index = max(0, min(index, len(proposal.candidates) - 1))
    title = proposal.candidates[index].get("title", "")

    bot.answer_callback(cq["id"], "Yazılır…")
    bot.edit_markup(proposal.telegram_message_id, None)
    bot.send_message(
        f"⏳ <b>Post yazılır…</b>\n<i>{_esc(title[:70])}</i>\n\n"
        "Tədqiqat, yazı, yoxlama və şəkil — <b>təxminən 3 dəqiqə</b>."
    )
    proposals.mark_picked(proposal, index,
                          "auto" if action == "pickauto" else "user")
    try:
        result = pipeline.write_from_proposal(proposal, index, verbose=False)
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Alınmadı: {_esc(str(exc))[:200]}")
        return f"{pid}: xəta — {exc}"
    if not result.ok:
        bot.send_message(f"⚠️ Post hazırlanmadı:\n<i>{_esc(result.error)[:200]}</i>")
        return f"{pid}: {result.error}"
    return _finish_and_send(result, bot)


def auto_pick_due(bot: telegram.Bot) -> list[str]:
    """Cavabsız qalmış təkliflər üçün sistem özü seçir — post günü boş keçməsin."""
    log = []
    for proposal in proposals.due_for_auto_pick():
        bot.send_message(
            f"🎲 <b>Cavab gəlmədi — özüm seçdim</b>\n"
            f"<i>{_esc(proposal.candidates[0].get('title', '')[:70])}</i>"
        )
        fake_cq = {"id": "auto", "message": {"message_id": proposal.telegram_message_id}}
        log.append(_handle_pick(proposal.id, "pickauto", fake_cq, bot))
    return log


def _now_command(bot: telegram.Bot) -> str:
    """Bankdan dərhal yayımlayır."""
    token = linkedin.load_token()
    if not token or token.expired:
        bot.send_message("⚠️ LinkedIn tokeni yoxdur/bitib.\n"
                         "<code>make li-renew</code>")
        return "now: token yoxdur"
    candidates = publisher.pick_due(from_bank=True)
    if not candidates:
        bot.send_message("🏦 Bank boşdur — yayımlanacaq post yoxdur.")
        return "now: bank boş"

    item = candidates[0]
    blocked = publisher.score_block(item)
    if blocked:
        bot.send_message(f"⚠️ {_esc(blocked)}")
        return f"now: bloklandı — {blocked}"

    bot.send_message(f"⏳ <b>Yayımlanır…</b>\n"
                     f"<i>{_esc(item.chosen.get('title', '')[:60])}</i>")
    try:
        with publisher.Lock():
            result = publisher.publish_item(item, token)
        notify_published(queue.get(item.id) or item, result, bot)
        return f"{item.id}: /now ilə yayımlandı"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Yayım alınmadı: {_esc(str(exc))[:200]}")
        return f"now: xəta — {exc}"


def _undo_command(bot: telegram.Bot) -> str:
    """Son yayımlanan postu LinkedIn-dən silir."""
    published = [i for i in queue.by_status(queue.PUBLISHED) if i.linkedin_urn]
    published.sort(key=lambda i: i.published_at or "", reverse=True)
    if not published:
        bot.send_message("Silinəcək yayımlanmış post yoxdur.")
        return "undo: post yoxdur"

    item = published[0]
    token = linkedin.load_token()
    if not token or token.expired:
        bot.send_message("⚠️ LinkedIn tokeni yoxdur/bitib.")
        return "undo: token yoxdur"
    try:
        publisher.undo(item, token)
        bot.send_message(
            f"🗑 <b>Silindi</b>\n<i>{_esc(item.chosen.get('title', '')[:60])}</i>\n"
            f"<i>{timefmt.fmt(item.published_at)} yayımlanmışdı.</i>")
        return f"{item.id}: /undo ilə silindi"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Silinmədi: {_esc(str(exc))[:200]}")
        return f"undo: xəta — {exc}"


def _health_command(bot: telegram.Bot) -> str:
    """Terminal açmadan sistem yoxlaması."""
    from . import calibration, sources
    from .images import render, stock

    lines = ["🩺 <b>Sistem yoxlaması</b>", ""]

    items, errors = sources.fetch_all(max_age_hours=48)
    mark = "✅" if len(errors) < len(sources.FEEDS) / 2 else "🔴"
    lines.append(f"{mark} Mənbələr: {len(items)} xəbər · "
                 f"{len(sources.FEEDS) - len(errors)}/{len(sources.FEEDS)} işlək")

    token = linkedin.load_token()
    if not token:
        lines.append("⚪️ LinkedIn: giriş yoxdur")
    elif token.expired:
        lines.append("🔴 <b>LinkedIn tokeni bitib</b> — make li-renew")
    elif token.expiring_soon:
        lines.append(f"🟡 LinkedIn tokeni {token.days_left:.0f} gün sonra bitir")
    else:
        lines.append(f"✅ LinkedIn: {token.days_left:.0f} gün qalır")

    lines.append(f"✅ Foto mənbələri: {len(stock.active_providers())}")
    try:
        render.find_chrome()
        lines.append("✅ Şəkil rendering")
    except Exception:  # noqa: BLE001
        lines.append("🔴 Chrome tapılmadı — şəkil çəkilə bilmir")

    stuck = publisher.stuck_items()
    if stuck:
        lines.append(f"🔴 <b>{len(stuck)} yarımçıq yayım</b>")

    st = queue.stats()
    lines += ["", f"🏦 Bank: {st['bank_size']} · ⏳ Açıq: {st['open']}"]
    if approval_paused := settings().get("paused"):
        lines.append("⏸ <b>Sistem dayandırılıb</b> — /resume")

    cal = calibration.reminder_lines()
    if cal:
        lines += ["", "📝 <i>Kalibrləmə tamamlanmayıb</i>"]

    bot.send_message("\n".join(lines))
    return "health"


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

    return "topic: " + _finish_and_send(result, bot)


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

    if cmd == "now":
        candidates = publisher.pick_due(from_bank=True)
        if not candidates:
            bot.send_message("🏦 Bank boşdur — yayımlanacaq post yoxdur.")
            return "now: bank boş"
        item = candidates[0]
        bot.send_message(
            "🚀 <b>İndi yayımlansın?</b>\n\n"
            f"<i>{_esc(item.chosen.get('title', '')[:70])}</i>\n"
            f"bal {item.scores.get('overall', '?')}/10 · {len(item.post)} simvol",
            [[{"text": "✅ Bəli, yayımla", "callback_data": f"a|{item.id}|donow"},
              {"text": "❌ Yox", "callback_data": f"a|{item.id}|cancelask"}]])
        return "now: təsdiq gözlənilir"

    if cmd == "undo":
        published = [i for i in queue.by_status(queue.PUBLISHED) if i.linkedin_urn]
        published.sort(key=lambda i: i.published_at or "", reverse=True)
        if not published:
            bot.send_message("Silinəcək yayımlanmış post yoxdur.")
            return "undo: post yoxdur"
        item = published[0]
        bot.send_message(
            "🗑 <b>Bu post LinkedIn-dən silinsin?</b>\n\n"
            f"<i>{_esc(item.chosen.get('title', '')[:70])}</i>\n"
            f"{timefmt.fmt(item.published_at)} yayımlanıb\n\n"
            "<b>Bu əməliyyat geri qaytarıla bilməz.</b>",
            [[{"text": "🗑 Bəli, sil", "callback_data": f"a|{item.id}|doundo"},
              {"text": "❌ Yox", "callback_data": f"a|{item.id}|cancelask"}]])
        return "undo: təsdiq gözlənilir"

    if cmd == "health":
        return _health_command(bot)

    if cmd == "edit":
        parts_ = text.split(None, 1)
        if not queue.open_items() and not queue.by_status(queue.APPROVED):
            bot.send_message("Düzəldiləcək post yoxdur.")
            return "edit: post yoxdur"
        if len(parts_) < 2:
            return ask_for("edit", bot)
        return _apply_edit(parts_[1], bot)

    if cmd == "topic":
        import re as _re

        if not _re.search(r"https?://", text):
            return ask_for("topic", bot)
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
        bot.send_message(
            "❌ <b>Bu post keçilsin?</b>\n\n"
            f"<i>{_esc(item.chosen.get('title', '')[:70])}</i>",
            [[{"text": "❌ Bəli, keç", "callback_data": f"a|{item.id}|doskip"},
              {"text": "↩️ Saxla", "callback_data": f"a|{item.id}|cancelask"}]])
        return "skip: təsdiq gözlənilir"

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

"""Telegram təsdiq döngəsi: mesaj, düymələr, cavabların emalı.

Axın: post hazır → Telegram-a şəkil + mətn + düymələr → siz basırsınız →
poll bunu tutur → status dəyişir (bank / cədvəl / keçildi).
"""
from __future__ import annotations

import html
import json
import pathlib
from datetime import datetime, timezone

from . import config, editor, images, linkedin, llm, pipeline, preview, proposals, publisher, queue, sources, store, telegram, timefmt

SETTINGS = config.STATE_DIR / "settings.json"

ACTIONS = {
    "ok": "✅ Yayımla",
    "now": "⚡ İndi yayımla",
    "bank": "🏦 Banka at",
    "img": "🔄 Başqa şəkil",
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
    """Təsdiq düymələri GÖSTƏRİLƏN kartın NÖMRƏSİNİ daşıyır (`ok@1`).

    22.09.2026: istifadəçi kart #1-in altındakı ✅-i basdı, amma arada
    «Başqa şəkil» kart #2-ni cari etmişdi — təsdiq elementin O ANDAKI
    şəklinə düşdü və LinkedIn-ə kart #2 getdi. İndi düymə hansı şəkil
    üçün göstərilibsə yalnız onu təsdiqləyir; uyğun gəlməsə soruşur.

    24.09.2026: həmin qoruyucu PİLLƏ nömrəsi ilə işləyirdi və buna görə
    tam işləmirdi. Zəncirin sonundakı AI pilləsi təkrar-təkrar icra
    olunur (hər dəfə başqa şəkil), yəni iki fərqli kartın pilləsi EYNİ
    olur — qoruyucu fərqi görmürdü və axırıncı şəkil yayımlanırdı.
    İndi tag kart nömrəsidir; o, heç vaxt təkrarlanmır.
    """
    tag = f"@{item.image_card}"
    return [
        [{"text": ACTIONS["ok"], "callback_data": f"a|{item.id}|ok{tag}"},
         {"text": ACTIONS["bank"], "callback_data": f"a|{item.id}|bank{tag}"}],
        [{"text": ACTIONS["now"], "callback_data": f"a|{item.id}|now{tag}"}],
        [{"text": ACTIONS["img"], "callback_data": f"a|{item.id}|img"}],
        [{"text": ACTIONS["rw"], "callback_data": f"a|{item.id}|rw"},
         {"text": ACTIONS["ed"], "callback_data": f"a|{item.id}|ed"}],
        [{"text": ACTIONS["skip"], "callback_data": f"a|{item.id}|skip"}],
    ]


# Aqreqator = başqasının xəbərini yığan sayt. İlkin mənbə kimi zəifdir.
AGGREGATORS = ("techmeme.com", "news.google.com", "reddit.com",
               "news.ycombinator.com", "flipboard.com", "msn.com")

# Bundan köhnə xəbər LinkedIn-də «təzə xəbər» kimi təqdim edilə bilməz.
STALE_AFTER_HOURS = 48


def _host(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return (urlparse(url).hostname or "").replace("www.", "")
    except ValueError:
        return ""


def verification(item: queue.Item) -> list[str]:
    """Doğrulama bloku — HÖKM yox, YOXLANA BİLƏN sübutlar.

    İstifadəçinin tələbi (24.09.2026): «hər dəfə Telegram-da məlumatın
    təzə olub-olmadığını və uydurma olmadığını sübut et».

    Burada model çağırılmır: bütün rəqəmlər elementin içindəki
    məlumatdan hesablanır, ona görə həm pulsuzdur, həm də özü uydura
    bilmir. Blok üç sual cavablandırır — nə qədər təzədir, neçə müstəqil
    nəşr yazıb, faktların neçəsi linklə gəlib. Zəiflik varsa ⚠️ ilə açıq
    yazılır: məqsəd «təmizdir» deməkdir yox, nəyi öz gözünüzlə
    yoxlamalı olduğunuzu göstərməkdir.
    """
    chosen = item.chosen or {}
    research = item.research or {}
    lines: list[str] = ["🔎 <b>Doğrulama</b>"]
    warnings: list[str] = []

    # --- təzəlik ---
    published = timefmt.local(chosen.get("published")) if chosen.get("published") else None
    if published:
        age = (timefmt.now() - published).total_seconds() / 3600.0
        lines.append(f"🕒 Xəbər {age:.0f} saat əvvəl dərc olunub "
                     f"({timefmt.fmt(published)})")
        if age > STALE_AFTER_HOURS:
            warnings.append(f"xəbər {age:.0f} saatlıqdır — «təzə» kimi təqdim etməyin")
    else:
        warnings.append("mənbədə dərc tarixi yoxdur — təzəliyi yoxlanmayıb")

    # --- müstəqil əhatə ---
    sources = [s for s in (chosen.get("sources") or []) if s]
    count = int(chosen.get("source_count") or len(sources))
    if sources:
        lines.append(f"📰 {count} müstəqil nəşr: {_esc(', '.join(sources[:4]))}")
    if count < 2:
        # Yerli xəbərdə bu normaldır — yerli nəşrlər bir-birini təkrar etmir.
        if chosen.get("region") == "local":
            lines.append("<i>Yerli xəbər — tək mənbə burada adi haldır</i>")
        else:
            warnings.append("TƏK mənbə — heç bir müstəqil nəşr təsdiqləməyib")

    # --- ilkin mənbə ---
    primary = research.get("primary_source_url") or chosen.get("link") or ""
    if primary:
        host = _host(primary)
        lines.append(f"🔗 İlkin mənbə: <a href=\"{_esc(primary)}\">{_esc(host)}</a>")
        if host in AGGREGATORS:
            warnings.append(f"ilkin mənbə aqreqatordur ({host}) — əsl nəşrə keçin")
    else:
        warnings.append("ilkin mənbə linki yoxdur")

    # --- faktlar və rəqəmlər ---
    facts = research.get("facts") or []
    if facts:
        linked = sum(1 for f in facts if (f.get("source_url") or "").startswith("http"))
        low = sum(1 for f in facts if (f.get("confidence") or "").lower() == "low")
        # «6 faktın 4-ü» kimi yazmırıq: azərbaycanca şəkilçi son rəqəmin
        # səsinə görə dəyişir (4-ü, 6-sı, 9-u) və səhv variant gözə dəyir.
        lines.append(f"✅ Faktlar: {linked}/{len(facts)} mənbə linki ilə")
        if linked < len(facts):
            warnings.append(f"{len(facts) - linked} fakt linksizdir — yoxlanmayıb")
        if low:
            warnings.append(f"{low} faktın etibarı AŞAĞI qiymətləndirilib")
    else:
        warnings.append("heç bir fakt çıxarılmayıb — post tədqiqatsız yazılıb")

    numbers = research.get("numbers") or []
    if numbers:
        linked = sum(1 for n in numbers if (n.get("source_url") or "").startswith("http"))
        lines.append(f"🔢 Rəqəmlər: {linked}/{len(numbers)} linklə")
        if linked < len(numbers):
            warnings.append(f"{len(numbers) - linked} rəqəm linksizdir — postdan çıxarın")

    lines += [f"⚠️ {_esc(w)}" for w in warnings]
    if not warnings:
        lines.append("<i>Zəif nöqtə görünmür — yenə də linki bir açın.</i>")
    return lines


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
    # Doğrulama ƏN SONDA: postun özü oxunandan sonra gəlir və düymələrin
    # tam üstündədir — təsdiqdən əvvəl görünən son şey odur.
    parts += ["", *verification(item)]
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
    expected_card = None
    if "@" in action:                      # «ok@1» — kart #2 üçün göstərilmiş düymə
        action, tag = action.split("@", 1)
        try:
            expected_card = int(tag)
        except ValueError:
            expected_card = None

    # Ani geri əlaqə: uzun sürən əməliyyatlarda istifadəçi düymənin
    # işlədiyini dərhal görməlidir, yoxsa «heç nə olmur» hissi yaranır.
    WAIT_MESSAGES = {
        "imgjust": "⏳ <b>Yeni dizayn hazırlanır…</b>\n<i>təxminən 40 saniyə</i>",
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

    if action == "dopropose":
        bot.answer_callback(cq["id"], "Hazırlanır…")
        try:
            bot.edit_markup(cq["message"]["message_id"], None)
        except Exception:  # noqa: BLE001
            pass
        return _propose_command(bot)

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

    # Təsdiq baxılan şəklə aiddir: düymənin kartı cari kartdan fərqlidirsə
    # DAYAN və soruş — səssizcə başqa şəkil yayımlama.
    if expected_card is not None and expected_card != item.image_card \
            and item.status not in queue.TERMINAL_STATES:
        bot.answer_callback(cq["id"], "Şəkil dəyişib — hansı?")
        bot.send_message(
            f"⚠️ <b>Bu düymə kart #{expected_card + 1} üçün idi</b>, hazırkı şəkil isə "
            f"kart #{item.image_card + 1}-dir.\n<i>{_esc(item.image_label[:80])}</i>\n\n"
            "Hansı ilə davam edək?",
            [[{"text": f"🖼 Kart #{expected_card + 1}-ə qayıt",
               "callback_data": f"a|{item.id}|useimg{expected_card}"},
              {"text": f"➡️ Kart #{item.image_card + 1} ilə davam",
               "callback_data": f"a|{item.id}|showkb"}]])
        return f"{item.id}: təsdiq kartı uyğun deyil ({expected_card} ≠ {item.image_card})"

    if action == "showkb":
        bot.answer_callback(cq["id"], "")
        item.telegram_message_id = bot.send_message(render_post(item), keyboard(item))
        queue.save(item)
        return f"{item.id}: klaviatura yenidən göndərildi"

    # Köhnə mesajlarda düymələr qalır. Bitmiş posta təkrar basılsa,
    # əməliyyatı yenidən icra etmirik — sadəcə vəziyyəti xatırladırıq.
    if item.status in queue.TERMINAL_STATES and action not in ("del", "restore",
                                                              "dorestore"):
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
        return _ask_image_note(item, cq, bot)

    if action == "imgjust":               # «Sadəcə dəyiş» — rəysiz davam
        return _next_image(item, cq, bot, agents)

    if action == "photo":
        return _photo_album(item, cq, bot, agents)

    if action.startswith("useopt"):
        return _use_option(item, int(action.replace("useopt", "")), cq, bot, agents)
    if action == "imgevent":
        return _search_event(item, cq, bot, agents)
    if action == "imgcollage":
        return _make_collage(item, cq, bot, agents)
    if action == "imgtypo":
        # Köhnə mesajlardakı düymə: tipoqrafik dizayn həmişəlik rədd edilib
        bot.answer_callback(cq["id"], "Bu dizayn artıq yoxdur")
        return f"{item.id}: mətn kartı rədd edilib"

    if action.startswith("useimg"):        # arqument KART nömrəsidir
        return _use_image(item, int(action.replace("useimg", "")), cq, bot)

    if action == "rw":
        return _rewrite(item, cq, bot, agents)

    if action == "restore":
        return _ask_restore(item, cq, bot)

    if action == "dorestore":
        return _do_restore(item, cq, bot)

    if action == "del":
        return _undo_publish(item, cq, bot)

    bot.answer_callback(cq["id"], "Naməlum əmr")
    return f"naməlum əməliyyat: {action}"


def _photo_album(item: queue.Item, cq: dict, bot: telegram.Bot,
                 agents: list) -> str:
    """Üç fotonu BİR mesajda göndərir — təkrar düymə basmağa ehtiyac yoxdur."""
    bot.answer_callback(cq["id"], "Üç variant hazırlanır…")
    if (item.director or {}).get("visual_type") == "news":
        # Xəbər kartında variantlar müfəttişin qərarlarıdır — mənbə və növü ilə
        try:
            director = _director_for(item)
            images.plan(director, item.id, agents)       # seçim yoxdursa yaradır
            _send_options(item, bot, header="📷 <b>Foto variantları</b>")
            return f"{item.id}: seçimlər göndərildi"
        except Exception as exc:  # noqa: BLE001
            bot.send_message(f"⚠️ Seçimlər alınmadı: {_esc(str(exc))[:150]}")
            return f"{item.id}: seçim xətası — {exc}"
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

        # Hər variant AYRI kart kimi arxivlənir: albomdakı üç foto eyni
        # pillə növündən gəlir, ona görə pillə nömrəsi onları ayırmır.
        cards = [_remember_card(item.id, rung, cand.path, cand.label,
                                cand.credit or "")
                 for rung, cand in made]
        caption = ["📷 <b>Foto variantları</b>", ""]
        for i, (_, cand) in enumerate(made):
            caption.append(f"{NUMERALS[i]} <i>{_esc(cand.label[:70])}</i>")
        bot.send_media_group(paths, "\n".join(caption))
        row = [{"text": NUMERALS[i], "callback_data": f"a|{item.id}|useimg{card_no}"}
               for i, card_no in enumerate(cards)]
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


def _use_image(item: queue.Item, card_no: int, cq: dict, bot: telegram.Bot) -> str:
    """Saxlanmış kartı posta geri qaytarır."""
    bot.answer_callback(cq["id"], "Seçildi")
    card = _card(item.id, card_no)
    path = card.get("path", "")
    if not path or not pathlib.Path(path).exists():
        bot.send_message("⚠️ Şəkil tapılmadı, yenidən axtarın.")
        return f"{item.id}: şəkil tapılmadı"

    item.image_path = queue._persist_image(item.id, path) or path
    item.image_rung = int(card.get("rung", card_no))
    item.image_card = card_no
    item.image_label = card.get("label", "") or f"Kart #{card_no + 1}"
    item.image_credit = card.get("credit", "") or ""
    item.note("image_chosen", f"kart #{card_no + 1}-ə qayıdıldı")
    queue.save(item)
    # Seçilən şəkli TƏKRAR göstəririk: istifadəçi nəyi təsdiqlədiyini
    # gözü ilə görməlidir, yaddaşına güvənməməlidir.
    try:
        bot.send_photo(item.image_path, f"🖼 {_esc(item.image_label)}")
    except Exception:  # noqa: BLE001 — şəkil göndərilməsə də seçim qüvvədədir
        pass
    bot.send_message("✅ <b>Şəkil seçildi.</b>")
    item.telegram_message_id = bot.send_message(render_post(item), keyboard(item))
    queue.save(item)
    return f"{item.id}: kart #{card_no + 1} seçildi"


def _ask_image_note(item: queue.Item, cq: dict, bot: telegram.Bot) -> str:
    """«Başqa şəkil» basılanda əvvəlcə NƏYİN dəyişməsini soruşur.

    İstifadəçinin tələbi (24.09.2026): şəkil bəyənilmirsə, sistem
    kor-koranə növbəti variantı yox, İSTƏNİLƏN variantı verməlidir.
    Yazmaq istəməyən üçün «🎲 Sadəcə dəyiş» düyməsi qalır — köhnə
    davranış bir basışla əlçatandır.
    """
    bot.answer_callback(cq["id"], "")
    set_pending("imgnote", item_id=item.id)
    bot.send_message(
        "🎨 <b>Bu şəkildə nə dəyişsin, nə qalsın?</b>\n\n"
        "<i>Adi cümlə ilə yazın:</i>\n"
        "<i>«hiss çox soyuqdur, daha canlı olsun — amma ofis mühiti qalsın»</i>\n"
        "<i>«insan olmasın, sadəcə avadanlıq»</i>",
        [[{"text": "🎲 Sadəcə dəyiş", "callback_data": f"a|{item.id}|imgjust"}],
         [{"text": "❌ Ləğv et", "callback_data": "a|-|cancelask"}]])
    return f"{item.id}: şəkil rəyi gözlənilir"


IMAGE_BRIEF_PROMPT = (
    "Sən şəkil direktorunun köməkçisisən. Sahibi çəkilən şəkil haqqında "
    "azərbaycanca rəy yazır. Vəzifən: həmin rəyi şəkil modelinə veriləcək "
    "QISA ingiliscə göstərişə çevirmək.\n\n"
    "Qaydalar:\n"
    "- Yalnız görünən şeylər: işıq, rəng, əhval, kadr, məkan, obyektlər\n"
    "- Ən çox 25 söz, bir cümlə, sonda nöqtə\n"
    "- Mətn, yazı, loqo, brend İSTƏMƏ — model onları səhv çəkir\n"
    "- İzah yazma, yalnız göstərişin özünü qaytar\n\n"
    "Nümunə: «hiss çox soyuqdur, daha canlı olsun, amma ofis qalsın» → "
    "warmer natural light, livelier mood, keep the modern office setting."
)


def _image_brief(note: str, agents: list) -> str:
    """Azərbaycanca rəyi ingiliscə şəkil göstərişinə çevirir.

    `gpt-image-1` ingiliscə sorğuya xeyli yaxşı reaksiya verir. Çevirmə
    alınmasa rəy OLDUĞU KİMİ işlənir — funksiya modelin əlçatanlığından
    asılı olmamalıdır.
    """
    try:
        res = llm.call_agent("image_brief", IMAGE_BRIEF_PROMPT, note,
                             model=config.MODEL_SCOUT, expect_json=False,
                             retries=1, timeout=120)
        if agents is not None:
            agents.append({"name": "image_brief", "model": res.model,
                           "ok": res.ok, "total_tokens": res.total_tokens,
                           "cost_usd": res.cost_usd})
        text = (res.text or "").strip() if res.ok else ""
        return text[:220] or note
    except Exception:  # noqa: BLE001 — çevirmə məcburi deyil
        return note


def _apply_image_note(text: str, item_id: str, bot: telegram.Bot,
                      agents: list) -> str:
    """Rəyi elementə yazır və şəkli həmin rəylə yenidən qurur."""
    item = queue.get(item_id)
    if not item:
        bot.send_message("⚠️ Post tapılmadı.")
        return f"şəkil rəyi: post tapılmadı ({item_id})"

    item.image_note = text.strip()[:400]
    item.image_brief = _image_brief(item.image_note, agents)
    item.note("image_note", item.image_note)
    queue.save(item)

    # Rəy YALNIZ AI fonunda tətbiq oluna bilir: arxiv fotolarını sözlə
    # dəyişmək mümkün deyil, onlar hazır şəkillərdir. Bunu gizlətmirik.
    target = None
    try:
        rungs = images.plan(_director_for(item), item.id, agents)
        target = next((i for i, (k, p) in enumerate(rungs)
                       if k == "news" and p == "ai"), None)
    except Exception:  # noqa: BLE001 — plan alınmasa adi zəncirlə davam
        rungs = []

    bot.send_message(f"🎨 <b>Rəyiniz yazıldı.</b>\n<i>{_esc(item.image_note[:120])}</i>")
    if target is None:
        bot.send_message(
            "ℹ️ <i>Bu postun şəkilləri foto arxivindən gəlir (hekayədə real "
            "şəxslər var və ya AI açarı yoxdur) — mətnlə idarə olunmur. "
            "Növbəti variantı göstərirəm; rəyiniz AI fonu mümkün olan "
            "kimi işə düşəcək.</i>")
        return _next_image(item, {"id": "note"}, bot, agents)

    bot.send_message("⏳ <b>Rəyinizə görə yeni şəkil çəkilir…</b>\n"
                     "<i>təxminən bir dəqiqə · ~$0.03</i>")
    return _next_image(item, {"id": "note"}, bot, agents, target_rung=target)


def _next_image(item: queue.Item, cq: dict, bot: telegram.Bot, agents: list,
                kind: str | None = None, target_rung: int | None = None) -> str:
    """Növbəti şəkil variantı. `kind` verilsə birbaşa həmin növə keçir."""
    bot.answer_callback(
        cq["id"], "Foto axtarılır…" if kind == "pexels" else "Başqa şəkil hazırlanır…"
    )
    try:
        director = _director_for(item)
        rungs = images.plan(director, item.id, agents)
        if target_rung is not None and 0 <= target_rung < len(rungs):
            nxt = target_rung
        elif kind:
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
            # AI pilləsi varsa zəncir BİTMİR: model hər çağırışda fərqli
            # şəkil verir, ona görə sonuncu pilləni təkrar icra edirik.
            # 11.09.2026: istifadəçi sona çatdı və «variant qalmadı»
            # aldı, halbuki yeni variant yaratmaq mümkün idi.
            if rungs and rungs[-1][1] == "ai":
                nxt = len(rungs) - 1
                # Kadr növbə ilə dəyişir (yaxın plan → geniş plan → …) —
                # gözləyən istifadəçi nəyin gəldiyini əvvəlcədən görsün.
                shot, _ = images.ai_shot(images.ai_take(item.id, nxt))
                bot.send_message(
                    f"🎨 <b>Yeni AI şəkli yaradılır — {shot}…</b>\n"
                    "<i>Təxminən bir dəqiqə · ~$0.03</i>"
                )
            else:
                # Təsdiqlənmiş variantlar bitdi — ümumi stok fotosuna DÜŞMÜRÜK.
                # İstifadəçiyə açıq seçim verilir (tələb 5-6).
                _send_options(item, bot, header="🖼 Təsdiqlənmiş variantlar bitdi.")
                return f"{item.id}: şəkil zənciri bitdi — seçimlər göndərildi"
        cand = images.produce(director, nxt, rungs, item.id, agents)
        if cand.error:
            bot.send_message(f"⚠️ Şəkil alınmadı: {_esc(cand.error)[:150]}")
            return f"{item.id}: şəkil xətası — {cand.error}"
        # ƏVVƏLCƏ arxivləyirik, sonra tətbiq edirik: `cand.path` `out/`
        # altındadır və növbəti icra onu üstündən yaza bilər.
        card_no = _remember_card(item.id, nxt, cand.path, cand.label,
                                 cand.credit or "")
        card = _card(item.id, card_no)
        item.image_path = queue._persist_image(item.id, card["path"]) or card["path"]
        item.image_rung, item.image_card, item.image_label = nxt, card_no, cand.label
        # Kredit də şəkillə birlikdə dəyişməlidir — 15.09.2026-a qədər ilk
        # fotonun krediti qalırdı və ilk şərhə YANLIŞ fotoqraf düşürdü
        # (Pixabay «father holding baby» krediti Tramp portretinə).
        item.image_credit = cand.credit or ""
        item.note("image_advanced", f"kart #{card_no + 1} · {cand.label}")
        queue.save(item)
        bot.send_photo(item.image_path,
                       f"🖼 {_esc(cand.label)} — kart #{card_no + 1} "
                       f"({nxt + 1}/{len(rungs)})")
        bot.send_message("Bu şəkil necədir?", keyboard(item))
        return f"{item.id}: kart #{card_no + 1} · pillə {nxt} — {cand.label}"
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
        bot.send_message(
            "🗑 <b>Post LinkedIn-dən silindi.</b>\n"
            "<i>Düzəldib yenidən yayımlamaq istəsəniz bərpa edə bilərəm.</i>",
            [[{"text": "♻️ Bərpa et və düzəlt",
               "callback_data": f"a|{item.id}|dorestore"}]])
        return f"{item.id}: LinkedIn-dən silindi"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Silinmədi: {_esc(str(exc))[:200]}")
        return f"{item.id}: silmə xətası — {exc}"


def _ask_restore(item: queue.Item, cq: dict, bot: telegram.Bot) -> str:
    """Bərpadan ƏVVƏL soruşur: post doğrudan LinkedIn-dən silinibmi?

    Bu sual məcburidir. Post hələ LinkedIn-dədirsə, bərpa + təkrar yayım
    profildə EYNİ postdan iki dənə yaradır — geri qaytarılması əziyyətli
    olan səhvdir.
    """
    bot.answer_callback(cq["id"], "")
    bot.send_message(
        "♻️ <b>Postu bərpa edim?</b>\n\n"
        f"<i>{_esc(item.chosen.get('title', '')[:70])}</i>\n\n"
        "Post təsdiq mərhələsinə qayıdır: şəkli, mətni dəyişib yenidən "
        "yayımlaya bilərsiniz. Gündəlik hədd də azad olur.\n\n"
        "⚠️ <b>Əvvəlcə LinkedIn-də silmisinizmi?</b> Post hələ oradadırsa, "
        "təkrar yayım profildə İKİ eyni post yaradacaq.",
        [[{"text": "✅ Sildim, bərpa et", "callback_data": f"a|{item.id}|dorestore"},
          {"text": "❌ Yox", "callback_data": f"a|{item.id}|cancelask"}]])
    return f"{item.id}: bərpa təsdiqi gözlənilir"


def _do_restore(item: queue.Item, cq: dict, bot: telegram.Bot) -> str:
    """Postu təsdiq mərhələsinə qaytarır və klaviaturanı yenidən verir."""
    bot.answer_callback(cq["id"], "Bərpa edilir…")
    try:
        publisher.restore(item)
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Bərpa alınmadı: {_esc(str(exc))[:200]}")
        return f"{item.id}: bərpa xətası — {exc}"

    fresh = queue.get(item.id) or item
    bot.send_message(
        "♻️ <b>Post bərpa olundu.</b>\n"
        "<i>LinkedIn linki və arxiv qeydi silindi; gündəlik hədd azaddır. "
        "Düzəliş edib yenidən yayımlaya bilərsiniz.</i>")
    send_for_approval(fresh, bot)
    return f"{item.id}: bərpa olundu"


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
    # İkinci düymə ayrı hal üçündür: sahibi postu LinkedIn-də ÖZÜ silib.
    # O zaman sistem «artıq yayımlanıb» deyib təkrar yayıma imkan
    # vermirdi və yeganə yol əl ilə JSON redaktəsi idi (24.09.2026).
    keyboard = [
        [{"text": "🗑 Postu sil", "callback_data": f"a|{item.id}|del"}],
        [{"text": "♻️ LinkedIn-dən özüm sildim",
          "callback_data": f"a|{item.id}|restore"}],
    ]
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
        if action == "imgnote":
            return _apply_image_note(text, pending.get("item_id", ""), bot, agents)

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
    ("propose", "📰 Bugünkü namizədləri hazırla"),
    ("topic", "🔗 Linkdən post yaz"),
    ("edit", "✏️ Gözləyən postu düzəlt"),
    ("preview", "👁 Növbəti postu göstər"),
    ("now", "🚀 Bankdan indi yayımla"),
    ("undo", "🗑 Son postu sil"),
    ("restore", "♻️ Silinmiş postu geri qaytar"),
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

# Yarımçıq yazı: seçim basılıb, post yazılır — proses ölsə (restart, pkill,
# reboot) dinləyici qalxanda bunu görüb DAVAM EDİR. 16.09.2026: istifadəçi
# namizəd seçdi, mən dinləyicini yenidən qurdum, yazı kəsildi, təklif
# `picked` qaldı — «3 dəqiqə» dedi, 15 dəqiqə heç nə gəlmədi.
INFLIGHT_FILE = config.STATE_DIR / "inflight.json"
INFLIGHT_MAX_MIN = 60          # bundan köhnə yarımçıq iş davam etdirilmir
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
    image_path = image_label = alt_text = image_credit = ""
    director: dict = {}
    try:
        agents: list = []
        director = images.direct(result.post, result.research, agents)
        # Model seçici YALNIZ post veriləndə işləyir (dərs 13). Bura
        # qoyulmamışdı → ilk şəkil xam söz-uyğunluğu ilə seçilirdi və
        # nəticə memo-ya düşüb bütün «başqa şəkil» basışlarına qalırdı
        # (15.09.2026: «man, father, holding, baby» Nvidia postuna).
        director["_post"] = result.post
        director["_research"] = result.research     # tədbir təsdiqi üçün
        rungs = images.plan(director, result.run_id, agents)
        if rungs:
            cand = images.produce(director, 0, rungs, result.run_id, agents,
                                  fallback_query=director.get("pexels_query", ""))
            if not cand.error:
                image_path, image_label = cand.path, cand.label
                alt_text = director.get("alt_text", "")
                image_credit = cand.credit
                _remember_card(result.run_id, 0, cand.path, cand.label,
                               cand.credit or "")
    except Exception:  # noqa: BLE001 — şəkil postu bloklamamalıdır
        pass

    item = queue.enqueue(
        item_id=result.run_id, post=result.post,
        first_comment=result.first_comment, hashtags=result.hashtags,
        chosen=result.chosen, scores=result.scores,
        image_path=image_path, image_label=image_label, alt_text=alt_text,
        image_credit=image_credit,
        research=result.research, angles=result.angles,
        chosen_angle_id=result.chosen_angle_id, director=director,
    )
    send_for_approval(item, bot)
    # Müfəttişin qərarları — istifadəçi nəyin niyə seçildiyini görsün;
    # uyğun şəkil yoxdursa bunu AÇIQ deyirik, boş yerə foto qoymuruq.
    try:
        _send_options(item, bot)
    except Exception:  # noqa: BLE001
        pass
    return f"{result.run_id}: hazırlandı ({result.scores.get('overall')}/10)"


def _director_for(item: queue.Item) -> dict:
    director = dict(item.director or images.load_manifest(item.id)["director"])
    director["_post"] = item.post
    director["_research"] = item.research or {}
    # Rəy elementdə qalır, ona görə SONRAKI bütün AI variantlarına da
    # tətbiq olunur — istifadəçi eyni şeyi təkrar yazmamalıdır.
    if item.image_brief or item.image_note:
        director["_image_brief"] = item.image_brief or item.image_note
    return director


def _options_keyboard(item: queue.Item, count: int) -> list:
    rows = []
    if count:
        rows.append([{"text": f"{NUMERALS[i]} Bu şəkil",
                      "callback_data": f"a|{item.id}|useopt{i}"} for i in range(min(count, 2))])
    rows.append([
        {"text": "🔎 Tədbir fotosu axtar", "callback_data": f"a|{item.id}|imgevent"},
        {"text": "🖼 Redaksiya kartı", "callback_data": f"a|{item.id}|imgcollage"},
    ])
    return rows


def _send_options(item: queue.Item, bot: telegram.Bot, header: str = "") -> None:
    """Ən çox 2 uyğun variant: növ · izah · mənbə · tarix. Rədd sayı və səbəbi."""
    sel = images.load_selection(item.id)
    if sel is None:
        return
    lines = [header] if header else []
    if sel.accepted:
        lines.append("🔍 <b>Müfəttişin qəbul etdiyi şəkillər</b>")
        for i, d in enumerate(sel.accepted[:2]):
            kind = {"event": "tədbir fotosu", "archive": "arxiv fotosu",
                    "contextual": "kontekst fotosu"}.get(d["image_type"], d["image_type"])
            lines += [
                f"{NUMERALS[i]} <b>{kind}</b>" + (f" · {_esc(d['date'][:10])}" if d.get("date") else ""),
                f"    {_esc((d.get('relevance') or '')[:140])}",
                f"    <a href=\"{_esc(d.get('source_page') or '')}\">mənbə</a>"
                + (f" · <i>{_esc(d['uncertainty'][:100])}</i>" if d.get("uncertainty") else ""),
            ]
    else:
        lines.append("🚫 <b>Uyğun şəkil tapılmadı.</b> Ümumi stok fotosu qoyulmadı.")
    if sel.rejected:
        reasons: dict[str, int] = {}
        for d in sel.rejected:
            for r in d.get("reasons", [])[:1]:
                reasons[r] = reasons.get(r, 0) + 1
        top = " · ".join(f"{r[:50]} ({n})" for r, n in sorted(reasons.items(), key=lambda x: -x[1])[:3])
        lines.append(f"<i>Rədd: {len(sel.rejected)} namizəd — {_esc(top)}</i>")
    story = sel.story or {}
    if story.get("event_confirmed"):
        lines.append(f"<i>Tədbir mənbədə təsdiqlənib: {_esc(story.get('event_name',''))} "
                     f"{_esc(story.get('event_date',''))}</i>")
    bot.send_message("\n".join(lines), _options_keyboard(item, len(sel.accepted)))


def _remember_card(item_id: str, rung: int, path: str, label: str,
                   credit: str) -> int:
    """Göstərilən kartı TOXUNULMAZ saxlayır və nömrəsini qaytarır.

    İki şey vacibdir:

    1. Fayl dərhal `state/images/<id>-cN.png` altına köçürülür. `out/`
       altındakı ad pilləyə görədir (`03-news.png`), ona görə eyni pillə
       ikinci dəfə icra olunanda əvvəlki kartın faylı ÜSTÜNDƏN yazılırdı
       — «kart #1-ə qayıt» düyməsi həmin fayla baxırdı və istifadəçi
       sonuncu şəkli alırdı (24.09.2026, istifadəçinin şikayəti).
    2. Nömrə siyahıdakı mövqedir, yəni artan və təkrarsızdır — pillə isə
       təkrarlanır.
    """
    data = (store.read_json(CHOICE_STORE, {}) or {}).get(item_id, {})
    cards = list(data.get("cards") or [])
    card_no = len(cards)
    kept = queue._persist_image(item_id, path, suffix=f"-c{card_no}") or path
    cards.append({"rung": rung, "path": kept, "label": label,
                  "credit": credit or ""})
    # Siyahı QIRXILMIR: kart nömrəsi mövqedir, başdan bir element atsaq
    # bütün nömrələr sürüşər və «kart #1-ə qayıt» başqa şəkli açar.
    # Yerə görə narahatlıq yoxdur — burada yalnız yol və etiket var;
    # faylların özünü `queue.prune_images()` post bitəndə silir.
    data["cards"] = cards
    _remember_choices(item_id, data)
    return card_no


def _card(item_id: str, card_no: int) -> dict:
    """Kart nömrəsinə görə saxlanmış qeydi qaytarır.

    Köhnə elementlərdə qeydlər pillə açarı ilə saxlanılırdı (`"3"`), ona
    görə tapılmasa həmin formata baxırıq — yeniləmədən əvvəl göndərilmiş
    düymələr işləməyə davam etsin.
    """
    data = (store.read_json(CHOICE_STORE, {}) or {}).get(item_id, {})
    cards = data.get("cards") or []
    if 0 <= card_no < len(cards):
        return dict(cards[card_no])
    legacy = data.get(str(card_no))
    if legacy:
        return {"rung": card_no, "path": legacy,
                "label": data.get(f"{card_no}:label", ""),
                "credit": data.get(f"{card_no}:credit", "")}
    return {}


def _apply_candidate(item: queue.Item, cand, rung: int, bot: telegram.Bot,
                     total: int) -> str:
    card_no = _remember_card(item.id, rung, cand.path, cand.label,
                             cand.credit or "")
    card = _card(item.id, card_no)
    item.image_path = queue._persist_image(item.id, card["path"]) or card["path"]
    item.image_rung, item.image_card, item.image_label = rung, card_no, cand.label
    item.image_credit = cand.credit or ""
    item.note("image_advanced", f"kart #{card_no + 1} · {cand.label}")
    queue.save(item)
    bot.send_photo(item.image_path,
                   f"🖼 {_esc(cand.label)} — kart #{card_no + 1} ({rung + 1}/{total})")
    bot.send_message("Bu şəkil necədir?", keyboard(item))
    return f"{item.id}: kart #{card_no + 1} · pillə {rung} — {cand.label}"


def _use_option(item: queue.Item, index: int, cq: dict, bot: telegram.Bot,
                agents: list) -> str:
    """Müfəttişin qəbul etdiyi N-ci şəkillə kart."""
    bot.answer_callback(cq["id"], "Kart hazırlanır…")
    try:
        director = _director_for(item)
        rungs = images.plan(director, item.id, agents)
        rung = next((i for i, (k, p) in enumerate(rungs) if k == "news" and p == index), None)
        if rung is None:
            bot.send_message("⚠️ Bu variant artıq mövcud deyil.")
            return f"{item.id}: variant {index} yoxdur"
        cand = images.produce(director, rung, rungs, item.id, agents)
        if cand.error:
            bot.send_message(f"⚠️ Şəkil alınmadı: {_esc(cand.error)[:150]}")
            return f"{item.id}: şəkil xətası — {cand.error}"
        sel_ok = images.accepted_decisions(item.id)
        if index < len(sel_ok):
            from .images import inspect as _inspect, story as _story
            _inspect.remember_asset(sel_ok[index],
                                    _story.Story(**(images.load_selection(item.id).story or {})),
                                    used_in=item.id)
        return _apply_candidate(item, cand, rung, bot, len(rungs))
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Şəkil xətası: {_esc(str(exc))[:150]}")
        return f"{item.id}: şəkil xətası — {exc}"


def _search_event(item: queue.Item, cq: dict, bot: telegram.Bot, agents: list) -> str:
    """Tədbirə xüsusi axtarış — namizəd dəsti genişlənir, müfəttiş yenidən baxır."""
    bot.answer_callback(cq["id"], "Tədbir fotosu axtarılır…")
    bot.send_message("🔎 <b>Tədbirə xüsusi axtarış…</b>\n"
                     "<i>İştirakçılar + tədbir adı (mənbə təsdiqləyibsə) · ~1 dəqiqə</i>")
    try:
        director = _director_for(item)
        sel = images.analyze(director, item.id, agents, force=True, event_only=True)
        if not sel.accepted:
            _send_options(item, bot, header="🔎 Tədbir axtarışı: uyğun şəkil tapılmadı.")
            return f"{item.id}: tədbir axtarışı — heç nə"
        _send_options(item, bot, header="🔎 Tədbir axtarışının nəticəsi:")
        return f"{item.id}: tədbir axtarışı — {len(sel.accepted)} variant"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Axtarış xətası: {_esc(str(exc))[:150]}")
        return f"{item.id}: tədbir axtarışı xətası — {exc}"


def _make_collage(item: queue.Item, cq: dict, bot: telegram.Bot, agents: list) -> str:
    """Etiketli redaksiya kollajı — təsdiqlənmiş portretlərdən."""
    bot.answer_callback(cq["id"], "Kollaj hazırlanır…")
    try:
        director = _director_for(item)
        rungs = images.plan(director, item.id, agents)
        rung = next((i for i, (k, _) in enumerate(rungs) if k == "collage"), None)
        if rung is None:
            bot.send_message("🖼 Kollaj üçün iki şəxsin təsdiqlənmiş portreti yoxdur — "
                             "əvvəlcə «Tədbir fotosu axtar» sınayın.")
            return f"{item.id}: kollaj mümkün deyil"
        cand = images.produce(director, rung, rungs, item.id, agents)
        if cand.error:
            bot.send_message(f"⚠️ Kollaj alınmadı: {_esc(cand.error)[:150]}")
            return f"{item.id}: kollaj xətası — {cand.error}"
        return _apply_candidate(item, cand, rung, bot, len(rungs))
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Kollaj xətası: {_esc(str(exc))[:150]}")
        return f"{item.id}: kollaj xətası — {exc}"


# --- Mövzu təklifi ----------------------------------------------------

def send_proposal(proposal, bot: telegram.Bot) -> None:
    """Hazırkı pəncərənin namizədlərini düymələrlə göndərir.

    Düymələr namizədin MÜTLƏQ indeksini daşıyır (`pick4`), ekrandakı
    nömrə isə nisbi (1️⃣) — «başqa xəbər» pəncərəni sürüşdürəndə
    seçim yenə düzgün namizədə düşür.
    """
    offset = getattr(proposal, "offset", 0)
    head = "🔄 <b>Başqa namizədlər</b>" if offset else "📰 <b>Bu gün üçün namizədlər</b>"
    lines = [head, ""]
    row = []
    for slot, cand in enumerate(proposal.shown):
        index = offset + slot
        sources_txt = ", ".join(cand.get("sources", [])[:3])
        # Qlobal/yerli balansı siyahıda görünür — sahibi «bu gün hamısı
        # dünya xəbəridir» deyə bilsin və lazım olsa başqa namizəd istəsin.
        flag = "🇦🇿" if cand.get("region") == "local" else "🌍"
        lines += [
            f"{NUMERALS[slot]} {flag} <b>{_esc(cand.get('title', '')[:80])}</b>",
            f"    <i>{_esc(sources_txt)} · {_esc(cand.get('pillar', ''))}</i>",
        ]
        # Hook — oxucunu dayandıran sətir. Seçim məhz bunun üstündə qurulur,
        # ona görə istifadəçi də onu görməlidir (15.09.2026).
        if cand.get("hook"):
            lines.append(f"    💬 {_esc(cand['hook'][:140])}")
        lines += [f"    {_esc(cand.get('why', '')[:110])}", ""]
        row.append({"text": NUMERALS[slot],
                    "callback_data": f"a|{proposal.id}|pick{index}"})
    for warning in getattr(proposal, "warnings", None) or []:
        lines.append(f"⚠️ <i>{_esc(warning)}</i>")
    lines.append(f"<i>Cavab verməsəniz {proposals.AUTO_PICK_HOURS:.0f} saat sonra "
                 f"sistem özü seçəcək.</i>")

    keyboard = [row, [
        {"text": "🎲 Sən seç", "callback_data": f"a|{proposal.id}|pickauto"},
        {"text": "🔄 Başqa xəbər", "callback_data": f"a|{proposal.id}|pickmore"},
        {"text": "❌ Bu gün keç", "callback_data": f"a|{proposal.id}|picknone"},
    ]]
    proposal.telegram_message_id = bot.send_message("\n".join(lines), keyboard)
    proposals.save(proposal)


def _more_candidates(proposal, cq: dict, bot: telegram.Bot) -> str:
    """«Başqa xəbər»: pəncərəni sürüşdürür; ehtiyat bitibsə Scout-u çağırır.

    Köhnə mesajın düymələri yalnız YENİ dəst hazır olanda silinir —
    ehtiyat gətirilməsə istifadəçi düyməsiz qalmasın.
    """
    bot.answer_callback(cq["id"], "Başqa xəbərlər…")
    nxt = proposal.offset + proposals.PAGE
    if nxt >= len(proposal.candidates):
        bot.send_message(
            "🔍 <b>Ehtiyat bitdi — Scout qalan xəbərlərə baxır…</b>\n"
            "<i>Təxminən bir dəqiqə · ~20k token</i>"
        )
        try:
            added = pipeline.propose_more(proposal)
        except llm.QuotaExhausted as exc:
            bot.send_message(f"⚠️ Abunəlik limiti — yeni namizəd gətirilmədi.\n"
                             f"<i>{_esc(str(exc))[:150]}</i>")
            return f"{proposal.id}: başqa xəbər — kvota"
        except Exception as exc:  # noqa: BLE001
            bot.send_message(f"⚠️ Yeni namizəd alınmadı: {_esc(str(exc))[:150]}")
            return f"{proposal.id}: başqa xəbər xətası — {exc}"
        if not added:
            bot.send_message("🤷 Bu gün başqa layiqli xəbər yoxdur — "
                             "yuxarıdakılardan seçin və ya günü keçin.")
            return f"{proposal.id}: başqa xəbər — qalmadı"
    bot.edit_markup(proposal.telegram_message_id, None)
    proposal.offset = nxt
    send_proposal(proposal, bot)          # yeni mesaj, yeni düymələr, saxlanır
    shown = ", ".join(c.get("title", "")[:30] for c in proposal.shown)
    return f"{proposal.id}: başqa xəbər — {nxt}-dən: {shown}"


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
    if action == "pickmore":
        return _more_candidates(proposal, cq, bot)

    # «Sən seç» pəncərənin BİRİNCİSİNİ götürür — istifadəçi «başqa xəbər»
    # basıbsa, əvvəlkiləri artıq rədd edib.
    index = proposal.offset if action == "pickauto" else int(action.replace("pick", ""))
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
    store.write_json(INFLIGHT_FILE, {
        "proposal": pid, "index": index, "by": "auto" if action == "pickauto" else "user",
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        result = pipeline.write_from_proposal(proposal, index, verbose=False)
        error = "" if result.ok else (result.error or "naməlum səbəb")
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        INFLIGHT_FILE.unlink(missing_ok=True)
    if error:
        # Yazı alınmadı → təklif YENİDƏN AÇILIR, düymələr qayıdır.
        # Əks halda təklif `picked` qalır və istifadəçi dalana dirənir
        # (15.09.2026: VPN-siz seçim, Researcher fakt tapmadı).
        proposals.reopen(proposal)
        bot.send_message(
            f"⚠️ <b>Post hazırlanmadı:</b> <i>{_esc(error)[:200]}</i>\n\n"
            "🔁 Namizədlər yenidən açıldı — eyni mövzunu təkrar seçə və ya "
            "başqasını götürə bilərsiniz."
        )
        send_proposal(proposal, bot)
        return f"{pid}: yazı alınmadı, təklif yenidən açıldı — {error}"
    return _finish_and_send(result, bot)


def resume_inflight(bot: telegram.Bot) -> list[str]:
    """Dinləyici qalxanda: yarımçıq qalmış yazı varsa DAVAM ET.

    Proses ölərkən `INFLIGHT_FILE` silinmir — məhz bu, «iş yarımçıqdır»
    siqnalıdır. Köhnədirsə (>60 dəq) davam etmirik — istifadəçiyə deyib
    təklifi yenidən açırıq; yeni post onun qərarı ilə yazılsın.
    """
    data = store.read_json(INFLIGHT_FILE, None)
    if not data:
        return []
    pid, index = data.get("proposal", ""), int(data.get("index", 0))
    try:
        started = datetime.fromisoformat(data.get("started_at", ""))
        age_min = (datetime.now(timezone.utc) - started).total_seconds() / 60
    except ValueError:
        age_min = INFLIGHT_MAX_MIN + 1
    INFLIGHT_FILE.unlink(missing_ok=True)
    proposal = proposals.get(pid)
    if not proposal:
        return [f"yarımçıq iş: təklif tapılmadı ({pid})"]
    if queue.get(pid) or any(i.chosen.get("_proposal") == pid for i in queue.all_items()):
        return [f"yarımçıq iş: {pid} artıq növbədədir — atlanır"]
    proposals.reopen(proposal)
    if age_min > INFLIGHT_MAX_MIN:
        send_proposal(proposal, bot)
        bot.send_message("⚠️ Əvvəlki seçimin yazısı kəsilmişdi və çox köhnədir — "
                         "namizədlər yenidən açıldı, təzədən seçin.")
        return [f"yarımçıq iş köhnədir ({age_min:.0f} dəq) — təklif yenidən açıldı"]
    title = proposal.candidates[index].get("title", "") if index < len(proposal.candidates) else ""
    bot.send_message(
        "🔁 <b>Yazı kəsilmişdi — davam edirəm.</b>\n"
        f"<i>{_esc(title[:70])}</i>\n\n"
        "Dinləyici yenidən qalxıb (yenilənmə və ya restart). Seçiminiz "
        "qorunub, təxminən 3 dəqiqə."
    )
    fake_cq = {"id": "resume", "message": {"message_id": proposal.telegram_message_id}}
    return [_handle_pick(pid, f"pick{index}", fake_cq, bot)]


def auto_pick_due(bot: telegram.Bot) -> list[str]:
    """Cavabsız qalmış təkliflər üçün sistem özü seçir — post günü boş keçməsin."""
    log = []
    for proposal in proposals.due_for_auto_pick():
        first = proposal.shown[0] if proposal.shown else proposal.candidates[0]
        bot.send_message(
            f"🎲 <b>Cavab gəlmədi — özüm seçdim</b>\n"
            f"<i>{_esc(first.get('title', '')[:70])}</i>"
        )
        fake_cq = {"id": "auto", "message": {"message_id": proposal.telegram_message_id}}
        log.append(_handle_pick(proposal.id, "pickauto", fake_cq, bot))
    return log


def _propose_command(bot: telegram.Bot) -> str:
    """Namizədləri indi hazırla — səhər hazırlığı buraxılıbsa və ya təzə dəst istənirsə."""
    for old in proposals.open_proposals():          # iki açıq təklif = iki auto-pick
        proposals.expire(old)
        bot.edit_markup(old.telegram_message_id, None)
    bot.send_message("📰 <b>Namizədlər hazırlanır…</b>\n"
                     f"<i>{len(sources.FEEDS)} mənbə (🌍 {len(sources.GLOBAL_FEEDS)} · "
                     f"🇦🇿 {len(sources.LOCAL_FEEDS)}) → Scout → 6 namizəd · "
                     "təxminən 2 dəqiqə</i>")
    try:
        result = pipeline.propose(verbose=False)
    except llm.QuotaExhausted as exc:
        bot.send_message(f"⚠️ Abunəlik limiti — namizəd hazırlanmadı.\n<i>{_esc(str(exc))[:150]}</i>")
        return "propose: kvota"
    except Exception as exc:  # noqa: BLE001
        bot.send_message(f"⚠️ Namizədlər hazırlanmadı: {_esc(str(exc))[:150]}")
        return f"propose: xəta — {exc}"
    if not result.get("ok"):
        bot.send_message(f"🔕 <b>Namizəd tapılmadı</b>\n<i>{_esc(result.get('error', ''))[:200]}</i>")
        return f"propose: {result.get('error')}"
    send_proposal(result["proposal"], bot)
    return f"propose: {len(result['proposal'].candidates)} namizəd göndərildi"


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
    from . import calibration
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

    if cmd == "restore":
        # Düymə köhnə mesajda qalıb və ya post dünən silinibsə bu yol işləyir.
        published = [i for i in queue.by_status(queue.PUBLISHED) if i.published_at]
        published.sort(key=lambda i: i.published_at or "", reverse=True)
        if not published:
            bot.send_message("Bərpa ediləcək yayımlanmış post yoxdur.")
            return "restore: post yoxdur"
        item = published[0]
        return _ask_restore(item, {"id": "cmd"}, bot)

    if cmd == "propose":
        # Mac 08:35-də sönülü olanda səhər hazırlığı buraxılır (dərs 37);
        # istifadəçi bunu mənə yazmadan özü başlada bilməlidir (16.09.2026).
        if proposals.prepared_today():
            bot.send_message(
                "📰 <b>Bu gün namizədlər artıq göndərilib.</b>\n"
                "Yenə də təzə dəst hazırlansın? <i>(~20k token, köhnə açıq təklif bağlanır)</i>",
                [[{"text": "✅ Bəli, təzə dəst", "callback_data": "a|-|dopropose"},
                  {"text": "❌ Yox", "callback_data": "a|-|cancelask"}]])
            return "propose: təsdiq gözlənilir"
        return _propose_command(bot)

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

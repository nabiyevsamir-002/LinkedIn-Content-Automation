"""Oflayn testlər — şəbəkə və LLM olmadan, saniyələr içində işləyir.

Məqsəd: bir dəyişiklik başqa yeri sındırsa, bunu YAYIMDAN ƏVVƏL bilmək.
Bu sistemdə səhvin qiyməti yüksəkdir — LinkedIn-ə çıxan postu geri
qaytarmaq olmur.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _block_network():
    """Testlər oflayn olmalıdır.

    Bir test təsadüfən şəbəkəyə çıxsa, qaçış müddəti saniyələrdən
    dəqiqələrə keçir və nəticə internetdən asılı olur. Qoruyucu:
    şəbəkə cəhdi dərhal xəta verir.
    """
    import socket

    def guard(*args, **kwargs):
        raise AssertionError(
            "Test şəbəkəyə çıxmağa çalışdı — oflayn qalmalıdır")

    socket.socket.connect = guard
    socket.create_connection = guard


_block_network()


class Filters(unittest.TestCase):
    def setUp(self):
        from src import filters
        self.f = filters

    def _kinds(self, text):
        return {flag.kind for flag in self.f.check(text)}

    def test_cliche_detected(self):
        self.assertIn("cliche_az", self._kinds("Bu, oyunun qaydalarını dəyişir."))
        self.assertIn("cliche_en", self._kinds("A real game-changer here."))

    def test_clean_text_passes(self):
        clean = ("Qısa hook sətri burada.\n\n• Bir fakt\n• İkinci fakt\n\n"
                 "Nəticə iki cümlədir. Konkret və aydın.\n\nSual?\n\n#AI") * 2
        self.assertNotIn("cliche_az", self._kinds(clean))

    def test_length_bounds(self):
        self.assertIn("too_long", self._kinds("a" * 1400))
        self.assertIn("too_short", self._kinds("a" * 300))

    def test_wall_of_text(self):
        self.assertIn("wall_of_text", self._kinds("x" * 400))

    def test_em_dash_limit(self):
        self.assertIn("em_dash", self._kinds("a — b — c — d — e"))

    def test_invented_number_hedge(self):
        self.assertIn("invented_number",
                      self._kinds("mənim təxminimcə gündə saatlarla vaxt gedir"))


class Preview(unittest.TestCase):
    def test_fold_within_limit(self):
        from src import config, preview
        text = "Hook sətri.\n\n" + "davamı " * 200
        cut = preview.fold_index(text)
        self.assertLessEqual(cut, config.LINKEDIN_FOLD_CHARS)
        self.assertIn("…daha çox", preview.render(text))

    def test_short_text_not_folded(self):
        from src import preview
        self.assertEqual(preview.fold_index("qısa"), len("qısa"))


class Cluster(unittest.TestCase):
    def _item(self, title, source="rundown", primary=False, weight=1.0):
        from src.sources import Item
        return Item(source=source, source_name=source, weight=weight,
                    primary=primary, title=title, link=f"http://x/{title[:9]}",
                    summary="", published=datetime.now(timezone.utc))

    def test_same_story_groups(self):
        from src import cluster
        clusters = cluster.build([
            self._item("OpenAI releases new agent model"),
            self._item("OpenAI releases new agent model today", source="tc"),
        ])
        self.assertEqual(len(clusters), 1)

    def test_pr_penalised(self):
        from src import cluster
        pr = cluster.Cluster(items=[self._item(
            "Supporting independent journalism in Ukraine", primary=True)])
        news = cluster.Cluster(items=[self._item("OpenAI agent swarm found")])
        self.assertTrue(pr.looks_like_pr)
        self.assertLess(pr.score, news.score,
                        "tək mənbəli PR elanı adi xəbərdən yuxarı olmamalıdır")

    def test_primary_alone_is_weak(self):
        """Tək mənbəli rəsmi elan iki müstəqil mənbəli xəbərdən aşağı olmalıdır.

        Bu, real səhv idi: sistem OpenAI-ın KSM press-relizini seçmişdi,
        çünki `primary` bonusu tək başına çox güclü idi.
        """
        from src import cluster
        solo_official = cluster.Cluster(items=[
            self._item("Model card update", primary=True, weight=1.0)])
        solo_plain = cluster.Cluster(items=[
            self._item("Model card update", primary=False, weight=1.0)])
        bonus = solo_official.score - solo_plain.score
        self.assertLessEqual(
            bonus, 0.35,
            f"tək mənbəli rəsmi elana verilən bonus çox böyükdür ({bonus:.2f}) — "
            "PR press-relizləri real xəbərləri üstələyəcək")

        pair_official = cluster.Cluster(items=[
            self._item("Model card update", primary=True, weight=1.0),
            self._item("Model card update analysed", source="ars", weight=0.85)])
        self.assertGreater(
            pair_official.score - solo_official.score, 1.0,
            "jurnalist əhatəsi olan rəsmi mənbə xeyli güclü olmalıdır")


class Queue(unittest.TestCase):
    def setUp(self):
        from src import config, queue
        self.queue = queue
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = queue.QUEUE
        queue.QUEUE = Path(self.tmp.name) / "queue.json"
        self._orig_images = queue.IMAGES_DIR
        queue.IMAGES_DIR = Path(self.tmp.name) / "images"

    def tearDown(self):
        self.queue.QUEUE = self._orig
        self.queue.IMAGES_DIR = self._orig_images
        self.tmp.cleanup()

    def _add(self, ident="a", **kw):
        return self.queue.enqueue(
            item_id=ident, post="mətn", first_comment="mənbə", hashtags=[],
            chosen={"title": "T", "pillar": "agents"}, scores={"overall": 7}, **kw)

    def test_lifecycle(self):
        item = self._add()
        self.assertEqual(item.status, self.queue.PENDING)
        self.queue.set_status(item, self.queue.APPROVED)
        self.assertEqual(len(self.queue.bank()), 1)
        self.queue.schedule(item)
        self.assertEqual(self.queue.get("a").status, self.queue.SCHEDULED)

    def test_enqueue_is_idempotent(self):
        self._add(); self._add()
        self.assertEqual(len(self.queue.all_items()), 1)

    def test_due_respects_time(self):
        item = self._add()
        self.queue.schedule(item, datetime.now(timezone.utc) + timedelta(hours=5))
        self.assertEqual(self.queue.due(), [])
        self.queue.schedule(item, datetime.now(timezone.utc) - timedelta(minutes=1))
        self.assertEqual(len(self.queue.due()), 1)

    def test_next_slot_is_future_and_weekday(self):
        from src import config
        slot = self.queue.next_slot(jitter=False)
        self.assertGreater(slot, datetime.now(timezone.utc))
        if not config.PUBLISH_WEEKENDS:
            self.assertLess(slot.weekday(), 5)

    def test_compact_strips_heavy_fields(self):
        item = self._add(research={"facts": [{"claim": "x" * 500}]},
                         angles=[{"id": 1}], director={"headline": "h"})
        self.queue.set_status(item, self.queue.SKIPPED)
        self.assertEqual(self.queue.compact(keep_days=0), 1)
        self.assertFalse(self.queue.get("a").research)
        # post mətni və ballar QALMALIDIR
        self.assertTrue(self.queue.get("a").post)
        self.assertTrue(self.queue.get("a").scores)

    def test_unknown_fields_are_ignored(self):
        """Sxem dəyişəndə köhnə vəziyyət faylı sistemi sındırmamalıdır.

        Real hadisə: karusel sahələri silindi, amma queue.json-da qaldı
        və bütün sistem `TypeError` ilə dayandı.
        """
        from src import store
        store.write_json(self.queue.QUEUE, {"items": [{
            "id": "a", "post": "mətn", "status": "pending",
            "silinmis_sahe": "köhnə məlumat", "basqa_sahe": 42,
        }]})
        items = self.queue.all_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].post, "mətn")
        self.assertEqual(self.queue.get("a").id, "a")

    def test_compact_spares_active_items(self):
        self._add(research={"facts": [{"claim": "x"}]})
        self.assertEqual(self.queue.compact(keep_days=0), 0)


class TimeFormat(unittest.TestCase):
    def test_local_conversion(self):
        from src import timefmt
        utc = datetime(2026, 9, 9, 8, 15, tzinfo=timezone.utc)
        self.assertEqual(timefmt.local(utc).hour, 12)      # Bakı = UTC+4

    def test_relative_labels(self):
        """Sabit müqayisə nöqtəsi ilə — gecəyarısına yaxın sınmasın.

        Əvvəl bu test `datetime.now()` işlədirdi və saat 22:00-dan sonra
        «+2 saat» ertəsi günə keçdiyi üçün təsadüfən sınırdı.
        """
        from src import timefmt
        # 09.09.2026, 08:00 UTC = 12:00 Bakı — gündüz, sərhəddən uzaq
        ref = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
        self.assertTrue(
            timefmt.fmt(ref + timedelta(hours=2), reference=ref).startswith("bu gün"))
        self.assertTrue(
            timefmt.fmt(ref + timedelta(days=1), reference=ref).startswith("sabah"))
        self.assertTrue(
            timefmt.fmt(ref - timedelta(days=1), reference=ref).startswith("dünən"))

    def test_relative_labels_near_midnight(self):
        """Gecəyarısına yaxın da düzgün işləməlidir."""
        from src import timefmt
        ref = datetime(2026, 9, 9, 19, 0, tzinfo=timezone.utc)    # 23:00 Bakı
        # 23:30 — hələ eyni gün
        self.assertTrue(
            timefmt.fmt(ref + timedelta(minutes=30), reference=ref).startswith("bu gün"))
        # 01:00 — artıq ertəsi gün
        self.assertTrue(
            timefmt.fmt(ref + timedelta(hours=2), reference=ref).startswith("sabah"))

    def test_none_is_safe(self):
        from src import timefmt
        self.assertEqual(timefmt.fmt(None), "—")
        self.assertEqual(timefmt.short("zibil"), "—")


class LinkedInFormat(unittest.TestCase):
    def test_escape_keeps_hashtags(self):
        from src import linkedin
        out = linkedin.escape_commentary("Qiymət (600$) artdı #AI")
        self.assertIn("#AI", out)
        self.assertIn(r"\(", out)

    def test_post_url(self):
        from src import linkedin
        self.assertIn("urn:li:share:7", linkedin.post_url("urn:li:share:7123"))


class ResearchQuality(unittest.TestCase):
    def test_stub_rejected(self):
        from src.pipeline import _research_quality_issue as check
        self.assertTrue(check({"facts": [{"claim": "Test claim"}]}))
        self.assertTrue(check({"facts": []}))

    def test_good_research_passes(self):
        from src.pipeline import _research_quality_issue as check
        self.assertEqual(check({
            "facts": [{"claim": "a"}, {"claim": "b"}],
            "numbers": [{"value": "1"}],
            "primary_source_url": "https://openai.com/x"}), "")


class VisualUnitSafety(unittest.TestCase):
    def test_mixed_units_forced_to_stats(self):
        from src import images
        out = images.enforce_unit_safety({
            "chart_style": "bars",
            "data_points": [{"value": "3,1x", "unit": "x"},
                            {"value": ">50%", "unit": "%"}]})
        self.assertEqual(out["chart_style"], "stats")

    def test_same_units_keep_bars(self):
        from src import images
        out = images.enforce_unit_safety({
            "chart_style": "bars",
            "data_points": [{"value": "3,1x", "unit": "x"},
                            {"value": "3,9x", "unit": "x"}]})
        self.assertEqual(out["chart_style"], "bars")


class NotionMapping(unittest.TestCase):
    def test_publishing_never_comes_from_notion(self):
        from src import notion, queue
        self.assertNotEqual(notion.queue_status("In progress"), queue.PUBLISHING)

    def test_editing_never_lands_in_bank(self):
        """Redaktə gözləyən post banka düşməməlidir — hələ təsdiqlənməyib."""
        from src import notion, queue
        orig = notion.status_options
        notion.status_options = lambda: ["Bank", "Not started", "Cədvəldə",
                                         "In progress", "Keçildi", "Done"]
        try:
            self.assertNotEqual(notion.notion_status(queue.EDITING), "Bank")
            self.assertEqual(notion.notion_status(queue.APPROVED), "Bank")
            self.assertEqual(notion.notion_status(queue.SKIPPED), "Keçildi")
            self.assertEqual(notion.notion_status(queue.SCHEDULED), "Cədvəldə")
        finally:
            notion.status_options = orig

    def test_staleness_guard(self):
        from src import notion, queue
        item = queue.Item(id="x", updated_at="2026-09-08T12:00:00+00:00")
        old = {"last_edited_time": "2026-09-08T10:00:00Z"}
        new = {"last_edited_time": "2026-09-08T13:00:00Z"}
        self.assertFalse(notion._newer_than_queue(old, item))
        self.assertTrue(notion._newer_than_queue(new, item))


class NewsCard(unittest.TestCase):
    """10.09.2026-da əlavə olunan `news` formatı: foto fon + başlıq zolağı."""

    PHOTO = "assets/fonts"          # yalnız yol lazımdır, oxunmur

    def _director(self, **kw):
        base = {"visual_type": "news", "headline": "Agent dövrü icra edir!",
                "kicker": "süni intellekt", "support": "altı kubitlik çip",
                "photo_queries": ["lab"], "accent_words": []}
        base.update(kw)
        return base

    def test_plan_puts_news_first_with_bubble_variant(self):
        from src import images
        from src.images import stock
        original = stock.available
        stock.available = lambda: True
        try:
            rungs = images.plan(self._director())
        finally:
            stock.available = original
        self.assertEqual(rungs[0], ("news", True))    # dairəvi şəkillə
        self.assertEqual(rungs[1], ("news", False))   # onsuz
        self.assertIn("claude", [k for k, _ in rungs])  # ehtiyat qalır

    def test_plan_falls_back_when_no_photo_source(self):
        """Xəbər kartı fotosuz qurula bilməz — adi kartlara düşməlidir."""
        from src import images
        from src.images import stock
        original = stock.available
        stock.available = lambda: False
        try:
            rungs = images.plan(self._director())
        finally:
            stock.available = original
        self.assertNotIn("news", [k for k, _ in rungs])
        self.assertEqual(rungs[0][0], "claude")

    def test_accent_words_are_marked(self):
        from src.images import news
        out = news._mark_accents("Agent dövrü icra edir", ["dövrü"])
        self.assertIn("<em>dövrü</em>", out)

    def test_accent_marks_each_word_once(self):
        from src.images import news
        out = news._mark_accents("dövrü və dövrü", ["dövrü"])
        self.assertEqual(out.count("<em>"), 1)

    def test_accent_words_as_json_string(self):
        """10.09.2026: model massiv əvəzinə JSON SƏTRİ qaytardı.

        Python sətri hərf-hərf iterasiya etdi, hər hərf ayrıca <em> ilə
        sarındı: Op<em>e</em><em>n</em><em>A</em>I… Başlıq alabəzək çıxdı.
        """
        from src.images import news
        out = news._mark_accents("OpenAI Astra modelini elan etdi",
                                 '["Astra"]')
        self.assertIn("<em>Astra</em>", out)
        self.assertEqual(out.count("<em>"), 1)

    def test_accent_respects_word_boundary(self):
        """«AI» vurğusu «AIDA» sözünün içinə düşməməlidir."""
        from src.images import news
        out = news._mark_accents("AI ve AIDA", ["AI"])
        self.assertTrue(out.startswith("<em>AI</em>"))
        self.assertIn("AIDA", out.replace("<em>AI</em>", ""))

    def test_accent_plain_string_is_one_word(self):
        from src.images import news
        self.assertEqual(news._accent_list("Astra"), ["Astra"])
        self.assertEqual(news._accent_list(""), [])
        self.assertEqual(news._accent_list(None), [])

    def test_headline_is_escaped(self):
        """Başlıqdakı < > şablonu sındırmamalıdır."""
        from src.images import news
        out = news._mark_accents('5 < 6 & "x"', [])
        self.assertNotIn("<", out.replace("&lt;", ""))
        self.assertIn("&amp;", out)

    def test_long_capsule_is_cut_to_one_line(self):
        """10.09.2026: 70 simvolluq kapsul iki sətirə düşüb formanı pozdu."""
        from src.images import news
        long = "Bu, geniş elmi nəticə deyil - tək bir sınaq, bir proof-of-concept idi."
        out = news._fit_capsule(long)
        self.assertLessEqual(len(out), news.CAPSULE_MAX + 1)
        self.assertTrue(out.endswith("…"))
        self.assertFalse(out.endswith(" …"))

    def test_short_capsule_is_untouched(self):
        from src.images import news
        self.assertEqual(news._fit_capsule("altı kubitlik çipdə ilk sınaq"),
                         "altı kubitlik çipdə ilk sınaq")

    def test_capsule_whitespace_is_normalised(self):
        from src.images import news
        self.assertEqual(news._fit_capsule("  iki   boşluq \n var "),
                         "iki boşluq var")

    def test_brand_name_comes_from_caller(self):
        """CI-da BRAND_NAME boşdur — ad kənardan gəlməlidir."""
        from src.images import news
        body, _ = news.build(
            self._director(), self.PHOTO if False else _tiny_png(),
            brand_info={"name": "Test Adı", "handle": "linkedin.com/in/x"})
        self.assertIn("Test Adı", body)
        self.assertIn("linkedin.com/in/x", body)


def _tiny_png() -> str:
    """1x1 PNG — build() faylı oxuduğu üçün real fayl lazımdır."""
    import base64, tempfile, pathlib as _p
    blob = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    path = _p.Path(tempfile.gettempdir()) / "_news_test_pixel.png"
    path.write_bytes(blob)
    return str(path)


class TelegramReachability(unittest.TestCase):
    """09.09.2026: Telegram TCP 443 bloklandı, dinləyici «gözləyir…» yazdı.

    `URLError` → `OSError` alt sinfidir və mesajı «timed out» olur, ona
    görə uzun polling-in NORMAL sükutu ilə tam şəbəkə bloku eyni sayılırdı.
    Nəticə: düymələr işləmirdi, sistem isə özünü sağlam göstərirdi.
    """

    class _Blocked:
        """Hər çağırışda şəbəkə timeout-u atan nəqliyyat."""

        def __init__(self, get_me_works: bool):
            self.get_me_works = get_me_works
            self.get_me_calls = 0

        def call(self, method, payload, file_field=None, file_path=None,
                 http_timeout=None, extra_files=None):
            if method == "getMe":
                self.get_me_calls += 1
                if self.get_me_works:
                    return {"id": 1, "username": "test_bot"}
            raise OSError("[Errno 60] Operation timed out")

    def _bot(self, get_me_works):
        from src import telegram
        return telegram.Bot(self._Blocked(get_me_works), chat_id="1")

    def test_silence_alone_is_not_an_error(self):
        """Limitə çatana qədər sükut normaldır — həyəcan siqnalı yoxdur."""
        from src import telegram
        bot = self._bot(get_me_works=True)
        for _ in range(telegram.BLIND_POLL_LIMIT - 1):
            self.assertEqual(bot.get_updates(timeout=25), [])
        self.assertEqual(bot.transport.get_me_calls, 0)

    def test_silence_with_live_api_stays_silent(self):
        """API cavab verirsə, uzun sükut yenə də nasazlıq deyil."""
        from src import telegram
        bot = self._bot(get_me_works=True)
        for _ in range(telegram.BLIND_POLL_LIMIT + 3):
            self.assertEqual(bot.get_updates(timeout=25), [])
        self.assertGreater(bot.transport.get_me_calls, 0)

    def test_unreachable_api_raises(self):
        """Bağlantı heç qurulmursa — bu, blokdur, sükut deyil."""
        from src import telegram
        bot = self._bot(get_me_works=False)
        for _ in range(telegram.BLIND_POLL_LIMIT - 1):
            bot.get_updates(timeout=25)
        with self.assertRaises(telegram.TelegramUnreachable):
            bot.get_updates(timeout=25)

    def test_successful_poll_resets_the_counter(self):
        from src import telegram
        transport = telegram.MockTransport()
        bot = telegram.Bot(transport, chat_id="1")
        bot._blind_polls = telegram.BLIND_POLL_LIMIT + 5
        bot.get_updates(timeout=0)
        self.assertEqual(bot._blind_polls, 0)


class AgentTiming(unittest.TestCase):
    """09.09.2026: bir şəkil qaçışı 6 saat sürdü, telemetriya 142s dedi.

    Səbəb: uğurlu çağırışlarda yalnız claude CLI-nin öz `duration_ms`
    ölçüsü yazılırdı — kvota gözləməsi və proses növbəsi ona daxil deyil.
    """

    def _result(self, duration_ms, wall_ms):
        from src import llm
        return llm.AgentResult(name="t", ok=True,
                               duration_ms=duration_ms, wall_ms=wall_ms)

    def test_long_wait_is_flagged(self):
        # model 40s işlədi, real vaxt 6 saat
        self.assertTrue(self._result(40_000, 21_600_000).stalled)

    def test_normal_run_is_not_flagged(self):
        self.assertFalse(self._result(40_000, 42_000).stalled)

    def test_short_absolute_gap_is_not_flagged(self):
        """2s → 10s nisbətcə böyükdür, amma araşdırmağa dəyməz."""
        self.assertFalse(self._result(2_000, 10_000).stalled)

    def test_missing_measurement_is_not_flagged(self):
        self.assertFalse(self._result(0, 0).stalled)
        self.assertFalse(self._result(40_000, 0).stalled)


class JsonExtraction(unittest.TestCase):
    def test_fenced_and_bare(self):
        from src.llm import extract_json
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('mətn {"a": 1} sonra'), {"a": 1})
        self.assertIsNone(extract_json("heç bir json yoxdur"))


class ApprovalFlow(unittest.TestCase):
    def setUp(self):
        from src import approval, queue, telegram
        self.approval, self.queue, self.telegram = approval, queue, telegram
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = queue.QUEUE
        queue.QUEUE = Path(self.tmp.name) / "queue.json"
        self._orig_settings = approval.SETTINGS
        approval.SETTINGS = Path(self.tmp.name) / "settings.json"
        # Gözləmə vəziyyəti testlər arasında sızmamalıdır
        self._orig_pending = approval.PENDING_FILE
        approval.PENDING_FILE = Path(self.tmp.name) / "pending.json"
        self.transport = telegram.MockTransport()
        self.bot = telegram.Bot(transport=self.transport, chat_id="1")
        self.item = queue.enqueue(
            item_id="x", post="mətn " * 40, first_comment="mənbə",
            hashtags=[], chosen={"title": "T"}, scores={"overall": 7})

    def tearDown(self):
        self.queue.QUEUE = self._orig
        self.approval.SETTINGS = self._orig_settings
        self.approval.PENDING_FILE = self._orig_pending
        self.tmp.cleanup()

    def _press(self, action, ident="x"):
        return self.approval.handle_callback(
            {"update_id": 1, "callback_query": {"id": "c", "data": f"a|{ident}|{action}"}},
            self.bot, [])

    def test_approve_schedules(self):
        self._press("ok")
        self.assertEqual(self.queue.get("x").status, self.queue.SCHEDULED)

    def test_terminal_item_not_reprocessed(self):
        self._press("skip")
        self._press("ok")            # köhnə mesajdan təkrar basma
        self.assertEqual(self.queue.get("x").status, self.queue.SKIPPED)

    def test_failing_callback_ack_does_not_block(self):
        class Failing(self.telegram.MockTransport):
            def call(self, method, payload, file_field=None, file_path=None,
                     http_timeout=None):
                if method in ("answerCallbackQuery", "editMessageReplyMarkup"):
                    raise RuntimeError("400 Bad Request")
                return super().call(method, payload, file_field, file_path)

        bot = self.telegram.Bot(transport=Failing(), chat_id="1")
        self.approval.handle_callback(
            {"update_id": 1, "callback_query": {"id": "old", "data": "a|x|bank"}},
            bot, [])
        self.assertEqual(self.queue.get("x").status, self.queue.APPROVED)

    def test_keyboard_has_every_action(self):
        """Klaviaturadan düymə düşməməlidir.

        Real səhv: karusel düyməsi əlavə edilərkən «Mətni dəyiş» və
        «Keç» düymələri təsadüfən silindi.
        """
        rows = self.approval.keyboard(self.item)
        actions = {b["callback_data"].split("|")[-1] for r in rows for b in r}
        self.assertEqual(
            actions,
            {"ok", "bank", "img", "photo", "rw", "ed", "skip"})
        for row in rows:
            self.assertLessEqual(len(row), 2, "sətirdə 2-dən çox düymə")
        for row in rows:
            for button in row:
                self.assertLessEqual(len(button["callback_data"].encode()), 64)

    def test_bare_link_offers_post(self):
        """Link atmaq kifayətdir — /topic yazmağa ehtiyac yoxdur."""
        from src import config
        orig = self.approval.URL_STORE
        self.approval.URL_STORE = Path(self.tmp.name) / "urls.json"
        try:
            out = self.approval.handle_message(
                {"update_id": 1, "message": {"text": "bax: https://example.com/a"}},
                self.bot, [])
            self.assertIn("link təklifi", out)
            kb = self.transport.calls[-1]["payload"]["reply_markup"]["inline_keyboard"]
            token = kb[0][0]["callback_data"].split("|")[1]
            self.assertEqual(self.approval._recall_url(token), "https://example.com/a")
            # callback_data Telegram-ın 64 bayt həddini aşmamalıdır
            self.assertLessEqual(len(kb[0][0]["callback_data"].encode()), 64)
        finally:
            self.approval.URL_STORE = orig

    def test_link_can_be_declined(self):
        orig = self.approval.URL_STORE
        self.approval.URL_STORE = Path(self.tmp.name) / "urls.json"
        try:
            token = self.approval._remember_url("https://example.com/b")
            out = self.approval.handle_callback(
                {"update_id": 1, "callback_query": {
                    "id": "c", "data": f"a|{token}|dropurl",
                    "message": {"message_id": 5}}}, self.bot, [])
            self.assertIn("ləğv", out)
        finally:
            self.approval.URL_STORE = orig

    def test_unknown_callback_is_safe(self):
        self.assertIn("naməlum", self._press("zibir").lower() + self.approval.handle_callback(
            {"update_id": 2, "callback_query": {"id": "c", "data": "zibil"}}, self.bot, []).lower())


class RateLimits(unittest.TestCase):
    """Ən vacib qoruyucu: gün ərzində bir neçə post çıxmamalıdır.

    Real qüsur idi: bank hər tick-də bir post yayımlayırdı —
    5 postluq bank 75 dəqiqəyə boşalırdı.
    """

    def setUp(self):
        from src import publisher, queue
        self.publisher, self.queue = publisher, queue
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = queue.QUEUE
        queue.QUEUE = Path(self.tmp.name) / "queue.json"

    def tearDown(self):
        self.queue.QUEUE = self._orig
        self.tmp.cleanup()

    def _bank(self, count):
        for i in range(count):
            item = self.queue.enqueue(
                item_id=f"b{i}", post="p", first_comment="", hashtags=[],
                chosen={"title": f"P{i}"}, scores={"overall": 7})
            self.queue.set_status(item, self.queue.APPROVED)

    def _publish(self, item, when=None):
        item.linkedin_urn = f"urn:{item.id}"
        item.published_at = (when or datetime.now(timezone.utc)).isoformat()
        self.queue.set_status(item, self.queue.PUBLISHED)

    def test_bank_does_not_drain(self):
        self._bank(5)
        published = 0
        for _ in range(6):
            due = self.publisher.pick_due(from_bank=True)
            if due:
                self._publish(due[0])
                published += 1
        self.assertEqual(published, 1, "gün ərzində bir postdan çox çıxdı")
        self.assertEqual(len(self.queue.bank()), 4, "qalanlar bankda qalmalıdır")

    def test_daily_limit_message(self):
        self._bank(2)
        self._publish(self.queue.get("b0"))
        blocked = self.publisher.rate_limit_block()
        self.assertIn("gündəlik hədd", blocked)

    def test_minimum_gap_enforced(self):
        """Gündəlik hədd qaldırılsa da minimum fasilə qalır."""
        from src import config
        original = config.MAX_POSTS_PER_DAY
        config.MAX_POSTS_PER_DAY = 5          # gündəlik hədd yolu açıq
        try:
            self._bank(2)
            self._publish(self.queue.get("b0"),
                          datetime.now(timezone.utc) - timedelta(hours=2))
            blocked = self.publisher.rate_limit_block()
            self.assertIn("fasilə", blocked)
            self.assertEqual(self.publisher.pick_due(from_bank=True), [])
        finally:
            config.MAX_POSTS_PER_DAY = original

    def test_gap_passes_after_enough_time(self):
        from src import config
        original = config.MAX_POSTS_PER_DAY
        config.MAX_POSTS_PER_DAY = 5
        try:
            self._bank(2)
            self._publish(
                self.queue.get("b0"),
                datetime.now(timezone.utc)
                - timedelta(hours=config.MIN_HOURS_BETWEEN_POSTS + 1))
            self.assertEqual(self.publisher.rate_limit_block(), "")
        finally:
            config.MAX_POSTS_PER_DAY = original

    def test_yesterday_post_does_not_block(self):
        self._bank(2)
        self._publish(self.queue.get("b0"),
                      datetime.now(timezone.utc) - timedelta(days=2))
        self.assertEqual(self.publisher.rate_limit_block(), "")
        self.assertEqual(len(self.publisher.pick_due(from_bank=True)), 1)

    def test_multiple_due_yields_one(self):
        now = datetime.now(timezone.utc)
        for i in range(3):
            item = self.queue.enqueue(
                item_id=f"s{i}", post="p", first_comment="", hashtags=[],
                chosen={"title": f"S{i}"}, scores={"overall": 7})
            self.queue.set_status(item, self.queue.APPROVED)
            self.queue.schedule(item, now - timedelta(minutes=10 + i))
        self.assertEqual(len(self.publisher.pick_due()), 1)

    def test_publish_item_refuses_when_rate_limited(self):
        from src import linkedin
        self._bank(2)
        self._publish(self.queue.get("b0"))
        token = linkedin.Token(access_token="t", person_urn="u",
                               expires_at=datetime.now(timezone.utc).isoformat(),
                               obtained_at="")
        with self.assertRaises(self.publisher.PublishError):
            self.publisher.publish_item(self.queue.get("b1"), token)

    def test_force_bypasses_rate_limit(self):
        """/now --force kimi açıq istifadəçi əmri hədd tanımamalıdır."""
        self._bank(2)
        self._publish(self.queue.get("b0"))
        result = self.publisher.publish_item(
            self.queue.get("b1"), None, dry_run=True, force=True)
        self.assertTrue(result["warnings"])


class PublishGuards(unittest.TestCase):
    def setUp(self):
        from src import publisher, queue
        self.publisher, self.queue = publisher, queue
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = queue.QUEUE
        queue.QUEUE = Path(self.tmp.name) / "queue.json"
        self._orig_lock = publisher.LOCK
        publisher.LOCK = Path(self.tmp.name) / "publish.lock"

    def tearDown(self):
        self.queue.QUEUE = self._orig
        self.publisher.LOCK = self._orig_lock
        self.tmp.cleanup()

    def _item(self, overall=7):
        return self.queue.enqueue(
            item_id="p", post="m", first_comment="c", hashtags=[],
            chosen={"title": "T"}, scores={"overall": overall})

    def test_low_score_blocked(self):
        self.assertTrue(self.publisher.score_block(self._item(overall=3)))

    def test_good_score_allowed(self):
        self.assertEqual(self.publisher.score_block(self._item(overall=7)), "")

    def test_lock_is_exclusive(self):
        with self.publisher.Lock():
            with self.assertRaises(self.publisher.PublishError):
                with self.publisher.Lock():
                    pass
        self.assertFalse(self.publisher.LOCK.exists())

    def test_double_publish_rejected(self):
        from src import linkedin
        item = self._item()
        item.linkedin_urn = "urn:li:share:1"
        self.queue.save(item)
        token = linkedin.Token(access_token="t", person_urn="u",
                               expires_at=datetime.now(timezone.utc).isoformat(),
                               obtained_at="")
        with self.assertRaises(self.publisher.PublishError):
            self.publisher.publish_item(self.queue.get("p"), token)


class SourceParsing(unittest.TestCase):
    RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Test AI story</title><link>https://x.test/1</link>
      <pubDate>Mon, 07 Sep 2026 10:00:00 GMT</pubDate>
      <description>Bir təsvir</description><category>AI</category></item>
    </channel></rss>"""

    ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Atom AI story</title>
      <link rel="alternate" href="https://x.test/2"/>
      <updated>2026-09-07T10:00:00Z</updated><summary>Xülasə</summary></entry>
    </feed>"""

    def _parse(self, blob):
        from src import sources
        feed = sources.Feed("t", "Test", "http://x", 1.0)
        return sources._parse_feed(feed, blob.encode())

    def test_rss(self):
        items = self._parse(self.RSS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://x.test/1")
        self.assertIsNotNone(items[0].published)

    def test_atom(self):
        items = self._parse(self.ATOM)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://x.test/2")
        self.assertIsNotNone(items[0].published)


class ManualTopic(unittest.TestCase):
    """/topic <link> axını — saxta agentlərlə, şəbəkəsiz."""

    def setUp(self):
        from src import llm, pipeline, state
        self.pipeline, self.llm = pipeline, llm
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_runs = state.config.RUNS_DIR
        state.config.RUNS_DIR = Path(self.tmp.name)

        self._orig_meta = pipeline._page_meta
        pipeline._page_meta = lambda url: {"title": "Test məqalə", "summary": "xülasə"}

        self._orig_call = llm.call_agent

        def fake(name, system_prompt, user_prompt, **kw):
            data = {
                "researcher": {
                    "headline": "h", "summary": "s",
                    "primary_source_url": "https://openai.com/x",
                    "facts": [{"claim": "birinci fakt", "confidence": "high"},
                              {"claim": "ikinci fakt", "confidence": "high"}],
                    "numbers": [{"label": "xərc", "value": "600"}]},
                "writer": {
                    "angles": [{"id": 1, "type": "contrarian", "headline": "h",
                                "thesis": "t", "strength": 9}],
                    "chosen_angle_id": 1,
                    "post": "Hook sətri burada.\n\n• Fakt bir\n• Fakt iki\n\n"
                            "Nəticə iki cümlədir. Konkretdir.\n\nSual?\n\n#AI #Agents",
                    "thesis": "t", "first_comment": "Mənbə: https://eski.example/x"},
                "reviewer": {
                    "fact_check": {"verdict": "ok", "issues": []},
                    "skeptic": {"stop_scroll": 8, "would_comment": True,
                                "cringe": [], "verdict": "ok"},
                    "risk": {"issues": [], "verdict": "ok"},
                    "scores": {"hook": 8, "concreteness": 8, "local_relevance": 5,
                               "voice": 7, "overall": 7},
                    "must_fix": [], "publish_recommendation": "publish"},
            }.get(name, {})
            return llm.AgentResult(name=name, ok=True, text="", data=data,
                                   usage={"input_tokens": 10, "output_tokens": 5},
                                   cost_usd=0.01, duration_ms=100, model="test")

        llm.call_agent = fake
        pipeline.llm.call_agent = fake

    def tearDown(self):
        from src import state
        self.llm.call_agent = self._orig_call
        self.pipeline.llm.call_agent = self._orig_call
        self.pipeline._page_meta = self._orig_meta
        state.config.RUNS_DIR = self._orig_runs
        self.tmp.cleanup()

    def test_produces_post(self):
        result = self.pipeline.run_from_url("https://example.com/a", verbose=False)
        self.assertTrue(result.ok, result.error)
        self.assertIn("Hook", result.post)
        self.assertEqual(result.chosen["link"], "https://example.com/a")
        self.assertEqual(result.scores["overall"], 7)

    def test_hashtags_from_post_body(self):
        result = self.pipeline.run_from_url("https://example.com/a", verbose=False)
        self.assertEqual(result.hashtags, ["#AI", "#Agents"])

    def test_first_comment_uses_primary_source(self):
        result = self.pipeline.run_from_url("https://example.com/a", verbose=False)
        self.assertIn("openai.com", result.first_comment)
        self.assertNotIn("eski.example", result.first_comment)


class AtomicStore(unittest.TestCase):
    """Vəziyyət faylları yarımçıq yazıdan qorunmalıdır.

    Real risk: `make watch` prosesi dayandırılanda yazı yarıda qalsa,
    bütün növbə (postlar, cədvəl, tarixçə) itə bilər.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_temp_file_left(self):
        from src import store
        store.write_json(self.path, {"a": 1})
        store.write_json(self.path, {"a": 2})
        leftovers = [p.name for p in self.path.parent.iterdir()
                     if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        self.assertEqual(store.read_json(self.path), {"a": 2})

    def test_backup_created_on_second_write(self):
        from src import store
        store.write_json(self.path, {"v": 1})
        store.write_json(self.path, {"v": 2})
        self.assertTrue(self.path.with_suffix(".json.bak").exists())

    def test_recovers_from_corruption(self):
        from src import store
        store.write_json(self.path, {"v": 1})
        store.write_json(self.path, {"v": 2})
        self.path.write_text('{"v": 2, "broke')      # yarımçıq yazı
        self.assertEqual(store.read_json(self.path), {"v": 1})

    def test_missing_file_returns_default(self):
        from src import store
        self.assertEqual(store.read_json(self.path, {"d": True}), {"d": True})

    def test_queue_survives_corruption(self):
        from src import queue
        orig = queue.QUEUE
        queue.QUEUE = self.path
        try:
            queue.enqueue(item_id="a", post="p", first_comment="", hashtags=[],
                          chosen={"title": "A"}, scores={})
            queue.enqueue(item_id="b", post="p", first_comment="", hashtags=[],
                          chosen={"title": "B"}, scores={})
            self.path.write_text('{"items": [{"id"')
            self.assertEqual([i.id for i in queue.all_items()], ["a"])
        finally:
            queue.QUEUE = orig


class LinkedInVersion(unittest.TestCase):
    """API versiyası sıradan çıxsa yayım dayanmamalıdır."""

    def setUp(self):
        from src import linkedin
        self.li = linkedin
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_cache = linkedin.VERSION_CACHE
        linkedin.VERSION_CACHE = Path(self.tmp.name) / "versions.json"
        self._orig_env = os.environ.get("LINKEDIN_API_VERSION")

    def tearDown(self):
        self.li.VERSION_CACHE = self._orig_cache
        if self._orig_env is None:
            os.environ.pop("LINKEDIN_API_VERSION", None)
        else:
            os.environ["LINKEDIN_API_VERSION"] = self._orig_env
        self.tmp.cleanup()

    def _cache(self, active):
        from src import store
        store.write_json(self.li.VERSION_CACHE,
                         {"checked_at": datetime.now(timezone.utc).isoformat(),
                          "active": active, "newest": active[-1] if active else ""})

    def test_dead_version_falls_back(self):
        os.environ["LINKEDIN_API_VERSION"] = "202401"
        self._cache(["202509", "202608"])
        self.assertEqual(self.li.current_version(), "202608")

    def test_active_preference_is_kept(self):
        os.environ["LINKEDIN_API_VERSION"] = "202509"
        self._cache(["202509", "202608"])
        self.assertEqual(self.li.current_version(), "202509")

    def test_no_cache_uses_preference(self):
        os.environ["LINKEDIN_API_VERSION"] = "202509"
        self.assertEqual(self.li.current_version(), "202509")

    def test_candidates_cover_past_and_future(self):
        cands = self.li._candidate_versions(months_back=12, months_forward=3)
        self.assertGreaterEqual(len(cands), 15)
        self.assertTrue(all(len(c) == 6 and c.isdigit() for c in cands))

    def test_version_recovery_only_on_426(self):
        from src.net import Response
        self.assertFalse(self.li._version_recovery(Response(403, b"{}", {})))
        self.assertFalse(
            self.li._version_recovery(Response(426, b'{"code":"OTHER"}', {})))


class AdminCommands(unittest.TestCase):
    def setUp(self):
        from src import approval, queue, telegram
        self.approval, self.queue = approval, queue
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = queue.QUEUE, approval.SETTINGS
        queue.QUEUE = Path(self.tmp.name) / "queue.json"
        approval.SETTINGS = Path(self.tmp.name) / "settings.json"
        self.bot = telegram.Bot(transport=telegram.MockTransport(), chat_id="1")

    def tearDown(self):
        self.queue.QUEUE, self.approval.SETTINGS = self._orig
        self.tmp.cleanup()

    def test_all_commands_are_safe_when_empty(self):
        """Boş sistemdə heç bir əmr istisna atmamalıdır."""
        for cmd in ("/help", "/status", "/bank", "/preview", "/now",
                    "/undo", "/skip", "/edit", "/topic", "/pause", "/resume"):
            out = self.approval.handle_command(cmd, self.bot)
            self.assertIsInstance(out, str, cmd)

    def test_help_lists_every_command(self):
        for cmd, _ in self.approval.COMMAND_CATALOG:
            self.assertIn(f"/{cmd}", self.approval.HELP)

    def test_catalog_is_telegram_valid(self):
        """Telegram əmr adları: yalnız kiçik hərf/rəqəm/alt xətt, ≤32 simvol."""
        import re
        for cmd, desc in self.approval.COMMAND_CATALOG:
            self.assertRegex(cmd, r"^[a-z0-9_]{1,32}$", cmd)
            self.assertTrue(0 < len(desc) <= 256, cmd)

    def test_every_catalog_command_is_handled(self):
        """Qeydiyyatdan keçən hər əmrin işləyən emalçısı olmalıdır."""
        for cmd, _ in self.approval.COMMAND_CATALOG:
            out = self.approval.handle_command(f"/{cmd}", self.bot)
            self.assertNotIn("naməlum", out.lower(), cmd)

    def test_unknown_command_is_handled(self):
        out = self.approval.handle_command("/zibil", self.bot)
        self.assertIn("naməlum", out.lower())


class GuidedCommands(unittest.TestCase):
    """Arqumentsiz əmr sual verməli və cavabı gözləməlidir."""

    def setUp(self):
        from src import approval, queue, telegram
        self.approval, self.queue = approval, queue
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = (queue.QUEUE, approval.SETTINGS, approval.PENDING_FILE)
        queue.QUEUE = Path(self.tmp.name) / "queue.json"
        approval.SETTINGS = Path(self.tmp.name) / "settings.json"
        approval.PENDING_FILE = Path(self.tmp.name) / "pending.json"
        self.transport = telegram.MockTransport()
        self.bot = telegram.Bot(transport=self.transport, chat_id="1")

    def tearDown(self):
        (self.queue.QUEUE, self.approval.SETTINGS,
         self.approval.PENDING_FILE) = self._orig
        self.tmp.cleanup()

    def _post(self):
        return self.queue.enqueue(
            item_id="x", post="mətn " * 40, first_comment="c", hashtags=[],
            chosen={"title": "T"}, scores={"overall": 7})

    def test_topic_without_link_asks(self):
        out = self.approval.handle_command("/topic", self.bot)
        self.assertIn("gözlənilir", out)
        self.assertEqual(self.approval.get_pending()["action"], "topic")

    def test_edit_without_text_asks(self):
        self._post()
        out = self.approval.handle_command("/edit", self.bot)
        self.assertIn("gözlənilir", out)
        self.assertEqual(self.approval.get_pending()["action"], "edit")

    def test_pending_is_cleared_after_answer(self):
        self._post()
        self.approval.set_pending("edit")
        from src import editor
        orig = editor.apply_instruction
        editor.apply_instruction = lambda p, f, i, a=None: {
            "post": p, "first_comment": f, "changes": ["x"], "warning": ""}
        self.approval.editor.apply_instruction = editor.apply_instruction
        try:
            self.approval.handle_message(
                {"message": {"text": "tonu yumşalt"}}, self.bot, [])
            self.assertEqual(self.approval.get_pending(), {})
        finally:
            editor.apply_instruction = orig
            self.approval.editor.apply_instruction = orig

    def test_pending_expires(self):
        from src import store
        store.write_json(self.approval.PENDING_FILE, {
            "action": "edit",
            "asked_at": (datetime.now(timezone.utc)
                         - timedelta(minutes=60)).isoformat()})
        self.assertEqual(self.approval.get_pending(), {})

    def test_command_beats_pending(self):
        """Gözləmə açıqdırsa da, «/» ilə başlayan mətn əmr sayılır."""
        self.approval.set_pending("edit")
        out = self.approval.handle_message(
            {"message": {"text": "/status"}}, self.bot, [])
        self.assertEqual(out, "status")

    def test_destructive_commands_confirm_first(self):
        item = self._post()
        self.queue.set_status(item, self.queue.APPROVED)
        out = self.approval.handle_command("/now", self.bot)
        self.assertIn("təsdiq", out)
        kb = self.transport.calls[-1]["payload"]["reply_markup"]["inline_keyboard"]
        actions = {b["callback_data"].split("|")[-1] for r in kb for b in r}
        self.assertIn("donow", actions)
        self.assertIn("cancelask", actions)
        # təsdiq olunmayıb — status dəyişməməlidir
        self.assertEqual(self.queue.get("x").status, self.queue.APPROVED)

    def test_skip_confirms_before_acting(self):
        self._post()
        self.approval.handle_command("/skip", self.bot)
        self.assertEqual(self.queue.get("x").status, self.queue.PENDING)

    def test_cancel_clears_pending(self):
        self.approval.set_pending("edit")
        self.approval.handle_callback(
            {"callback_query": {"id": "c", "data": "a|-|cancelask",
                                "message": {"message_id": 1}}}, self.bot, [])
        self.assertEqual(self.approval.get_pending(), {})


class Proposals(unittest.TestCase):
    def setUp(self):
        from src import proposals
        self.p = proposals
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = proposals.STORE
        proposals.STORE = Path(self.tmp.name) / "proposals.json"

    def tearDown(self):
        self.p.STORE = self._orig
        self.tmp.cleanup()

    def _make(self):
        return self.p.create(
            [{"title": f"T{i}", "cluster_id": i} for i in range(3)], [])

    def test_create_and_pick(self):
        prop = self._make()
        self.assertEqual(prop.status, self.p.OPEN)
        self.assertEqual(len(prop.candidates), 3)
        self.p.mark_picked(prop, 1)
        self.assertEqual(self.p.get(prop.id).picked_index, 1)
        self.assertEqual(self.p.get(prop.id).status, self.p.PICKED)

    def test_auto_pick_after_deadline(self):
        prop = self._make()
        self.assertEqual(self.p.due_for_auto_pick(), [])
        later = datetime.now(timezone.utc) + timedelta(
            hours=self.p.AUTO_PICK_HOURS + 1)
        self.assertEqual(len(self.p.due_for_auto_pick(later)), 1)

    def test_picked_not_auto_picked(self):
        prop = self._make()
        self.p.mark_picked(prop, 0)
        later = datetime.now(timezone.utc) + timedelta(days=1)
        self.assertEqual(self.p.due_for_auto_pick(later), [])


class Performance(unittest.TestCase):
    def setUp(self):
        from src import publisher, queue
        self.publisher, self.queue = publisher, queue
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = queue.QUEUE
        queue.QUEUE = Path(self.tmp.name) / "queue.json"

    def tearDown(self):
        self.queue.QUEUE = self._orig
        self.tmp.cleanup()

    def _published(self, ident, angle, views, pillar="agents"):
        item = self.queue.enqueue(
            item_id=ident, post="p", first_comment="", hashtags=[],
            chosen={"title": "T", "pillar": pillar}, scores={"overall": 7},
            angles=[{"id": 1, "type": angle}], chosen_angle_id=1)
        item.status = self.queue.PUBLISHED
        item.metrics = {"views": views}
        self.queue.save(item)
        return item

    def test_ranks_angles_by_views(self):
        self._published("a", "contrarian", 500)
        self._published("b", "contrarian", 400)
        self._published("c", "practical", 100)
        report = self.publisher.performance_report()
        self.assertEqual(report["samples"], 3)
        self.assertEqual(report["by_angle"][0]["key"], "contrarian")
        self.assertEqual(report["by_angle"][0]["avg"], 450)

    def test_hint_needs_three_samples(self):
        from src.pipeline import _performance_hint
        self._published("a", "contrarian", 500)
        self.assertEqual(_performance_hint(), {})
        self._published("b", "contrarian", 400)
        self._published("c", "practical", 100)
        self.assertIn("best_angles", _performance_hint())

    def test_awaiting_metrics_picks_latest(self):
        item = self._published("a", "contrarian", 0)
        item.metrics = {}
        item.metrics_requested_at = datetime.now(timezone.utc).isoformat()
        self.queue.save(item)
        self.assertEqual(self.publisher.awaiting_metrics().id, "a")


class Archive(unittest.TestCase):
    def setUp(self):
        from src import archive, queue
        self.archive, self.queue = archive, queue
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_dir, self._orig_index = archive.ARCHIVE_DIR, archive.INDEX
        archive.ARCHIVE_DIR = Path(self.tmp.name)
        archive.INDEX = Path(self.tmp.name) / "INDEX.md"
        self._orig_queue = queue.QUEUE
        queue.QUEUE = Path(self.tmp.name) / "queue.json"

    def tearDown(self):
        self.archive.ARCHIVE_DIR = self._orig_dir
        self.archive.INDEX = self._orig_index
        self.queue.QUEUE = self._orig_queue
        self.tmp.cleanup()

    def test_slug_handles_azerbaijani(self):
        out = self.archive.slug("Şəkilli başlıq: 3,2 milyard — Google")
        self.assertRegex(out, r"^[a-z0-9-]+$")
        self.assertIn("sekilli", out)

    def test_write_and_index(self):
        item = self.queue.enqueue(
            item_id="a", post="Post mətni burada", first_comment="Mənbə: x",
            hashtags=["#AI"], chosen={"title": "Test başlıq", "pillar": "agents"},
            scores={"overall": 8})
        item.status = self.queue.PUBLISHED
        item.linkedin_url = "https://linkedin.com/feed/x"
        item.published_at = datetime.now(timezone.utc).isoformat()
        self.queue.save(item)

        path = self.archive.write(item)
        body = path.read_text(encoding="utf-8")
        self.assertIn("Post mətni burada", body)
        self.assertIn("linkedin: https://linkedin.com/feed/x", body)
        self.assertIn("Mənbə: x", body)

        self.archive.rebuild_index()
        index = self.archive.INDEX.read_text(encoding="utf-8")
        self.assertIn("Test başlıq", index)
        self.assertIn("Cəmi: **1**", index)

    def test_sync_only_published(self):
        self.queue.enqueue(item_id="pending", post="p", first_comment="",
                           hashtags=[], chosen={"title": "T"}, scores={})
        self.assertEqual(self.archive.sync_all(), 0)


class PhotoRelevance(unittest.TestCase):
    """Şəkillərin mövzuya uyğunluğu.

    Real problem: Visual Director «laptop login screen dark» kimi hərfi
    sorğular yazırdı və adi noutbuk şəkilləri gəlirdi. Həll: üç səviyyəli
    sorğu (səhnə → metafora → geniş) + təsvir mətninə görə sıralama.
    """

    _CAPTIONS = (
        "man in hoodie typing laptop dark room",
        "rusty padlock chain metal fence",
        "empty office chairs morning light",
        "server room blue cables corridor",
        "woman presenting whiteboard meeting",
        "firefighter smoke industrial building",
        "child reading book library window",
    )

    def _distinct(self, count):
        """Bir-birindən həqiqətən fərqli təsvirlər — təkrar filtri
        eyni sözlü nümunələri birləşdirir və test yalan nəticə verir."""
        return [self._photo(c) for c in self._CAPTIONS[:count]]

    def _photo(self, caption, provider="Pexels"):
        from src.images.stock import Photo
        return Photo(url="u", provider=provider, photographer="p",
                     page_url="page", width=2000, height=3000, caption=caption)

    def test_matching_caption_scores_higher(self):
        from src.images import stock
        good = self._photo("man in hoodie hacking laptop in dark room")
        bad = self._photo("woman drinking coffee in bright cafe")
        query = "hooded hacker laptop dark room"
        self.assertGreater(stock._relevance(good, query, 0),
                           stock._relevance(bad, query, 0))

    def test_first_query_gets_priority(self):
        from src.images import stock
        photo = self._photo("hacker laptop dark")
        first = stock._relevance(photo, "hacker laptop dark", 0)
        third = stock._relevance(photo, "hacker laptop dark", 2)
        self.assertGreater(first, third)

    def test_long_query_not_penalised(self):
        """5 sözlük sorğu 3 sözlük qədər bal ala bilməlidir."""
        from src.images import stock
        photo = self._photo("tired programmer late night office desk")
        short = stock._relevance(photo, "tired programmer office", 0)
        long_ = stock._relevance(photo, "tired programmer late night office", 0)
        self.assertAlmostEqual(short, long_, places=2)

    def test_stopwords_ignored(self):
        from src.images import stock
        self.assertNotIn("the", stock._terms("the man in the office"))
        self.assertIn("office", stock._terms("the man in the office"))

    def test_queries_fall_back(self):
        from src import images
        self.assertEqual(images.photo_queries({"photo_queries": ["a", "b"]}),
                         ["a", "b"])
        self.assertEqual(images.photo_queries({"pexels_query": "köhnə"}),
                         ["köhnə"])
        self.assertEqual(images.photo_queries({}), ["technology abstract"])

    def test_generic_fallback_is_detectable(self):
        """Ümumi ehtiyata düşmək səssiz olmamalıdır — çağıran bilməlidir."""
        from src import images
        self.assertTrue(images.queries_are_generic({}))
        self.assertTrue(images.queries_are_generic({"photo_queries": []}))
        self.assertFalse(images.queries_are_generic({"pexels_query": "rusty lock"}))
        self.assertFalse(
            images.queries_are_generic({"photo_queries": ["a", "b", "c"]}))

    def test_empty_queries_are_dropped(self):
        from src import images
        self.assertEqual(images.photo_queries({"photo_queries": ["", None, "x"]}),
                         ["x"])

    def test_duplicates_are_dropped(self):
        """İki paslı kilid bir seçim deməkdir, iki yox."""
        from src.images import stock
        photos = [
            self._photo("padlock, iron, metal, lock, rust, chain"),
            self._photo("iron, rust, metal, chain, padlock, lock"),
            self._photo("man in hoodie typing on laptop at night"),
        ]
        kept = stock._dedupe_by_concept(photos)
        self.assertEqual(len(kept), 2)
        self.assertIn("hoodie", kept[1].caption)

    def test_dedupe_runs_without_model_ranking(self):
        """09.09.2026: `make image`-də iki eyni kolba şəkli yan-yana düşdü.

        Təkrar filtri `pick_best` daxilində idi, o da post kontekstsiz
        atlanırdı — yəni filtr modelin seçiminə bağlı qalmışdı.
        """
        from src import images
        from src.images import stock
        photos = [
            self._photo("scientist holding pink flask gloves mask lab"),
            self._photo("pink flask gloves mask scientist laboratory"),
            self._photo("researcher adjusting equipment at night"),
        ]
        original = stock.search
        stock.search = lambda *a, **k: list(photos)
        images._PHOTO_MEMO.clear()
        try:
            # post="" → model sıralaması işləmir, filtr yenə də işləməlidir
            got = images._photo_cache(["lab"], post="")
            self.assertEqual(len(got), 2)
        finally:
            stock.search = original
            images._PHOTO_MEMO.clear()

    def test_picker_falls_back_when_model_fails(self):
        from src import llm
        from src.images import stock
        photos = self._distinct(6)
        original = llm.call_agent
        llm.call_agent = lambda *a, **k: llm.AgentResult(
            name="photo_picker", ok=False, error="sındı")
        try:
            picked = stock.pick_best(photos, "post", count=3)
            self.assertEqual(len(picked), 3)
        finally:
            llm.call_agent = original

    def test_picker_skipped_for_small_pools(self):
        """Namizəd azdırsa modelə müraciət etmirik — mənasız xərcdir."""
        from src.images import stock
        photos = [self._photo("a"), self._photo("b")]
        self.assertEqual(len(stock.pick_best(photos, "post", count=3)), 2)

    def test_picker_honours_model_order(self):
        from src import llm
        from src.images import stock
        photos = self._distinct(6)
        original = llm.call_agent
        llm.call_agent = lambda *a, **k: llm.AgentResult(
            name="photo_picker", ok=True,
            data={"picks": [{"index": 4, "why": "ən yaxşısı"},
                            {"index": 1, "why": "ikinci"}]})
        try:
            picked = stock.pick_best(photos, "post", count=3)
            self.assertEqual(picked[0].caption, photos[4].caption)
            self.assertEqual(picked[0].reason, "ən yaxşısı")
        finally:
            llm.call_agent = original

    def test_picker_ignores_out_of_range_index(self):
        from src import llm
        from src.images import stock
        photos = self._distinct(6)
        original = llm.call_agent
        llm.call_agent = lambda *a, **k: llm.AgentResult(
            name="photo_picker", ok=True,
            data={"picks": [{"index": 99, "why": "x"}, {"index": -1, "why": "y"}]})
        try:
            self.assertEqual(len(stock.pick_best(photos, "post", count=3)), 3)
        finally:
            llm.call_agent = original

    def test_director_schema_requires_queries(self):
        from src.images import schemas
        self.assertIn("photo_queries", schemas.DIRECTOR["required"])

    # 09.09.2026 — real hadisə: model JSON əvəzinə alət-çağırışı
    # sintaksisi ilə cavab verdi, `design_brief` qalan sahələri uddu.
    # Nəticə: `pexels_query` boş qaldı və kvant kalibrasiyası haqqında
    # post «technology abstract» fotoları ilə Telegram-a getdi.
    BROKEN_BRIEF = (
        'Tünd, laboratoriya-kimi minimalist fon.</design_brief>\n'
        '<parameter name="kicker">AI və kvant kalibrasiyası</parameter>\n'
        '<parameter name="pexels_query">superconducting quantum chip lab</parameter>\n'
        '<parameter name="support">Kubit kalibrasiyası: sabit addım</parameter>\n'
        '</invoke>\n'
    )

    def test_tagged_fields_are_recovered(self):
        from src import images
        fixed = images.recover_tagged_fields(
            {"design_brief": self.BROKEN_BRIEF, "headline": "h"})
        self.assertEqual(fixed["pexels_query"], "superconducting quantum chip lab")
        self.assertEqual(fixed["kicker"], "AI və kvant kalibrasiyası")
        self.assertEqual(fixed["support"], "Kubit kalibrasiyası: sabit addım")
        self.assertNotIn("<parameter", fixed["design_brief"])
        self.assertNotIn("</design_brief>", fixed["design_brief"])
        self.assertEqual(fixed["headline"], "h")

    def test_recovery_saves_the_photo_query(self):
        """Əsas nəticə: sorğu «technology abstract»-a düşməməlidir."""
        from src import images
        director = {"design_brief": self.BROKEN_BRIEF}
        self.assertEqual(images.photo_queries(director), ["technology abstract"])
        fixed = images.recover_tagged_fields(director)
        self.assertEqual(images.photo_queries(fixed),
                         ["superconducting quantum chip lab"])

    def test_recovery_never_overwrites_a_real_value(self):
        from src import images
        fixed = images.recover_tagged_fields({
            "design_brief": self.BROKEN_BRIEF,
            "kicker": "əsl dəyər",
        })
        self.assertEqual(fixed["kicker"], "əsl dəyər")

    def test_recovery_parses_a_list_field(self):
        from src import images
        fixed = images.recover_tagged_fields({
            "design_brief": 'brif</design_brief>\n'
                            '<parameter name="photo_queries">'
                            '["tired scientist lab", "cold blue machine", "quantum research"]'
                            '</parameter>',
        })
        self.assertEqual(images.photo_queries(fixed),
                         ["tired scientist lab", "cold blue machine", "quantum research"])

    def test_clean_director_is_untouched(self):
        from src import images
        clean = {"design_brief": "adi brif", "photo_queries": ["a", "b", "c"]}
        self.assertEqual(images.recover_tagged_fields(clean), clean)


class Branding(unittest.TestCase):
    def test_signature_uses_configured_name(self):
        from src import config
        from src.images import render
        orig = config.BRAND_NAME
        config.BRAND_NAME = "Test Adı"
        try:
            block = render.brand_block()
            self.assertIn("Test Adı", block)
            self.assertIn("position:absolute", block)
        finally:
            config.BRAND_NAME = orig

    def test_brand_color_applied(self):
        from src import config
        from src.images import render
        orig_name, orig_color = config.BRAND_NAME, config.BRAND_COLOR
        config.BRAND_NAME, config.BRAND_COLOR = "X", "#ff0055"
        try:
            self.assertIn("#ff0055", render.brand_block())
        finally:
            config.BRAND_NAME, config.BRAND_COLOR = orig_name, orig_color

    def test_signature_has_explicit_colour(self):
        """İmza `color:inherit` işlətməməlidir.

        Real səhv: imza dizayn blokunun qardaşıdır və `body`-nin defolt
        qara rəngini miras alırdı — qaranlıq fonda görünmürdü.
        """
        from src import config
        from src.images import render
        orig = config.BRAND_NAME
        config.BRAND_NAME = "Test"
        try:
            dark = render.brand_block(palette="gecə")
            light = render.brand_block(palette="kağız")
            self.assertNotIn("color:inherit", dark)
            self.assertIn("#f8fafc", dark)
            self.assertIn("#14110e", light)
        finally:
            config.BRAND_NAME = orig

    def test_name_is_prominent(self):
        """Ad linkdən açıq şəkildə iri və qalın olmalıdır."""
        import re

        from src import config
        from src.images import render
        orig_name, orig_handle = config.BRAND_NAME, config.BRAND_HANDLE
        config.BRAND_NAME, config.BRAND_HANDLE = "Ad", "linkedin.com/in/x"
        try:
            block = render.brand_block()
            sizes = [int(x) for x in re.findall(r"font-size:(\d+)px", block)]
            self.assertGreaterEqual(max(sizes), 30)
            self.assertGreater(max(sizes), min(sizes) + 10)
        finally:
            config.BRAND_NAME, config.BRAND_HANDLE = orig_name, orig_handle

    def test_handle_is_shortened(self):
        from src import config
        from src.images import render
        orig_name, orig_handle = config.BRAND_NAME, config.BRAND_HANDLE
        config.BRAND_NAME = "X"
        config.BRAND_HANDLE = "https://www.linkedin.com/in/samir-nabiyev-784a2831a/"
        try:
            block = render.brand_block()
            self.assertNotIn("https://", block)
            self.assertNotIn("www.", block)
            self.assertIn("linkedin.com/in/", block)
        finally:
            config.BRAND_NAME, config.BRAND_HANDLE = orig_name, orig_handle

    def test_missing_logo_is_safe(self):
        from src import config
        from src.images import render
        orig = config.BRAND_LOGO
        config.BRAND_LOGO = "assets/yoxdur.png"
        try:
            self.assertEqual(render.logo_data_uri(), "")
        finally:
            config.BRAND_LOGO = orig

    def test_wrap_injects_signature(self):
        from src import config
        from src.images import render
        orig = config.BRAND_NAME
        config.BRAND_NAME = "İmza Testi"
        try:
            self.assertIn("İmza Testi", render.wrap("<div></div>"))
            self.assertNotIn("İmza Testi", render.wrap("<div></div>", brand=False))
        finally:
            config.BRAND_NAME = orig


class TokenExpiry(unittest.TestCase):
    def _token(self, days):
        from src import linkedin
        return linkedin.Token(
            access_token="t", person_urn="u",
            expires_at=(datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
            obtained_at="", name="X")

    def test_expired_warns(self):
        self.assertTrue(self._token(-1).expired)

    def test_expiring_soon_window(self):
        self.assertTrue(self._token(3).expiring_soon)
        self.assertFalse(self._token(30).expiring_soon)

    def test_warning_text_mentions_command(self):
        from src import linkedin
        orig = linkedin.load_token
        linkedin.load_token = lambda: self._token(3)
        try:
            self.assertIn("li-renew", linkedin.expiry_warning())
        finally:
            linkedin.load_token = orig

    def test_no_warning_when_fresh(self):
        from src import linkedin
        orig = linkedin.load_token
        linkedin.load_token = lambda: self._token(40)
        try:
            self.assertEqual(linkedin.expiry_warning(), "")
        finally:
            linkedin.load_token = orig


class Calibration(unittest.TestCase):
    def setUp(self):
        from src import calibration
        self.cal = calibration
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = calibration.POSITIONING, calibration.VOICE_GUIDE
        calibration.POSITIONING = Path(self.tmp.name) / "positioning.md"
        calibration.VOICE_GUIDE = Path(self.tmp.name) / "voice_guide.md"

    def tearDown(self):
        self.cal.POSITIONING, self.cal.VOICE_GUIDE = self._orig
        self.tmp.cleanup()

    def test_reports_status(self):
        status = self.cal.status()
        for key in ("positioning_ok", "voice_ok", "complete"):
            self.assertIn(key, status)

    def test_placeholder_template_not_counted(self):
        self.cal.POSITIONING.write_text(
            "## 1. Kiməm?\n\n(doldurun)\n\n## 2. Auditoriya\n\n(doldurun)\n",
            encoding="utf-8")
        ok, filled, total = self.cal.positioning_filled()
        self.assertFalse(ok)
        self.assertEqual(filled, 0)

    def test_filled_prose_counted(self):
        body = "\n\n".join(
            f"## {i}. Bölmə\n\n" + ("Bu bölmədə real məzmun var. " * 4)
            for i in range(1, 6))
        self.cal.POSITIONING.write_text(body, encoding="utf-8")
        ok, filled, total = self.cal.positioning_filled()
        self.assertTrue(ok)
        self.assertEqual(filled, total)

    def test_voice_examples_counted_by_label(self):
        self.cal.VOICE_GUIDE.write_text(
            "<!-- NÜMUNƏLƏR BAŞLAYIR -->\n"
            "**Nümunə 1 — a**\n\n" + "mətn " * 30 + "\n\n---\n\n"
            "**Nümunə 2 — b**\n\n" + "mətn " * 30 + "\n"
            "<!-- NÜMUNƏLƏR BİTİR -->", encoding="utf-8")
        self.assertEqual(self.cal.voice_examples(), 2)

    def test_empty_voice_guide(self):
        self.cal.VOICE_GUIDE.write_text(
            "<!-- NÜMUNƏLƏR BAŞLAYIR -->\n\n<!-- NÜMUNƏLƏR BİTİR -->",
            encoding="utf-8")
        self.assertEqual(self.cal.voice_examples(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

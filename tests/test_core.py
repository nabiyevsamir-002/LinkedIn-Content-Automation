"""Oflayn testlər — şəbəkə və LLM olmadan, saniyələr içində işləyir.

Məqsəd: bir dəyişiklik başqa yeri sındırsa, bunu YAYIMDAN ƏVVƏL bilmək.
Bu sistemdə səhvin qiyməti yüksəkdir — LinkedIn-ə çıxan postu geri
qaytarmaq olmur.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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
        self.transport = telegram.MockTransport()
        self.bot = telegram.Bot(transport=self.transport, chat_id="1")
        self.item = queue.enqueue(
            item_id="x", post="mətn " * 40, first_comment="mənbə",
            hashtags=[], chosen={"title": "T"}, scores={"overall": 7})

    def tearDown(self):
        self.queue.QUEUE = self._orig
        self.approval.SETTINGS = self._orig_settings
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

    def test_unknown_callback_is_safe(self):
        self.assertIn("naməlum", self._press("zibir").lower() + self.approval.handle_callback(
            {"update_id": 2, "callback_query": {"id": "c", "data": "zibil"}}, self.bot, []).lower())


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

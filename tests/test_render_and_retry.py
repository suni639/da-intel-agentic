import datetime
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

from schema import StrategicAnalysis  # noqa: E402
from render import (  # noqa: E402
    enforce_link_allowlist, to_british, render_briefing, finalise_briefing, find_hedging,
)
import run_pipeline  # noqa: E402
from publish import parse_recipients, convert_markdown_to_newsletter_html  # noqa: E402


def sample_payload():
    return {
        "macro_view": [{"headline": "Deposit tokens go live", "detail": "Banks utilize 24/7 rails."}],
        "pillars": [
            {
                "name": "Sovereign Infrastructure & CBDCs",
                "synthesis": "Central banks prioritize synchronization.",
                "developments": [
                    {"article_id": "a1", "title": "BoE DSS update", "source": "BoE News",
                     "url": "https://www.bankofengland.co.uk/news/dss", "details": "Sandbox expanded."},
                ],
            },
            {
                "name": "Banking Infrastructure & Commercial Rails",
                "synthesis": "Commercial bank money is tokenized.",
                "developments": [
                    {"article_id": "a2", "title": "Fnality [GBP] launch", "source": "Ledger Insights",
                     "url": "https://www.ledgerinsights.com/fnality/", "details": "Live settlement."},
                    {"article_id": "a3", "title": "Made-up BIS paper", "source": "BIS",
                     "url": "https://www.bis.org/publ/fake123.htm", "details": "Hallucinated."},
                ],
            },
            {"name": "Frontier & Emerging Innovations", "synthesis": "None.", "developments": []},
        ],
        "structural_pain_points": {
            "interoperability_silos": "Silos.",
            "balance_sheet_and_liquidity_friction": "Friction.",
            "post_trade_plumbing_constraints": "Constraints.",
        },
        "new_high_signal_targets": [
            {"name": "Fnality", "url": "https://www.ledgerinsights.com/fnality", "rationale": "Track it."},
            {"name": "Project Agora", "url": "", "rationale": "Track it too."},
        ],
    }


ALLOWED = ["https://www.bankofengland.co.uk/news/dss", "https://www.ledgerinsights.com/fnality/"]


class TestSchema(unittest.TestCase):
    def test_accepts_list_pillars(self):
        analysis = StrategicAnalysis.model_validate(sample_payload())
        self.assertEqual(len(analysis.pillars), 3)

    def test_accepts_legacy_dict_pillars(self):
        payload = sample_payload()
        payload["pillars"] = {p["name"]: {k: v for k, v in p.items() if k != "name"} for p in payload["pillars"]}
        analysis = StrategicAnalysis.model_validate(payload)
        self.assertEqual(analysis.pillars[0].name.value, "Sovereign Infrastructure & CBDCs")

    def test_rejects_unknown_pillar(self):
        payload = sample_payload()
        payload["pillars"][0]["name"] = "Memecoins"
        with self.assertRaises(Exception):
            StrategicAnalysis.model_validate(payload)


class TestLinkAllowlist(unittest.TestCase):
    def test_untrusted_links_replaced(self):
        analysis = StrategicAnalysis.model_validate(sample_payload())
        warnings = enforce_link_allowlist(analysis, ALLOWED)
        devs = analysis.pillars[1].developments
        self.assertEqual(devs[0].url, "https://www.ledgerinsights.com/fnality/")
        self.assertTrue(devs[1].url.startswith("https://www.google.com/search?q=Made-up+BIS+paper"))
        # trailing-slash difference is tolerated
        self.assertEqual(analysis.new_high_signal_targets[0].url, "https://www.ledgerinsights.com/fnality")
        self.assertTrue(analysis.new_high_signal_targets[1].url.startswith("https://www.google.com/search?q="))
        self.assertEqual(len(warnings), 2)


class TestBritishEnglish(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(to_british("Tokenization was prioritized; banks utilize it."),
                         "Tokenisation was prioritised; banks utilise it.")
        self.assertEqual(to_british("We analyze and ORGANIZE."), "We analyse and ORGANISE.")

    def test_plain_english_swaps(self):
        from render import plain_english
        self.assertEqual(plain_english("Concurrently, DBS utilised Kinexys for its inaugural client."),
                         "At the same time, DBS used Kinexys for its first client.")
        self.assertEqual(plain_english("In order to settle"), "To settle")

    def test_exceptions_untouched(self):
        text = "The size of the prize; regulators seize assets; a citizen; a hazard."
        self.assertEqual(to_british(text), text)

    def test_hedging_detected(self):
        self.assertEqual(find_hedging("It is evident that settlement matters."), ["it is evident that"])


class TestArticleIdStripping(unittest.TestCase):
    def test_ids_removed_from_prose(self):
        from render import strip_article_ids
        self.assertEqual(strip_article_ids("DBS launched transfers (a128). Next (a2, a49) and [a7]."),
                         "DBS launched transfers. Next and.")
        self.assertEqual(strip_article_ids("Banks (articles a1 and a2) moved"), "Banks moved")
        self.assertEqual(strip_article_ids("Pillar (a) and a12 notes"), "Pillar (a) and a12 notes")


class TestRender(unittest.TestCase):
    def test_layout_and_links(self):
        analysis = StrategicAnalysis.model_validate(sample_payload())
        md = finalise_briefing(analysis, ALLOWED)
        self.assertTrue(md.startswith("## In one minute"))
        self.assertIn("## What happened", md)
        # No UK implications in the sample payload -> section omitted
        self.assertNotIn("## What it means for UK banks", md)
        # Old evergreen pain-points section is gone
        self.assertNotIn("holding things back", md)
        # The BoE item is detected as UK (even without the strategist's flag) and shown first
        happened = md.split("## What happened")[1]
        self.assertTrue(happened.lstrip().startswith("### UK"))
        self.assertLess(happened.index("BoE DSS update"), happened.index("### Banks and payments"))
        # Empty pillars are omitted; pillar syntheses are not rendered
        self.assertNotIn("### New technology", md)
        self.assertNotIn("prioritise synchronisation", md)
        # Brackets in titles are escaped so the link is not broken
        self.assertIn("[Fnality \\[GBP\\] launch](https://www.ledgerinsights.com/fnality/)", md)
        self.assertIn("Banks use 24/7 rails", md)  # utilize -> utilise -> use
        self.assertNotIn("fake123", md)
        # Headlines are terminated; publisher shown after the link
        self.assertIn("* **Deposit tokens go live.** Banks", md)
        self.assertIn("(https://www.bankofengland.co.uk/news/dss) *(BoE News)*:", md)
        # 'Worth watching' drops Fnality (already covered) and Project Agora (no source article),
        # so the section is omitted entirely
        self.assertNotIn("## Worth watching", md)

    def test_newsletter_is_plain(self):
        md = render_briefing(StrategicAnalysis.model_validate(sample_payload()))
        html = convert_markdown_to_newsletter_html("s", "2026-11-16", md)
        # No cards, coloured panels, borders or style sheet; every element styled inline.
        for banned in ("class=", "<style", "border", "gradient", "box-shadow"):
            self.assertNotIn(banned, html)
        self.assertNotRegex(html, r"background:#(?!ffffff)")
        self.assertIn("16 November 2026", html)
        self.assertRegex(html, r'<h2 style="[^"]+">In one minute</h2>')
        self.assertRegex(html, r'<a style="[^"]+" href="https://www\.bankofengland\.co\.uk/news/dss">')


class TestNewStructure(unittest.TestCase):
    def payload(self):
        p = sample_payload()
        p["macro_view"] = [{"headline": f"Point {i}", "detail": "Why it matters."} for i in range(5)]
        p["uk_implications"] = ["Monument puts pressure on UK deposit pricing.", "BoE consultation closes soon.",
                                "Third.", "Fourth is dropped."]
        devs = p["pillars"][1]["developments"]
        devs[0]["label"] = "Fnality goes live for sterling"
        devs.append({"article_id": "a9", "title": "Monument tokenised deposits", "source": "Finextra",
                     "url": "https://finextra.com/monument", "details": "Monument launched.", "uk": True})
        devs.append({"article_id": "a10", "title": "Thin item", "source": "X", "url": "https://x.com/t",
                     "details": "Thin.", "exclude": True})
        devs.append({"article_id": "a2", "title": "Duplicate citation", "source": "X",
                     "url": "https://x.com/d", "details": "Dup."})
        p["subject_hook"] = "Monument tokenised deposits; Fnality goes live."
        return p

    def test_sections_caps_uk_first_and_labels(self):
        from render import render_briefing
        md = render_briefing(StrategicAnalysis.model_validate(self.payload()))
        one_minute = md.split("## What it means for UK banks")[0]
        self.assertEqual(one_minute.count("* **Point"), 3)  # capped at 3
        uk = md.split("## What it means for UK banks")[1].split("## What happened")[0]
        self.assertEqual(uk.count("\n* "), 3)  # capped at 3
        happened = md.split("## What happened")[1]
        self.assertTrue(happened.lstrip().startswith("### UK"))
        self.assertLess(happened.index("Monument"), happened.index("### Banks and payments"))
        self.assertIn("[Fnality goes live for sterling](", md)  # label used as link text
        self.assertNotIn("Thin item", md)
        self.assertNotIn("Duplicate citation", md)

    def test_thin_items_dropped_only_from_weak_sources(self):
        from render import render_briefing
        p = self.payload()
        devs = p["pillars"][0]["developments"]
        devs += [
            {"article_id": "t1", "title": "IOSCO tokenisation report", "source": "IOSCO",
             "url": "https://iosco.org/r", "details": "IOSCO published a report.", "thin": True},
            {"article_id": "t2", "title": "Aggregator rehash", "source": "CoinMarketCap",
             "url": "https://cmc.com/x", "details": "Something happened.", "thin": True},
            {"article_id": "t3", "title": "Lloyds tokenised gilt pilot", "source": "CoinMarketCap",
             "url": "https://cmc.com/l", "details": "Lloyds ran a pilot.", "thin": True},
        ]
        md = render_briefing(StrategicAnalysis.model_validate(p))
        self.assertIn("IOSCO tokenisation report", md)   # primary source: kept
        self.assertNotIn("Aggregator rehash", md)         # weak source, not UK: dropped
        self.assertIn("Lloyds tokenised gilt pilot", md)  # UK: kept
        self.assertLess(md.index("Lloyds tokenised gilt pilot"), md.index("### Banks and payments"))

    def test_worth_watching_requires_source_article(self):
        from render import render_briefing
        p = self.payload()
        p["new_high_signal_targets"] = [
            {"name": "BoE consultation closes 30 January", "article_id": "a77",
             "url": "https://bankofengland.co.uk/c", "rationale": "Responses due."},
            {"name": "Canton progress", "article_id": "", "url": "", "rationale": "Ongoing."},
        ]
        md = render_briefing(StrategicAnalysis.model_validate(p))
        watching = md.split("## Worth watching")[1]
        self.assertIn("BoE consultation closes 30 January", watching)
        self.assertNotIn("Canton progress", watching)

    def test_uk_does_not_crowd_out_global_news(self):
        from render import MAX_ITEMS, MAX_UK_FIRST, render_briefing, selected_developments
        p = self.payload()
        p["pillars"][0]["developments"] = (
            [{"article_id": f"uk{i}", "title": f"Barclays item {i}", "url": f"https://x/uk{i}",
              "details": "UK detail.", "uk": True} for i in range(7)]
            + [{"article_id": f"g{i}", "title": f"Global item {i}", "url": f"https://x/g{i}",
                "details": "Global detail."} for i in range(10)])
        analysis = StrategicAnalysis.model_validate(p)
        chosen = selected_developments(analysis)
        self.assertEqual(len(chosen), MAX_ITEMS)
        self.assertEqual(sum(1 for _, d in chosen if d.uk), MAX_UK_FIRST)  # UK heading capped
        globals_shown = sum(1 for _, d in chosen if d.title.startswith("Global"))
        self.assertGreaterEqual(globals_shown, MAX_ITEMS - 7)  # global news keeps its slots
        md = render_briefing(StrategicAnalysis.model_validate(p))
        uk_block = md.split("### UK")[1].split("###")[0]
        self.assertEqual(uk_block.count("\n* "), MAX_UK_FIRST)

    def test_london_based_global_firm_not_uk(self):
        from render import is_uk
        from schema import Development
        d = Development(article_id="x", title="London-based Copper raises funding for custody in Asia",
                        details="The firm expands in Singapore.")
        self.assertFalse(is_uk(d))
        self.assertTrue(is_uk(Development(article_id="y", title="Bank of England consults", details="d")))

    def test_item_cap(self):
        from render import MAX_ITEMS, selected_developments
        p = self.payload()
        p["pillars"][0]["developments"] = [
            {"article_id": f"b{i}", "title": f"T{i}", "url": f"https://x/{i}", "details": "d"} for i in range(20)]
        chosen = selected_developments(StrategicAnalysis.model_validate(p))
        self.assertEqual(len(chosen), MAX_ITEMS)
        self.assertTrue(chosen[0][1].uk)  # UK item first even though its pillar comes later

    def test_subject(self):
        from render import subject_line
        import tempfile
        from publish import email_subject
        hook = subject_line(StrategicAnalysis.model_validate(self.payload()))
        self.assertEqual(hook, "Monument tokenised deposits; Fnality goes live")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(hook)
        self.assertEqual(email_subject("2026-11-23", f.name),
                         "Digital Asset Digest, 23 Nov: Monument tokenised deposits; Fnality goes live")
        self.assertEqual(email_subject("2026-11-23", "/nonexistent"), "Digital Asset Digest: 2026-11-23")

    def test_sentence_case_regression_headline_in_analysis(self):
        # Live bug: the headline itself was part of the reference text, so every word looked
        # like a proper noun and Title Case survived.
        p = self.payload()
        p["macro_view"] = [{"headline": "Commercial Banks Interlink Deposit Platforms to Support Continuous Dollar Transfers",
                            "detail": "DBS and J.P. Morgan connected their platforms so banks can move dollars at weekends."}]
        analysis = StrategicAnalysis.model_validate(p)
        md = finalise_briefing(analysis, ALLOWED)
        self.assertIn("**Commercial banks interlink deposit platforms to support continuous dollar transfers.**", md)

    def test_word_count_excludes_urls(self):
        from render import word_count
        self.assertEqual(word_count("* [Two words](https://example.com/a/very/long/path) *(Src)*: three more words"), 6)

    def test_source_quality_in_prompt(self):
        prompt_articles, _ = run_pipeline.index_articles([{"title": "t", "url": "u", "source": "CoinMarketCap"},
                                                          {"title": "t", "url": "u2", "source": "BoE News"}])
        self.assertEqual([a["quality"] for a in prompt_articles], ["aggregator", "primary"])


class TestEditorMerge(unittest.TestCase):
    def test_identity_fields_preserved(self):
        original = StrategicAnalysis.model_validate(sample_payload())
        edited_payload = sample_payload()
        edited_payload["pillars"][1]["developments"][0]["url"] = "https://evil.example/changed"
        edited_payload["pillars"][1]["developments"][0]["details"] = "Polished."
        edited = StrategicAnalysis.model_validate(edited_payload)
        merged = run_pipeline.merge_editor_prose(original, edited)
        dev = merged.pillars[1].developments[0]
        self.assertEqual(dev.url, "https://www.ledgerinsights.com/fnality/")
        self.assertEqual(dev.details, "Polished.")

    def test_shape_change_rejected(self):
        original = StrategicAnalysis.model_validate(sample_payload())
        edited_payload = sample_payload()
        edited_payload["macro_view"].append({"headline": "x", "detail": "y"})
        edited = StrategicAnalysis.model_validate(edited_payload)
        self.assertIsNone(run_pipeline.merge_editor_prose(original, edited))


class FakeAPIError(Exception):
    def __init__(self, code):
        super().__init__(f"error {code}")
        self.code = code


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, **kwargs):
        self.calls.append(model)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestRetry(unittest.TestCase):
    def call(self, client):
        return run_pipeline.generate_content_with_retry(
            client, "m1", "prompt", max_retries=3, fallback_models=["m2"], sleep=lambda s: None)

    def test_transient_then_success(self):
        client = FakeClient([FakeAPIError(503), FakeAPIError(429), "ok"])
        self.assertEqual(self.call(client), "ok")
        self.assertEqual(client.calls, ["m1", "m1", "m1"])

    def test_exhausted_transient_falls_back(self):
        client = FakeClient([FakeAPIError(503)] * 3 + ["ok"])
        self.assertEqual(self.call(client), "ok")
        self.assertEqual(client.calls, ["m1", "m1", "m1", "m2"])

    def test_not_found_switches_immediately(self):
        client = FakeClient([FakeAPIError(404), "ok"])
        self.assertEqual(self.call(client), "ok")
        self.assertEqual(client.calls, ["m1", "m2"])

    def test_auth_error_raises_without_retry(self):
        client = FakeClient([FakeAPIError(401)])
        with self.assertRaises(FakeAPIError):
            self.call(client)
        self.assertEqual(client.calls, ["m1"])

    def test_daily_quota_switches_model_immediately(self):
        daily = FakeAPIError(429)
        daily.args = ("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier",)
        client = FakeClient([daily, "ok"])
        self.assertEqual(self.call(client), "ok")
        self.assertEqual(client.calls, ["m1", "m2"])

    def test_network_error_is_retried(self):
        client = FakeClient([ConnectionError("reset"), "ok"])
        self.assertEqual(self.call(client), "ok")

    def test_parse_analysis_strips_fences(self):
        import json
        resp = SimpleNamespace(parsed=None, text="```json\n" + json.dumps(sample_payload()) + "\n```")
        self.assertIsInstance(run_pipeline.parse_analysis(resp), StrategicAnalysis)


class TestArticleRefs(unittest.TestCase):
    def test_index_and_resolve(self):
        feed = [
            {"title": "Fnality live", "url": "https://news.google.com/rss/articles/LONGOPAQUE?oc=5",
             "source": "FT", "published": "2026-11-15T09:00:00+00:00", "content": ""},
            {"title": "BoE DSS", "url": "https://bankofengland.co.uk/dss", "source": "BoE", "content": "x"},
        ]
        prompt_articles, by_id = run_pipeline.index_articles(feed)
        self.assertEqual(prompt_articles[0], {"id": "a1", "title": "Fnality live", "source": "FT",
                                              "quality": "trade", "published": "2026-11-15"})
        self.assertNotIn("url", prompt_articles[1])

        analysis = StrategicAnalysis.model_validate({
            "macro_view": [], "structural_pain_points": sample_payload()["structural_pain_points"],
            "pillars": [{"name": "Banking Infrastructure & Commercial Rails", "synthesis": "s", "developments": [
                {"article_id": "a1", "details": "d"},
                {"article_id": "a99", "title": "Ghost", "details": "invented"},
            ]}],
            "new_high_signal_targets": [{"name": "Fnality", "article_id": "a1", "rationale": "r"},
                                        {"name": "Other", "article_id": "", "rationale": "r"}],
        })
        run_pipeline.resolve_article_refs(analysis, by_id)
        devs = analysis.pillars[0].developments
        self.assertEqual(len(devs), 1)  # unknown id dropped
        self.assertEqual((devs[0].title, devs[0].source, devs[0].url),
                         ("Fnality live", "FT", "https://news.google.com/rss/articles/LONGOPAQUE?oc=5"))
        self.assertEqual(analysis.new_high_signal_targets[0].url, feed[0]["url"])
        self.assertEqual(analysis.new_high_signal_targets[1].url, "")


class TestStructuredRetry(unittest.TestCase):
    def test_truncated_json_is_regenerated(self):
        import json
        good = SimpleNamespace(parsed=None, text=json.dumps(sample_payload()), candidates=[])
        truncated = SimpleNamespace(parsed=None, text='{"macro_view": [{"headline": "cut', candidates=[])
        client = FakeClient([truncated, good])
        result = run_pipeline.generate_analysis(client, "m1", "prompt", "Test", attempts=2)
        self.assertIsInstance(result, StrategicAnalysis)
        self.assertEqual(len(client.calls), 2)

    def test_gives_up_after_attempts(self):
        truncated = SimpleNamespace(parsed=None, text='{"macro_view": [', candidates=[])
        client = FakeClient([truncated, truncated])
        with self.assertRaises(ValueError):
            run_pipeline.generate_analysis(client, "m1", "prompt", "Test", attempts=2)


class TestClient(unittest.TestCase):
    def test_client_uses_v1beta_for_json_mode(self):
        os.environ.pop("GEMINI_API_VERSION", None)
        client = run_pipeline.make_client("dummy-key")
        self.assertEqual(client._api_client._http_options.api_version, "v1beta")


class TestFinaliseRun(unittest.TestCase):
    def run_case(self, result, rc=0, dry=False):
        from unittest.mock import patch
        with patch.object(run_pipeline, "update_system_state") as upd, \
                patch.object(run_pipeline, "log_error"):
            code = run_pipeline.finalise_run(result, rc, [{"url": "u"}], dry)
        return code, upd.called

    def test_all_ok(self):
        self.assertEqual(self.run_case({"hugo": "ok", "email": "ok"}), (0, True))

    def test_partial_failure_saves_state_but_fails_run(self):
        self.assertEqual(self.run_case({"hugo": "failed", "email": "ok"}, rc=1), (1, True))

    def test_total_failure_keeps_state_for_retry(self):
        self.assertEqual(self.run_case({"hugo": "failed", "email": "failed"}, rc=1), (1, False))

    def test_publisher_crash(self):
        self.assertEqual(self.run_case({}, rc=1), (1, False))

    def test_dry_run_never_saves(self):
        self.assertEqual(self.run_case({"hugo": "dry-run", "email": "dry-run"}, dry=True), (0, False))


class TestStateAndPublish(unittest.TestCase):
    def test_prune_processed_urls(self):
        now = datetime.datetime(2026, 11, 16, tzinfo=datetime.timezone.utc)
        processed = {
            "old": (now - datetime.timedelta(days=200)).isoformat(),
            "new": (now - datetime.timedelta(days=5)).isoformat(),
            "bad": "not-a-date",
        }
        kept = run_pipeline.prune_processed_urls(processed, now=now, retention_days=120)
        self.assertEqual(set(kept), {"new", "bad"})

    def test_parse_recipients(self):
        self.assertEqual(parse_recipients("a@x.com; b@x.com,", default="me@x.com"), ["a@x.com", "b@x.com"])
        self.assertEqual(parse_recipients("", default="me@x.com"), ["me@x.com"])
        self.assertEqual(parse_recipients(None), [])


if __name__ == "__main__":
    unittest.main()

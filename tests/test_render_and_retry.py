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
from publish import wrap_section, parse_recipients, convert_markdown_to_newsletter_html  # noqa: E402


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

    def test_exceptions_untouched(self):
        text = "The size of the prize; regulators seize assets; a citizen; a hazard."
        self.assertEqual(to_british(text), text)

    def test_hedging_detected(self):
        self.assertEqual(find_hedging("It is evident that rails matter."), ["it is evident that"])


class TestRender(unittest.TestCase):
    def test_layout_and_links(self):
        analysis = StrategicAnalysis.model_validate(sample_payload())
        md = finalise_briefing(analysis, ALLOWED)
        self.assertTrue(md.startswith("## 1. MACRO VIEW"))
        for header in ["## 2. CORE PILLAR DEVELOPMENTS", "## 3. STRUCTURAL & OPERATIONAL PAIN POINTS",
                       "## 4. NEW HIGH-SIGNAL TARGETS FOR TRACKING"]:
            self.assertIn(header, md)
        # Fixed pillar order: Banking before Sovereign regardless of input order
        self.assertLess(md.index("### Banking Infrastructure"), md.index("### Sovereign Infrastructure"))
        # Empty pillars are omitted
        self.assertNotIn("### Frontier", md)
        # Brackets in titles are escaped so the link is not broken
        self.assertIn("[Fnality \\[GBP\\] launch](https://www.ledgerinsights.com/fnality/)", md)
        # Prose normalised to British English, titles untouched
        self.assertIn("synchronisation", md)
        self.assertIn("utilise", md)
        self.assertNotIn("fake123", md)
        # Headlines are terminated; publisher shown after the link
        self.assertIn("* **Deposit tokens go live.** Banks", md)
        self.assertIn("(https://www.bankofengland.co.uk/news/dss) *(BoE News)*:", md)

    def test_render_converts_to_html_cards(self):
        md = render_briefing(StrategicAnalysis.model_validate(sample_payload()))
        html = convert_markdown_to_newsletter_html("s", "d", md)
        self.assertIn('<h2>1. MACRO VIEW</h2><div class="synthesis-card">', html.replace("\n", ""))


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
                                              "published": "2026-11-15"})
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

    def test_wrap_section_is_case_and_number_insensitive(self):
        html = "<h2>2. Macro View</h2><p>x</p><h2>3. Other</h2><p>y</p>"
        self.assertEqual(wrap_section(html, "MACRO VIEW", "c"),
                         '<h2>2. Macro View</h2><div class="c"><p>x</p></div><h2>3. Other</h2><p>y</p>')
        self.assertEqual(wrap_section(html, "MISSING", "c"), html)

    def test_parse_recipients(self):
        self.assertEqual(parse_recipients("a@x.com; b@x.com,", default="me@x.com"), ["a@x.com", "b@x.com"])
        self.assertEqual(parse_recipients("", default="me@x.com"), ["me@x.com"])
        self.assertEqual(parse_recipients(None), [])


if __name__ == "__main__":
    unittest.main()

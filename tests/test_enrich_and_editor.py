import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import enrich  # noqa: E402
import run_pipeline  # noqa: E402
from render import find_hedging  # noqa: E402
from schema import StrategicAnalysis  # noqa: E402
from test_render_and_retry import FakeClient, sample_payload  # noqa: E402

ARTICLE_HTML = """<html><head><meta property="og:description" content="DBS and Kinexys launch 24/7 USD
tokenised deposit transfers."></head><body><nav><p>Home | News | Markets | Subscribe to our newsletter today</p></nav>
<article><p>Short.</p>
<p>DBS Bank and J.P. Morgan's Kinexys said on Monday that clients can now move USD deposit tokens between
Singapore and New York around the clock, including weekends.</p>
<p>The service settles in seconds and removes the need for pre-funding across time zones, the banks said.</p>
</article><footer><p>Copyright 2026 Example Media Ltd. All rights reserved worldwide.</p></footer></body></html>"""


class TestExcerpt(unittest.TestCase):
    def test_extracts_meta_and_body_not_chrome(self):
        text = enrich.extract_excerpt(ARTICLE_HTML)
        self.assertTrue(text.startswith("DBS and Kinexys launch 24/7 USD tokenised deposit transfers."))
        self.assertIn("around the clock, including weekends", text)
        self.assertNotIn("Subscribe", text)
        self.assertNotIn("Copyright", text)
        self.assertNotIn("Short.", text)

    def test_limit(self):
        self.assertLessEqual(len(enrich.extract_excerpt(ARTICLE_HTML, limit=50)), 50)


class TestGatherEvidence(unittest.TestCase):
    def test_resolves_links_and_collects_excerpts(self):
        gnews = "https://news.google.com/rss/articles/ABC?oc=5"
        by_id = {"a1": {"title": "BoE DSS update", "url": "https://www.bankofengland.co.uk/news/dss", "source": "BoE"},
                 "a2": {"title": "Fnality launch", "url": gnews, "source": "FT"}}
        payload = sample_payload()
        payload["pillars"][1]["developments"][0]["url"] = gnews
        payload["pillars"][1]["developments"] = payload["pillars"][1]["developments"][:1]
        payload["new_high_signal_targets"] = [{"name": "Fnality", "article_id": "a2", "url": gnews, "rationale": "r"}]
        analysis = StrategicAnalysis.model_validate(payload)

        with patch.object(enrich, "resolve_google_news", return_value={gnews: "https://ft.com/fnality"}), \
                patch.object(enrich, "fetch_excerpt", side_effect=lambda u: f"excerpt for {u}"):
            evidence, trusted = enrich.gather_evidence(analysis, by_id)

        self.assertEqual(analysis.pillars[1].developments[0].url, "https://ft.com/fnality")
        self.assertEqual(analysis.new_high_signal_targets[0].url, "https://ft.com/fnality")
        self.assertEqual(trusted, ["https://ft.com/fnality"])
        self.assertEqual(evidence["a2"], "excerpt for https://ft.com/fnality")
        self.assertEqual(evidence["a1"], "excerpt for https://www.bankofengland.co.uk/news/dss")

        block = enrich.evidence_for_prompt(analysis, by_id, evidence)
        self.assertEqual(block["a2"]["headline"], "Fnality launch")
        self.assertEqual(block["a2"]["excerpt"], "excerpt for https://ft.com/fnality")

    def test_unresolved_google_link_gets_no_fetch(self):
        with patch.object(enrich, "fetch_excerpt") as fetch:
            self.assertEqual(enrich._safe_excerpt("https://news.google.com/rss/articles/X"), "")
        fetch.assert_not_called()


def response(payload):
    return SimpleNamespace(parsed=None, text=json.dumps(payload), candidates=[])


class TestEditorRevision(unittest.TestCase):
    def test_banned_phrases_trigger_one_revision(self):
        original = StrategicAnalysis.model_validate(sample_payload())
        fluffy = sample_payload()
        fluffy["macro_view"][0]["detail"] = "This signals a crucial shift."
        clean = sample_payload()
        clean["macro_view"][0]["detail"] = "DBS moved USD deposit tokens 24/7."
        client = FakeClient([response(fluffy), response(clean)])
        result = run_pipeline.run_editor(client, "m1", original, {})
        self.assertEqual(result.macro_view[0].detail, "DBS moved USD deposit tokens 24/7.")
        self.assertEqual(len(client.calls), 2)

    def test_gives_up_after_max_revisions_with_last_draft(self):
        original = StrategicAnalysis.model_validate(sample_payload())
        fluffy = sample_payload()
        fluffy["macro_view"][0]["detail"] = "Robust and seamless."
        client = FakeClient([response(fluffy), response(fluffy)])
        result = run_pipeline.run_editor(client, "m1", original, {}, max_revisions=1)
        self.assertEqual(result.macro_view[0].detail, "Robust and seamless.")
        self.assertEqual(len(client.calls), 2)

    def test_prompt_contains_evidence_and_banned_list(self):
        original = StrategicAnalysis.model_validate(sample_payload())
        prompt = run_pipeline._editor_prompt(original, {"a1": {"headline": "h", "excerpt": "e"}})
        self.assertIn('"a1":{"headline":"h","excerpt":"e"}', prompt)
        self.assertIn("pave the way", prompt)


class TestStale(unittest.TestCase):
    def test_editor_stale_flag_merged_and_dropped_from_render(self):
        from render import render_briefing
        original = StrategicAnalysis.model_validate(sample_payload())
        edited_payload = sample_payload()
        edited_payload["pillars"][0]["developments"][0]["stale"] = True
        merged = run_pipeline.merge_editor_prose(original, StrategicAnalysis.model_validate(edited_payload))
        self.assertTrue(merged.pillars[0].developments[0].stale)
        md = render_briefing(merged)
        self.assertNotIn("BoE DSS update", md)
        self.assertNotIn("### Sovereign Infrastructure", md)  # pillar emptied -> omitted
        self.assertIn("Fnality", md)


class TestHedging(unittest.TestCase):
    def test_word_boundaries(self):
        self.assertEqual(find_hedging("A robust framework"), ["robust"])
        self.assertEqual(find_hedging("Robustness testing"), [])
        self.assertIn("this signals", find_hedging("This signals a shift"))


if __name__ == "__main__":
    unittest.main()

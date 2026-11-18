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


class TestHeadlines(unittest.TestCase):
    BODY = ("DBS and JPMorgan moved tokenised deposits. The Bank of England, MAS and Bank of Thailand "
            "completed trials with Mizuho on Canton Network. Central banks set rules for collateral.")

    def test_sentence_case_keeps_proper_nouns(self):
        from render import to_sentence_case
        self.assertEqual(
            to_sentence_case("The Bank of England Tests Tokenised Collateral With Canton Network Partners.", self.BODY),
            "The Bank of England tests tokenised collateral with Canton Network partners.")
        self.assertEqual(to_sentence_case("BIS FX Trials Prove Cross-Border Settlement.", self.BODY),
                         "BIS FX trials prove cross-border settlement.")

    def test_already_sentence_case_untouched(self):
        from render import to_sentence_case
        h = "DBS and JPMorgan link Tokenised deposits across Asia."
        self.assertEqual(to_sentence_case(h, self.BODY), h)

    def test_long_headline_triggers_revision(self):
        original = StrategicAnalysis.model_validate(sample_payload())
        long_payload = sample_payload()
        long_payload["macro_view"][0]["headline"] = " ".join(["word"] * 15)
        long_payload["macro_view"][0]["detail"] = "Banks moved dollars at weekends."
        short_payload = sample_payload()
        short_payload["macro_view"][0]["detail"] = "Banks moved dollars at weekends."
        client = FakeClient([response(long_payload), response(short_payload)])
        result = run_pipeline.run_editor(client, "m1", original, {})
        self.assertEqual(result.macro_view[0].headline, "Deposit tokens go live")
        self.assertEqual(len(client.calls), 2)

    def test_insider_jargon_flagged(self):
        self.assertIn("nostro", find_hedging("Banks cut Nostro pre-funding"))
        self.assertIn("earmarks", find_hedging("using locked reserve earmarks"))


class TestHedging(unittest.TestCase):
    def test_word_boundaries(self):
        self.assertEqual(find_hedging("A robust framework"), ["robust"])
        self.assertEqual(find_hedging("Robustness testing"), [])
        self.assertIn("this signals", find_hedging("This signals a shift"))


if __name__ == "__main__":
    unittest.main()


class TestFreshnessAndUKAngle(unittest.TestCase):
    TODAY = __import__("datetime").date(2026, 11, 18)

    def payload(self):
        p = sample_payload()
        devs = p["pillars"][1]["developments"]
        devs[0]["event_date"] = "2026-10-28"        # Fnality: 21 days old -> dropped
        devs.append({"article_id": "fresh", "title": "HKEX wCBDC margin", "source": "Ledger Insights",
                     "url": "https://li/hkex", "event_date": "2026-11-17",
                     "details": "HKEX will accept wCBDC margin from 14 December; HSBC and Standard Chartered are settlement banks."})
        p["macro_view"] = [{"headline": "Fnality goes live", "detail": "It settled sterling.", "article_id": "a2"},
                           {"headline": "HKEX accepts wCBDC", "detail": "From 14 December.", "article_id": "fresh"}]
        return p

    def test_old_events_dropped_and_flagged(self):
        import datetime
        from unittest.mock import patch
        import render
        analysis = StrategicAnalysis.model_validate(self.payload())
        with patch.object(render.datetime, "date", wraps=datetime.date) as d:
            d.today.return_value = self.TODAY
            ids = [dev.article_id for _, dev in render.selected_developments(analysis)]
            flagged = render.old_one_minute(analysis, today=self.TODAY)
        self.assertNotIn("a2", ids)
        self.assertIn("fresh", ids)
        self.assertEqual(len(flagged), 1)
        self.assertIn("2026-10-28", flagged[0])

    def test_undated_events_are_kept(self):
        from render import is_old_event
        from schema import Development
        self.assertFalse(is_old_event(Development(article_id="x", details="d"), 7))

    def test_editor_can_swap_one_minute_story(self):
        original = StrategicAnalysis.model_validate(self.payload())
        edited_payload = self.payload()
        edited_payload["macro_view"][0] = {"headline": "BoE DSS expands", "detail": "Sandbox grew.", "article_id": "a1"}
        merged = run_pipeline.merge_editor_prose(original, StrategicAnalysis.model_validate(edited_payload))
        self.assertEqual(merged.macro_view[0].article_id, "a1")
        bogus = self.payload()
        bogus["macro_view"][0]["article_id"] = "made-up"
        merged = run_pipeline.merge_editor_prose(original, StrategicAnalysis.model_validate(bogus))
        self.assertEqual(merged.macro_view[0].article_id, "a2")  # unknown id rejected

    def test_uk_angle_does_not_repeat_uk_items(self):
        from render import render_briefing
        p = sample_payload()
        p["pillars"][1]["developments"].append({
            "article_id": "mon", "title": "Monument launches tokenised deposits", "source": "Finextra",
            "url": "https://f/m", "uk": True,
            "details": "Monument Bank launched the UK's first interest-bearing tokenised deposits on Midnight."})
        p["uk_implications"] = [
            "Monument Bank launched the UK's first interest-bearing tokenised deposits on the Midnight Network.",
            "HSBC and Standard Chartered are settlement banks for the HKEX wholesale CBDC margin service."]
        md = render_briefing(StrategicAnalysis.model_validate(p))
        angle = md.split("## The UK angle")[1].split("## What happened")[0]
        self.assertNotIn("Monument", angle)
        self.assertIn("HSBC and Standard Chartered", angle)

    def test_new_technology_requires_ledger_or_tokens(self):
        from render import render_briefing
        p = sample_payload()
        p["pillars"].append({"name": "Frontier & Emerging Innovations", "developments": [
            {"article_id": "ai1", "title": "HKMA explores AI for crime detection", "url": "https://x/ai",
             "details": "The HKMA is testing AI agents to flag suspicious transactions."},
            {"article_id": "ai2", "title": "AI agents settle FX on Kinexys", "url": "https://x/k",
             "details": "Hyundai Card and JPMorgan ran AI agents that settled FX on the Kinexys blockchain."}]})
        md = render_briefing(StrategicAnalysis.model_validate(p))
        self.assertNotIn("crime detection", md)
        self.assertIn("Kinexys", md)


class TestPdfEvidence(unittest.TestCase):
    def test_pdf_excerpt(self):
        from pdf_fixture import make_pdf
        self.assertEqual(enrich.extract_pdf_excerpt(make_pdf("IOSCO 2026 Monitoring Report")),
                         "IOSCO 2026 Monitoring Report")
        self.assertEqual(enrich.extract_pdf_excerpt(b"not a pdf"), "")

    def test_fetch_excerpt_routes_pdf(self):
        from pdf_fixture import make_pdf
        with patch.object(enrich, "_get_document", return_value=("pdf", make_pdf("BIS paper text"))):
            self.assertEqual(enrich.fetch_excerpt("https://bis.org/x.pdf"), "BIS paper text")
        with patch.object(enrich, "_get_document", return_value=(None, None)):
            self.assertEqual(enrich.fetch_excerpt("https://x"), "")

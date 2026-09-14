import unittest
import os
import sys

# Add pipeline directory to sys.path so we can import modules
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

from publish import get_env_var, convert_markdown_to_newsletter_html

class TestPipelineUtilities(unittest.TestCase):

    def test_environment_variable_lookup(self):
        # Set a temporary environment variable
        test_var_name = "TEST_PIPELINE_VAR"
        test_var_val = "pipeline_test_value_123"
        os.environ[test_var_name] = test_var_val
        
        # Verify get_env_var successfully retrieves it
        self.assertEqual(get_env_var(test_var_name), test_var_val)
        
        # Clean up
        del os.environ[test_var_name]

    def test_newsletter_html_generation_four_sections(self):
        # Sample markdown brief with 4-section layout using H3 subsections
        sample_markdown = """## 1. MACRO VIEW
* **Cross-border intraday liquidity now bypasses legacy suspensions.** DBS and Citi completed live payments.

## 2. CORE PILLAR DEVELOPMENTS

### Banking Infrastructure & Commercial Rails
*Commercial banks and pure-play stablecoin issuers are integrating payment rails.*

*   [Circle Tazapay](https://example.com/circle): Circle completed acquisition.

## 3. STRUCTURAL & OPERATIONAL PAIN POINTS
* **Interoperability Silos:** Ledger isolation issues.

## 4. NEW HIGH-SIGNAL TARGETS FOR TRACKING
* [**Tazapay**](https://example.com/tazapay): B2B cross-border payments.
"""
        subject = "Digital Asset Digest Test 4-Section"
        date_str = "2026-09-14"
        
        html_output = convert_markdown_to_newsletter_html(subject, date_str, sample_markdown)
        
        # Verify HTML structure has successfully wrapped Macro View in synthesis-card
        self.assertIn("<!DOCTYPE html>", html_output)
        self.assertIn("synthesis-card", html_output)
        self.assertIn("Cross-border intraday liquidity", html_output)
        self.assertIn("CORE PILLAR DEVELOPMENTS", html_output)
        self.assertIn("<h3>Banking Infrastructure &amp; Commercial Rails</h3>", html_output)
        self.assertIn("STRUCTURAL &amp; OPERATIONAL PAIN POINTS", html_output)
        self.assertIn("NEW HIGH-SIGNAL TARGETS FOR TRACKING", html_output)

    def test_newsletter_html_generation_five_sections(self):
        # Sample markdown brief with 5-section layout (backward compatibility)
        sample_markdown = """## 1. STRATEGIC TAKEAWAYS
* **What Happened This Week:** Breakthrough in wholesale tokenised deposit settlement.
* **Why It Matters (Banks, Corporate Treasury & FMIs):** Eliminates weekend settlement risk.

## 2. MACRO VIEW
* **Cross-border intraday liquidity now bypasses legacy suspensions.** DBS and Citi completed live payments.

## 3. CORE INSTITUTIONAL PILLARS
* **Bank-Led Digital Money & Settlement Rails:** Update on Swift Digital Ledger.

## 4. STRUCTURAL, BALANCE SHEET & OPERATIONAL FRICTIONS
* **Interoperability Silos:** Ledger isolation issues.

## 5. INSTITUTIONAL HORIZON RADAR & WATCHLIST
* **Fnality:** Continuing interbank wholesale settlement trials.
"""
        subject = "Digital Asset Digest Test 5-Section"
        date_str = "2026-09-14"
        
        html_output = convert_markdown_to_newsletter_html(subject, date_str, sample_markdown)
        
        # Verify HTML structure has successfully wrapped both Takeaways and Macro View cards
        self.assertIn("<!DOCTYPE html>", html_output)
        self.assertIn("takeaways-card", html_output)
        self.assertIn("synthesis-card", html_output)
        self.assertIn("What Happened This Week:", html_output)
        self.assertIn("Cross-border intraday liquidity", html_output)
        self.assertIn("CORE INSTITUTIONAL PILLARS", html_output)
        self.assertIn("INSTITUTIONAL HORIZON RADAR &amp; WATCHLIST", html_output)

    def test_feed_parsing_and_keyword_filter(self):
        from ingestion import parse_feed, PUBLIC_SECTOR_KEYWORDS
        from unittest.mock import patch, MagicMock

        # Mock Atom feed XML
        atom_xml = """<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>HM Treasury</title>
          <entry>
            <title>Speech on UK Digital Securities Sandbox and Tokenisation</title>
            <link href="https://gov.uk/dss-speech" />
            <summary>Discussion on DLT market infrastructure and settlement.</summary>
          </entry>
          <entry>
            <title>Annual Agriculture Subsidy Report</title>
            <link href="https://gov.uk/farming-report" />
            <summary>Summary of farming support schemes.</summary>
          </entry>
        </feed>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = atom_xml.encode("utf-8")

        with patch("requests.get", return_value=mock_response):
            # Test with keyword filter
            filtered_articles = parse_feed("Test HMT", "https://gov.uk/feed.atom", keyword_filter=PUBLIC_SECTOR_KEYWORDS)
            
            # The digital securities entry should pass, agriculture entry should be filtered out
            self.assertEqual(len(filtered_articles), 1)
            self.assertIn("Digital Securities Sandbox", filtered_articles[0]["title"])
            self.assertEqual(filtered_articles[0]["url"], "https://gov.uk/dss-speech")

    def test_link_validation_and_normalization(self):
        from run_pipeline import validate_and_normalize_links
        
        # Test absolute links (should be untouched)
        content_abs = "Check [Visa](https://www.google.com/search?q=Visa) or [BIS](https://www.bis.org/press/p260520.htm)."
        self.assertEqual(validate_and_normalize_links(content_abs), content_abs)
        
        # Test page fragment links (should be untouched)
        content_fragment = "See [Section 2](#section-2)."
        self.assertEqual(validate_and_normalize_links(content_fragment), content_fragment)
        
        # Test relative/broken links (should be normalized to Google Search fallback)
        content_rel = "Read [Project Pontes](atlantic_council_cbdc_tracker_2026-22) and [Drex](atlantic_council_cbdc_tracker_2026-22)."
        expected_normalized = "Read [Project Pontes](https://www.google.com/search?q=Project+Pontes) and [Drex](https://www.google.com/search?q=Drex)."
        self.assertEqual(validate_and_normalize_links(content_rel), expected_normalized)

    def test_system_state_updates(self):
        import run_pipeline
        import tempfile
        import shutil
        import json
        
        # Create a temp directory to act as workspace root
        temp_dir = tempfile.mkdtemp()
        original_workspace_root = run_pipeline.WORKSPACE_ROOT
        run_pipeline.WORKSPACE_ROOT = temp_dir
        
        try:
            # Set up sample raw feed
            sample_feed = [
                {"title": "Test 1", "url": "https://example.com/1"},
                {"title": "Test 2", "url": "https://example.com/2"}
            ]
            
            # Run the update
            run_pipeline.update_system_state(sample_feed)
            
            # Check file was created
            state_file_path = os.path.join(temp_dir, "system_state.json")
            self.assertTrue(os.path.exists(state_file_path))
            
            with open(state_file_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                
            self.assertIn("processed_urls", state_data)
            self.assertIn("https://example.com/1", state_data["processed_urls"])
            self.assertIn("https://example.com/2", state_data["processed_urls"])
            
            # Run it again with a new url to test merging/updating
            new_feed = [
                {"title": "Test 3", "url": "https://example.com/3"}
            ]
            run_pipeline.update_system_state(new_feed)
            
            with open(state_file_path, "r", encoding="utf-8") as f:
                updated_state_data = json.load(f)
                
            self.assertIn("https://example.com/1", updated_state_data["processed_urls"])
            self.assertIn("https://example.com/3", updated_state_data["processed_urls"])
            
        finally:
            run_pipeline.WORKSPACE_ROOT = original_workspace_root
            shutil.rmtree(temp_dir)

if __name__ == '__main__':
    unittest.main()

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

    def test_newsletter_html_generation(self):
        # Sample markdown brief content
        sample_markdown = """## 1. MACRO VIEW
* **Test point.** This is a test.

## 2. CORE PILLAR DEVELOPMENTS
* **Banking Infrastructure & Commercial Rails:** Update.
"""
        subject = "Digital Asset Digest Test"
        date_str = "2026-06-11"
        
        # Run conversion helper
        html_output = convert_markdown_to_newsletter_html(subject, date_str, sample_markdown)
        
        # Verify HTML structure has successfully wrapped the Macro View card
        self.assertIn("<!DOCTYPE html>", html_output)
        self.assertIn("synthesis-card", html_output)
        self.assertIn("CORE PILLAR DEVELOPMENTS", html_output)
        self.assertIn("Test point.", html_output)

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

if __name__ == '__main__':
    unittest.main()

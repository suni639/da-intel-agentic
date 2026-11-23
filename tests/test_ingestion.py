import datetime
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

import ingestion  # noqa: E402
from feeds import Feed, FEEDS, INSTITUTIONAL_KEYWORDS, active_feeds  # noqa: E402

NOW = datetime.datetime(2026, 11, 16, tzinfo=datetime.timezone.utc)


def rss(items):
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate>"
        f"<description>{desc}</description>{extra}</item>"
        for t, u, d, desc, extra in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


class TestKeywords(unittest.TestCase):
    def test_word_boundaries(self):
        self.assertTrue(ingestion.matches_keywords("SEC approves rule", INSTITUTIONAL_KEYWORDS))
        self.assertFalse(ingestion.matches_keywords("Bitcoin rallies for a second day", ["sec"]))
        self.assertFalse(ingestion.matches_keywords("Memecoin surges 40%", INSTITUTIONAL_KEYWORDS))
        self.assertTrue(ingestion.matches_keywords("Move to T+1 settlement", ["t+1"]))


class TestParseEntries(unittest.TestCase):
    def setUp(self):
        self._state = ingestion.state
        ingestion.state = {"processed_urls": {"https://x.com/seen": "2026-11-10T00:00:00+00:00"}}

    def tearDown(self):
        ingestion.state = self._state

    def test_lookback_filter_and_state(self):
        content = rss([
            ("Bank tokenised deposit pilot", "https://x.com/new", "Sun, 15 Nov 2026 09:00:00 GMT", "d", ""),
            ("Old stablecoin story", "https://x.com/old", "Mon, 01 Jun 2026 09:00:00 GMT", "d", ""),
            ("Seen stablecoin story", "https://x.com/seen", "Sun, 15 Nov 2026 09:00:00 GMT", "d", ""),
            ("Memecoin pumps", "https://x.com/meme", "Sun, 15 Nov 2026 09:00:00 GMT", "price up", ""),
        ])
        out = ingestion.parse_entries("Test", "https://x.com/feed", content,
                                      keyword_filter=INSTITUTIONAL_KEYWORDS, now=NOW, lookback_days=8)
        self.assertEqual([a["url"] for a in out], ["https://x.com/new"])
        self.assertTrue(out[0]["published"].startswith("2026-11-15"))

    def test_google_news_publisher_extracted(self):
        content = rss([("Fnality goes live - Financial Times", "https://news.google.com/rss/articles/abc",
                        "Sun, 15 Nov 2026 09:00:00 GMT", "", '<source url="https://ft.com">Financial Times</source>')])
        out = ingestion.parse_entries("News: x", "https://news.google.com/rss", content, now=NOW)
        self.assertEqual(out[0]["title"], "Fnality goes live")
        self.assertEqual(out[0]["source"], "Financial Times")

    def test_url_publisher_normalised(self):
        content = rss([("Group launched - https://genfinity.io/", "https://news.google.com/rss/articles/x",
                        "Sun, 15 Nov 2026 09:00:00 GMT", "", '<source url="https://genfinity.io">https://www.genfinity.io/</source>')])
        out = ingestion.parse_entries("News: x", "https://news.google.com/rss", content, now=NOW)
        self.assertEqual(out[0]["source"], "genfinity.io")

    def test_headline_echo_summary_dropped(self):
        content = rss([("Fnality goes live - FT", "https://news.google.com/rss/articles/abc",
                        "Sun, 15 Nov 2026 09:00:00 GMT", "&lt;a href='x'&gt;Fnality goes live&lt;/a&gt; FT",
                        '<source url="https://ft.com">FT</source>')])
        out = ingestion.parse_entries("News: x", "https://news.google.com/rss", content, now=NOW)
        self.assertEqual(out[0]["content"], "")


class TestCollect(unittest.TestCase):
    def test_dedup_across_feeds_and_cap(self):
        feeds = [Feed("A", "https://a/feed"), Feed("B", "https://b/feed")]
        a_items = [{"title": f"Story {i}", "url": f"https://a/{i}", "published": f"2026-11-1{i}", "source": "A"}
                   for i in range(4)]
        b_items = [{"title": "Story 1!", "url": "https://b/dup", "published": None, "source": "B"},
                   {"title": "Unique", "url": "https://b/u", "published": None, "source": "B"}]
        with patch.object(ingestion, "parse_feed", side_effect=[a_items, b_items]), \
                patch.object(ingestion, "MAX_ITEMS_PER_FEED", 3):
            out = ingestion.collect(feeds)
        urls = [a["url"] for a in out]
        self.assertEqual(urls, ["https://a/3", "https://a/2", "https://a/1", "https://b/u"])


class TestFetch(unittest.TestCase):
    def test_falls_back_to_browser_agent(self):
        refused = MagicMock(status_code=403, content=b"")
        ok = MagicMock(status_code=200, content=b"<rss/>")
        with patch("requests.get", side_effect=[refused, ok]) as get:
            status, _, agent = ingestion.fetch("https://x/feed")
        self.assertEqual((status, agent), (200, "browser"))
        self.assertIn("DA-Intel", get.call_args_list[0].kwargs["headers"]["User-Agent"])


    def test_retries_transient_errors(self):
        busy = MagicMock(status_code=503, content=b"")
        ok = MagicMock(status_code=200, content=b"<rss/>")
        sleep = MagicMock()
        with patch("requests.get", side_effect=[busy, busy, ok]) as get:
            status, _, agent = ingestion.fetch("https://x/feed", retry_delays=(5, 9), sleep=sleep)
        self.assertEqual((status, agent), (200, "bot"))
        self.assertEqual(get.call_count, 3)
        sleep.assert_called_once_with(5)

    def test_gives_up_after_retries(self):
        busy = MagicMock(status_code=503, content=b"")
        sleep = MagicMock()
        with patch("requests.get", return_value=busy) as get:
            status, content, agent = ingestion.fetch("https://x/feed", retry_delays=(5,), sleep=sleep)
        self.assertEqual((status, content, agent), (503, b"", None))
        self.assertEqual(get.call_count, 4)

    def test_no_retry_on_permanent_error(self):
        gone = MagicMock(status_code=404, content=b"")
        sleep = MagicMock()
        with patch("requests.get", return_value=gone) as get:
            status, _, _ = ingestion.fetch("https://x/feed", sleep=sleep)
        self.assertEqual(status, 404)
        self.assertEqual(get.call_count, 2)
        sleep.assert_not_called()

class TestFeedConfig(unittest.TestCase):
    def test_config_is_valid(self):
        names = [f.name for f in FEEDS]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(f.filter in ingestion.FILTERS for f in FEEDS))
        self.assertTrue(active_feeds())

    def test_google_news_queries_fit_word_limit(self):
        # Google ignores words past the 32nd, which would drop the "when:7d" limit.
        from urllib.parse import parse_qs, urlparse
        for feed in FEEDS:
            if "news.google.com" in feed.url:
                q = parse_qs(urlparse(feed.url).query)["q"][0]
                self.assertLessEqual(len(q.split()), 32, feed.name)


if __name__ == "__main__":
    unittest.main()

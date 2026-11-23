import calendar
import datetime
import json
import os
import re
import sys
import time
from functools import lru_cache
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from feeds import DIGITAL_ASSET_KEYWORDS, INSTITUTIONAL_KEYWORDS, PUBLIC_SECTOR_KEYWORDS, active_feeds

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(WORKSPACE_DIR, "system_state.json")

# Only consider items published within this window (undated items are kept).
LOOKBACK_DAYS = int(os.environ.get("INGEST_LOOKBACK_DAYS", "8"))
# Bound the prompt size: per-feed cap and per-article text length.
MAX_ITEMS_PER_FEED = int(os.environ.get("INGEST_MAX_ITEMS_PER_FEED", "15"))
CONTENT_CHARS = 800

# Load state history if present to ensure proper deduplication
if os.path.exists(STATE_PATH):
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        state = json.load(f)
else:
    state = {"processed_urls": {}}

# Identify honestly first; some publishers block non-browser agents, so fall
# back to a browser string only when the polite request is refused.
BOT_USER_AGENT = "Mozilla/5.0 (compatible; DA-Intel-RSS-Reader/1.0)"
BROWSER_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": BROWSER_USER_AGENT}  # kept for backwards compatibility


def log(msg):
    print(f"[ingestion] {msg}", file=sys.stderr)


# Statuses that usually clear within seconds (rate limits, overloaded servers).
# Google News answers 503 when it briefly throttles a runner's IP address.
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS = (10, 30)  # seconds to wait before each retry


def _fetch_once(url, timeout):
    last_status, last_exc = None, None
    for label, agent in (("bot", BOT_USER_AGENT), ("browser", BROWSER_USER_AGENT)):
        try:
            r = requests.get(url, headers={"User-Agent": agent,
                                           "Accept": "application/rss+xml, application/atom+xml, "
                                                     "application/xml;q=0.9, */*;q=0.8"},
                             timeout=timeout)
        except Exception as e:  # network error: try the other agent once
            last_exc = e
            continue
        last_status = r.status_code
        if r.status_code == 200 and r.content.strip():
            return r.status_code, r.content, label, None
    return last_status, b"", None, last_exc


def fetch(url, timeout=15, retry_delays=RETRY_DELAYS, sleep=time.sleep):
    """GET a feed. Returns (status_code, content_bytes, agent_label).

    Tries a polite bot agent, then a browser agent. If both get a transient
    error (429/5xx), waits and tries again, up to len(retry_delays) times.
    """
    for attempt in range(len(retry_delays) + 1):
        status, content, label, exc = _fetch_once(url, timeout)
        if status == 200 and label:
            return status, content, label
        if status not in TRANSIENT_STATUS or attempt == len(retry_delays):
            break
        log(f"HTTP {status} from {urlparse(url).netloc}; retrying in {retry_delays[attempt]}s")
        sleep(retry_delays[attempt])
    if status is None and exc is not None:
        raise exc
    return status, b"", None


@lru_cache(maxsize=None)
def _keyword_regex(keywords):
    parts = []
    for kw in keywords:
        escaped = re.escape(kw.lower())
        start = r"\b" if re.match(r"\w", kw) else ""
        end = r"\b" if re.search(r"\w$", kw) else ""
        parts.append(f"{start}{escaped}{end}")
    return re.compile("|".join(parts))


def matches_keywords(text, keywords):
    return bool(_keyword_regex(tuple(keywords)).search(text.lower()))


def _entry_datetime(entry):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime.datetime.fromtimestamp(calendar.timegm(value), tz=datetime.timezone.utc)
    return None


def _clean_text(html_text):
    return " ".join(BeautifulSoup(html_text or "", "html.parser").get_text(" ", strip=True).split())


def parse_entries(source_name, feed_url, content, keyword_filter=None, now=None,
                  lookback_days=LOOKBACK_DAYS):
    """Parse feed bytes into article dicts, applying filter, lookback and dedup state."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=lookback_days)
    parsed = feedparser.parse(content)
    processed = state.get("processed_urls", {})

    articles, stale, filtered = [], 0, 0
    for entry in parsed.entries:
        link = (entry.get("link") or "").strip()
        if not link:
            continue
        link = urljoin(feed_url, link)

        title = _clean_text(entry.get("title", ""))
        publisher = source_name
        src = entry.get("source")
        if isinstance(src, dict) and src.get("title"):
            # Google News: "Headline - Publisher"; keep the real publisher name.
            raw_publisher = src["title"]
            suffix = f" - {raw_publisher}"
            if title.endswith(suffix):
                title = title[: -len(suffix)]
            publisher = raw_publisher
            if publisher.startswith(("http://", "https://")):
                host = urlparse(publisher).hostname or publisher
                publisher = host[4:] if host.startswith("www.") else host

        summary = entry.get("summary") or ""
        if not summary and entry.get("content"):
            summary = entry["content"][0].get("value", "")
        text = _clean_text(summary)[:CONTENT_CHARS]
        # Search-aggregator summaries just repeat the headline; drop them to save tokens.
        if text and _title_key(text).startswith(_title_key(title)):
            text = ""

        published = _entry_datetime(entry)
        if published and published < cutoff:
            stale += 1
            continue

        if keyword_filter and not matches_keywords(f"{title} {text}", keyword_filter):
            filtered += 1
            continue

        if link in processed:
            continue

        articles.append({
            "title": title,
            "url": link,
            "source": publisher,
            "published": published.isoformat() if published else None,
            "content": text,
        })

    log(f"{source_name}: {len(parsed.entries)} items in feed, {stale} older than {lookback_days}d, "
        f"{filtered} filtered out, {len(articles)} new")
    if not parsed.entries:
        log(f"WARNING: {source_name} returned no items - check the feed URL or whether "
            f"the site is blocking the client")
    return articles


def parse_feed(source_name, feed_url, keyword_filter=None):
    try:
        status, content, agent = fetch(feed_url)
    except Exception as e:
        log(f"Error fetching feed {source_name}: {e}")
        return []
    if status != 200:
        log(f"{source_name}: HTTP {status} - feed skipped")
        return []
    if agent == "browser":
        log(f"{source_name}: bot user agent refused; fetched with browser user agent")
    try:
        return parse_entries(source_name, feed_url, content, keyword_filter)
    except Exception as e:
        log(f"Error parsing feed {source_name}: {e}")
        return []


FILTERS = {
    None: None,
    "public_sector": PUBLIC_SECTOR_KEYWORDS,
    "institutional": INSTITUTIONAL_KEYWORDS,
    "digital_asset": DIGITAL_ASSET_KEYWORDS,
}


def _title_key(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def collect(feeds=None):
    """Fetch all active feeds and de-duplicate across them (by URL and headline)."""
    harvested, seen_urls, seen_titles = [], set(), set()
    for feed in feeds or active_feeds():
        items = parse_feed(feed.name, feed.url, keyword_filter=FILTERS[feed.filter])
        # Newest first, then cap so one noisy feed cannot dominate the prompt.
        items.sort(key=lambda a: a.get("published") or "", reverse=True)
        kept = 0
        for item in items:
            key = _title_key(item["title"])
            if item["url"] in seen_urls or (key and key in seen_titles):
                continue
            if kept >= MAX_ITEMS_PER_FEED:
                break
            seen_urls.add(item["url"])
            if key:
                seen_titles.add(key)
            harvested.append(item)
            kept += 1
    log(f"Total unique new articles: {len(harvested)}")
    return harvested


def run_ingestion():
    # Print clean JSON array to standard out for the orchestrator to capture
    print(json.dumps(collect(), indent=2))


if __name__ == "__main__":
    run_ingestion()

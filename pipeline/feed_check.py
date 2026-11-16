"""Probe every configured feed (active and candidate) and report its health.

Usage:
    python pipeline/feed_check.py            # report only
    python pipeline/feed_check.py --strict   # exit 1 if an active feed is broken
    python pipeline/feed_check.py --discover # also scan DISCOVERY_PAGES for feed links

In GitHub Actions the report is also written to the job summary.
"""
import datetime
import os
import sys
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from feeds import DISCOVERY_PAGES, FEEDS
from ingestion import FILTERS, _entry_datetime, fetch, matches_keywords


def probe(feed, now):
    row = {"name": feed.name, "status": "-", "agent": "-", "items": 0, "recent": 0,
           "relevant": 0, "newest": "-", "ok": False,
           "role": "candidate" if feed.candidate else "active"}
    try:
        status, content, agent = fetch(feed.url)
    except Exception as e:
        row["status"] = f"error: {type(e).__name__}"
        return row
    row["status"], row["agent"] = status, agent or "-"
    if status != 200:
        return row
    parsed = feedparser.parse(content)
    keywords = FILTERS[feed.filter]
    cutoff = now - datetime.timedelta(days=7)
    newest = None
    for entry in parsed.entries:
        published = _entry_datetime(entry)
        if published and (newest is None or published > newest):
            newest = published
        if published is None or published >= cutoff:
            row["recent"] += 1
            text = f"{entry.get('title', '')} {entry.get('summary', '')}"
            if keywords is None or matches_keywords(text, keywords):
                row["relevant"] += 1
    row["items"] = len(parsed.entries)
    row["newest"] = newest.strftime("%Y-%m-%d") if newest else "undated"
    row["ok"] = row["items"] > 1
    return row


def discover(page):
    try:
        status, content, _ = fetch(page)
    except Exception as e:
        return [f"error: {type(e).__name__}"]
    if status != 200:
        return [f"HTTP {status}"]
    soup = BeautifulSoup(content, "html.parser")
    found = []
    for tag in soup.find_all(["link", "a"]):
        href = tag.get("href") or ""
        kind = (tag.get("type") or "").lower()
        if "rss" in kind or "atom" in kind or any(
                s in href.lower() for s in (".rss", "/rss", "/feed", "atom", ".xml")):
            url = urljoin(page, href)
            if url not in found:
                found.append(url)
    return found[:40] or ["no feed links found"]


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = [probe(feed, now) for feed in FEEDS]

    lines = ["## Feed health", "",
             "| Feed | Role | HTTP | Agent | Items | Last 7d | Relevant (7d) | Newest | OK |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['role']} | {r['status']} | {r['agent']} | {r['items']} | "
                     f"{r['recent']} | {r['relevant']} | {r['newest']} | {'yes' if r['ok'] else 'NO'} |")

    if "--discover" in sys.argv:
        lines += ["", "## Discovered feed links", ""]
        for page in DISCOVERY_PAGES:
            lines.append(f"**{page}**")
            lines += [f"- {u}" for u in discover(page)]
            lines.append("")

    report = "\n".join(lines)
    print(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(report + "\n")

    broken = [r["name"] for r in rows if r["role"] == "active" and not r["ok"]]
    if broken:
        print(f"\nBroken active feeds: {', '.join(broken)}", file=sys.stderr)
        if "--strict" in sys.argv:
            sys.exit(1)


if __name__ == "__main__":
    main()

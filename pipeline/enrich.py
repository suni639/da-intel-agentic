"""Evidence gathering for the developments the strategist selected.

For each selected article we:
  1. resolve Google News redirect links to the publisher's own URL, so the
     brief links straight to the source; and
  2. fetch a short excerpt (meta description + opening paragraphs), which the
     editor uses to keep every stated fact grounded in the article.

Everything here is best-effort: a failure leaves the original link in place
and the editor falls back to the headline alone.
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ingestion import BOT_USER_AGENT, BROWSER_USER_AGENT

EXCERPT_CHARS = 1500
MIN_PARAGRAPH_CHARS = 60
FETCH_TIMEOUT = 12
MAX_WORKERS = 8


def log(msg):
    print(f"[enrich] {msg}", file=sys.stderr)


def is_google_news(url: str) -> bool:
    return urlparse(url or "").hostname == "news.google.com"


def resolve_google_news(urls: List[str]) -> Dict[str, str]:
    """Map Google News redirect URLs to publisher URLs (unresolvable ones are omitted)."""
    targets = [u for u in dict.fromkeys(urls) if is_google_news(u)]
    if not targets:
        return {}
    try:
        from googlenewsdecoder import GoogleDecoder
    except ImportError:
        log("googlenewsdecoder not installed; keeping Google News links")
        return {}
    resolved = {}
    try:
        with GoogleDecoder(timeout=FETCH_TIMEOUT) as decoder:
            for source, result in zip(targets, decoder.decode_google_news_urls(targets)):
                decoded = result.get("decoded_url") if result.get("success") else None
                if decoded and decoded.startswith(("http://", "https://")) and not is_google_news(decoded):
                    resolved[source] = decoded
                else:
                    log(f"could not resolve Google News link: {result.get('message', 'unknown error')}")
    except Exception as e:  # never let link resolution break the run
        log(f"Google News resolution failed: {e}")
    log(f"resolved {len(resolved)}/{len(targets)} Google News links to publisher URLs")
    return resolved


MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 3


def _get_document(url: str):
    """Return ("html", text) or ("pdf", bytes) for a URL, or (None, None)."""
    for agent in (BOT_USER_AGENT, BROWSER_USER_AGENT):
        try:
            r = requests.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True,
                             headers={"User-Agent": agent,
                                      "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"})
        except Exception:
            continue
        if r.status_code != 200:
            continue
        ctype = r.headers.get("Content-Type", "").lower()
        if "pdf" in ctype or r.content[:5] == b"%PDF-":
            if len(r.content) <= MAX_PDF_BYTES:
                return "pdf", r.content
            return None, None
        if "html" in ctype:
            return "html", r.text
    return None, None


def _get_html(url: str):
    kind, body = _get_document(url)
    return body if kind == "html" else None


def extract_pdf_excerpt(data: bytes, limit: int = EXCERPT_CHARS) -> str:
    """Text of the first few pages of a PDF (regulators and central banks often publish as PDF)."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])
    except Exception as e:
        log(f"PDF text extraction failed: {e}")
        return ""
    return " ".join(text.split())[:limit].strip()


def extract_excerpt(html: str, limit: int = EXCERPT_CHARS) -> str:
    """Meta description plus the opening substantive paragraphs of the article body."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    parts = []
    for attrs in ({"property": "og:description"}, {"name": "description"}):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            parts.append(" ".join(meta["content"].split()))
            break

    container = soup.find("article") or soup.find("main") or soup.body or soup
    for p in container.find_all("p"):
        text = " ".join(p.get_text(" ", strip=True).split())
        if len(text) < MIN_PARAGRAPH_CHARS or text in parts:
            continue
        parts.append(text)
        if sum(len(x) for x in parts) >= limit:
            break
    return " ".join(parts)[:limit].strip()


def fetch_excerpt(url: str) -> str:
    kind, body = _get_document(url)
    if kind == "pdf":
        return extract_pdf_excerpt(body)
    if kind == "html":
        return extract_excerpt(body)
    return ""


def gather_evidence(analysis, by_id) -> Tuple[Dict[str, str], List[str]]:
    """Resolve links and fetch excerpts for every cited article.

    Mutates ``analysis`` so developments/targets point at publisher URLs where
    resolvable. Returns (article_id -> excerpt, list of newly trusted URLs).
    """
    cited: Dict[str, str] = {}
    for pillar in analysis.pillars:
        for dev in pillar.developments:
            cited[dev.article_id] = dev.url
    for target in analysis.new_high_signal_targets:
        if target.article_id and target.url:
            cited[target.article_id] = target.url

    resolved = resolve_google_news(list(cited.values()))
    final_urls = {aid: resolved.get(url, url) for aid, url in cited.items()}

    for pillar in analysis.pillars:
        for dev in pillar.developments:
            dev.url = final_urls.get(dev.article_id, dev.url)
    for target in analysis.new_high_signal_targets:
        if target.article_id in final_urls:
            target.url = final_urls[target.article_id]

    ids = list(final_urls)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        excerpts = list(pool.map(lambda aid: _safe_excerpt(final_urls[aid]), ids))
    evidence = {aid: text for aid, text in zip(ids, excerpts) if text}
    log(f"fetched excerpts for {len(evidence)}/{len(ids)} cited articles")
    return evidence, list(resolved.values())


def _safe_excerpt(url: str) -> str:
    if is_google_news(url):
        return ""  # unresolved redirect: nothing useful to fetch
    try:
        return fetch_excerpt(url)
    except Exception as e:
        log(f"excerpt fetch failed for {url}: {e}")
        return ""


def evidence_for_prompt(analysis, by_id, evidence: Dict[str, str]) -> Dict[str, dict]:
    """Compact {article_id: {headline, publisher, excerpt}} block for the editor."""
    block = {}
    ids: Iterable[str] = [d.article_id for p in analysis.pillars for d in p.developments]
    for aid in ids:
        article = by_id.get(aid, {})
        block[aid] = {
            "headline": article.get("title", ""),
            "publisher": article.get("source", ""),
            "excerpt": evidence.get(aid) or article.get("content", ""),
        }
    return block

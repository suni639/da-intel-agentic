import os
import sys
import json
import requests
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning

# Suppress BS4 XML warning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Paths optimized for our new agent workspace
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(WORKSPACE_DIR, "system_state.json")

# Load state history if present to ensure proper deduplication
if os.path.exists(STATE_PATH):
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        state = json.load(f)
else:
    state = {"processed_urls": {}}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_feed(source_name, feed_url, keyword_filter=None):
    articles = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=15)
        if r.status_code != 200: return articles
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # Support both RSS 2.0 (<item>) and Atom 1.0 (<entry>)
        items = soup.find_all('item')
        is_atom = False
        if not items:
            items = soup.find_all('entry')
            is_atom = True

        for item in items:
            title = item.find('title').get_text(strip=True) if item.find('title') else ""
            
            link = ""
            if is_atom:
                link_tag = item.find('link')
                if link_tag:
                    link = link_tag.get('href', '') or link_tag.get_text(strip=True)
            else:
                # Extract link robustly as html.parser treats <link> as void tag
                link_tag = item.find('link')
                if link_tag:
                    text = link_tag.get_text(strip=True)
                    if text:
                        link = text
                    elif link_tag.next_sibling:
                        link = link_tag.next_sibling.strip()
                
                if not link and link_tag and 'href' in link_tag.attrs:
                    link = link_tag['href']
                
            if link:
                # Resolve relative paths to absolute URLs
                link = urljoin(feed_url, link)
            
            if is_atom:
                summary_tag = item.find('summary') or item.find('content')
                desc = summary_tag.get_text(strip=True) if summary_tag else ""
            else:
                desc = item.find('description').get_text(strip=True) if item.find('description') else ""
            
            clean_content = BeautifulSoup(desc, 'html.parser').get_text(strip=True)[:1500]
            
            # Apply keyword filter for broad public-sector/regulator feeds to avoid noise
            if keyword_filter:
                combined_text = f"{title} {clean_content}".lower()
                if not any(kw.lower() in combined_text for kw in keyword_filter):
                    continue

            if link and link not in state.get("processed_urls", {}):
                articles.append({
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "content": clean_content
                })
    except Exception as e:
        print(f"Error parsing feed {source_name}: {e}", file=sys.stderr)
        pass
    return articles

def parse_rss_feed(source_name, feed_url, keyword_filter=None):
    return parse_feed(source_name, feed_url, keyword_filter)

# Institutional Digital Asset keywords for filtering general regulator feeds
PUBLIC_SECTOR_KEYWORDS = [
    "token", "tokenisation", "tokenization", "digital asset", "digital assets",
    "digital pound", "cbdc", "dss", "digital securities", "sandbox", "dlt",
    "distributed ledger", "blockchain", "stablecoin", "crypto", "settlement",
    "rtgs", "synchronisation", "synchronization", "deposit token", "tokenised deposit",
    "commercial bank money", "wholesale", "rwa", "fmi", "market infrastructure",
    "clearing", "collateral", "programmable", "fnality", "kinexys", "swift",
    "property (digital assets)", "custody", "t+1", "agentic", "zero-knowledge", "zk"
]

def run_ingestion():
    # Dedicated institutional and specialized feeds (unfiltered at ingestion)
    specialized_feeds = {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
        "The Block RSS": "https://www.theblock.co/rss.xml",
        "BIS Research": "https://www.bis.org/doclist/rss_all_categories.rss",
        "Ledger Insights": "https://www.ledgerinsights.com/feed/"
    }
    
    # Public sector and regulatory feeds (gated by institutional digital asset keywords)
    regulatory_feeds = {
        "BoE News": "https://www.bankofengland.co.uk/rss/news",
        "BoE Publications": "https://www.bankofengland.co.uk/rss/publications",
        "FCA Updates": "https://www.fca.org.uk/news/rss.xml",
        "HM Treasury": "https://www.gov.uk/government/organisations/hm-treasury.atom",
        "ECB Press": "https://www.ecb.europa.eu/rss/press.xml"
    }
    
    harvested = []
    for name, url in specialized_feeds.items():
        harvested.extend(parse_feed(name, url))
        
    for name, url in regulatory_feeds.items():
        harvested.extend(parse_feed(name, url, keyword_filter=PUBLIC_SECTOR_KEYWORDS))
        
    # Print clean JSON array to standard out for our Scout agent to capture
    print(json.dumps(harvested, indent=2))

if __name__ == "__main__":
    run_ingestion()
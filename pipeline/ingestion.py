import os
import sys
import json
import requests
import re
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

def parse_rss_feed(source_name, feed_url):
    articles = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=15)
        if r.status_code != 200: return articles
        soup = BeautifulSoup(r.content, 'html.parser')
        for item in soup.find_all('item'):
            title = item.find('title').get_text(strip=True) if item.find('title') else ""
            
            # Extract link robustly as html.parser treats <link> as void tag
            link_tag = item.find('link')
            link = ""
            if link_tag:
                text = link_tag.get_text(strip=True)
                if text:
                    link = text
                elif link_tag.next_sibling:
                    link = link_tag.next_sibling.strip()
            
            if not link and link_tag and 'href' in link_tag.attrs:
                link = link_tag['href']
                
            desc = item.find('description').get_text(strip=True) if item.find('description') else ""
            
            if link and link not in state.get("processed_urls", {}):
                articles.append({
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "content": BeautifulSoup(desc, 'html.parser').get_text(strip=True)[:1500]
                })
    except Exception as e:
        print(f"Error parsing feed {source_name}: {e}", file=sys.stderr)
        pass
    return articles

def run_ingestion():
    # Focused purely on high-signal institutional feeds
    feeds = {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
        "The Block RSS": "https://www.theblock.co/rss.xml",
        "BIS Research": "https://www.bis.org/doclist/rss_all_categories.rss"
    }
    
    harvested = []
    for name, url in feeds.items():
        harvested.extend(parse_rss_feed(name, url))
        
    # Print clean JSON array to standard out for our Scout agent to capture
    print(json.dumps(harvested, indent=2))

if __name__ == "__main__":
    run_ingestion()
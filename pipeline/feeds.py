"""Source configuration for the ingestion layer.

Each feed has a ``filter`` mode:
  - None:            ingest every item (highly specialised sources only)
  - "public_sector": keep items matching PUBLIC_SECTOR_KEYWORDS (regulators, central banks)
  - "institutional": keep items matching the narrower INSTITUTIONAL_KEYWORDS
                     (general crypto/fintech press, where most items are retail noise)

``candidate=True`` feeds are not ingested; they are only probed by
``pipeline/feed_check.py`` so they can be verified before being switched on.
"""
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    filter: Optional[str] = None
    candidate: bool = False


def google_news(name: str, query: str, days: int = 7) -> Feed:
    """Targeted Google News search feed (UK edition), limited to the last ``days``."""
    q = quote_plus(f"{query} when:{days}d")
    return Feed(name, f"https://news.google.com/rss/search?q={q}&hl=en-GB&gl=GB&ceid=GB:en",
                filter="institutional")


# Keywords for regulator / central bank feeds that publish on many topics.
PUBLIC_SECTOR_KEYWORDS = [
    "token", "tokenisation", "tokenization", "digital asset", "digital assets",
    "digital pound", "cbdc", "dss", "digital securities", "sandbox", "dlt",
    "distributed ledger", "blockchain", "stablecoin", "crypto", "settlement",
    "rtgs", "synchronisation", "synchronization", "deposit token", "tokenised deposit",
    "commercial bank money", "wholesale", "rwa", "fmi", "market infrastructure",
    "clearing", "collateral", "programmable", "fnality", "kinexys", "swift",
    "property (digital assets)", "custody", "t+1", "agentic", "zero-knowledge", "zk",
]

# Narrower list for general crypto/fintech press: institutional plumbing only.
# Deliberately excludes generic terms ("crypto", "blockchain", "token") that
# match nearly every retail/price story.
INSTITUTIONAL_KEYWORDS = [
    "tokenised", "tokenized", "tokenisation", "tokenization", "deposit token",
    "stablecoin", "cbdc", "central bank", "wholesale", "settlement", "custody", "custodian",
    "bank", "banks", "banking", "treasury", "treasuries", "money market fund", "mmf",
    "collateral", "repo", "clearing", "fmi", "market infrastructure", "real-world asset",
    "rwa", "bond", "gilt", "regulator", "regulation", "regulatory", "legislation", "bill",
    "mica", "genius act", "clarity act", "fca", "bank of england", "ecb", "federal reserve",
    "sec", "cftc", "occ", "mas", "hkma", "esma", "eba", "bis", "fsb", "iosco",
    "swift", "dtcc", "euroclear", "clearstream", "fnality", "kinexys", "canton", "partior",
    "agora", "rln", "regulated liability network", "dss", "digital securities sandbox",
    "blackrock", "buidl", "franklin templeton", "jpmorgan", "j.p. morgan", "citi", "hsbc",
    "barclays", "lloyds", "natwest", "standard chartered", "goldman", "bny", "state street",
    "circle", "usdc", "ripple", "rlusd", "paxos", "coinbase institutional", "anchorage",
    "agentic payment", "programmable", "atomic settlement", "dvp", "pvp", "interoperability",
]


FEEDS: List[Feed] = [
    # --- Specialist institutional press -----------------------------------
    Feed("Ledger Insights", "https://www.ledgerinsights.com/feed/"),

    # --- Targeted searches: cover the full week regardless of feed volume --
    google_news("News: Tokenised deposits & bank money",
                '"tokenised deposits" OR "tokenized deposits" OR "deposit token" OR "tokenised deposit"'),
    google_news("News: Wholesale settlement networks",
                'Fnality OR Kinexys OR "Canton Network" OR Partior OR "Regulated Liability Network" '
                'OR "Project Agora" OR "Project Agorá"'),
    google_news("News: UK digital securities & BoE",
                '"Digital Securities Sandbox" OR "digital gilt" OR DIGIT gilt OR '
                '"Bank of England" stablecoin OR "Bank of England" tokenisation'),
    google_news("News: Wholesale CBDC & central bank DLT",
                '"wholesale CBDC" OR "wholesale central bank digital currency" OR '
                '"Project Ensemble" OR "Project Guardian" OR "Pontes" ECB'),
    google_news("News: Stablecoin regulation",
                'stablecoin (regulation OR "GENIUS Act" OR MiCA OR FCA OR "systemic stablecoin")'),
    google_news("News: Tokenised funds & RWAs",
                '"tokenized fund" OR "tokenised fund" OR "tokenized treasury" OR '
                '"tokenised money market fund" OR "tokenized money market fund" OR "real-world assets" bank'),
    google_news("News: UK banks & digital assets",
                '(Lloyds OR Barclays OR HSBC OR NatWest OR "Standard Chartered") '
                '(tokenisation OR tokenization OR stablecoin OR "digital assets" OR blockchain)'),

    # --- General crypto press: narrowed to institutional stories ----------
    Feed("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
         filter="institutional"),
    Feed("The Block", "https://www.theblock.co/rss.xml", filter="institutional"),

    # --- UK & EU public sector ---------------------------------------------
    Feed("BoE News", "https://www.bankofengland.co.uk/rss/news", filter="public_sector"),
    Feed("BoE Publications", "https://www.bankofengland.co.uk/rss/publications", filter="public_sector"),
    Feed("FCA Updates", "https://www.fca.org.uk/news/rss.xml", filter="public_sector"),
    Feed("HM Treasury", "https://www.gov.uk/government/organisations/hm-treasury.atom",
         filter="public_sector"),
    Feed("ECB Press", "https://www.ecb.europa.eu/rss/press.xml", filter="public_sector"),

    # --- Candidates (probed by feed_check.py, not ingested yet) -----------
    Feed("BIS Press", "https://www.bis.org/doclist/all_pressrels.rss", filter="public_sector", candidate=True),
    Feed("BIS CPMI", "https://www.bis.org/doclist/cpmi_publs.rss", filter="public_sector", candidate=True),
    Feed("BIS Speeches", "https://www.bis.org/doclist/cbspeeches.rss", filter="public_sector", candidate=True),
    Feed("BIS Innovation Hub", "https://www.bis.org/doclist/bisih_publs.rss", filter="public_sector",
         candidate=True),
    Feed("Federal Reserve Press", "https://www.federalreserve.gov/feeds/press_all.xml",
         filter="public_sector", candidate=True),
    Feed("FSB", "https://www.fsb.org/feed/", filter="public_sector", candidate=True),
    Feed("ESMA", "https://www.esma.europa.eu/rss.xml", filter="public_sector", candidate=True),
    Feed("Finextra Headlines", "https://www.finextra.com/rss/headlines.aspx", filter="institutional",
         candidate=True),
    Feed("Global Custodian", "https://www.globalcustodian.com/feed/", filter="institutional", candidate=True),
    Feed("The TRADE", "https://www.thetradenews.com/feed/", filter="institutional", candidate=True),
    Feed("Banking Dive", "https://www.bankingdive.com/feeds/news/", filter="institutional", candidate=True),
    Feed("Payments Dive", "https://www.paymentsdive.com/feeds/news/", filter="institutional", candidate=True),
    Feed("DL News", "https://www.dlnews.com/arc/outboundfeeds/rss/", filter="institutional", candidate=True),
    Feed("Blockworks", "https://blockworks.co/feed", filter="institutional", candidate=True),
]

# Pages scanned by feed_check.py to discover feed URLs we don't know yet.
DISCOVERY_PAGES = [
    "https://www.bis.org/rss/index.htm",
    "https://www.bis.org/",
    "https://www.mas.gov.sg/news",
    "https://www.hkma.gov.hk/eng/other-information/rss/",
    "https://www.esma.europa.eu/press-news/esma-news",
    "https://www.eba.europa.eu/",
    "https://www.iosco.org/",
    "https://www.dtcc.com/news",
    "https://www.euroclear.com/newsandinsights/en.html",
    "https://www.swift.com/news-events/news",
    "https://www.finextra.com/rss/rss.aspx",
]


def active_feeds() -> List[Feed]:
    return [f for f in FEEDS if not f.candidate]

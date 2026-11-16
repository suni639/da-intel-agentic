"""Source configuration for the ingestion layer.

Each feed has a ``filter`` mode:
  - None:            ingest every item (highly specialised sources only)
  - "public_sector": keep items matching PUBLIC_SECTOR_KEYWORDS (regulators, central banks)
  - "institutional": keep items matching the narrower INSTITUTIONAL_KEYWORDS
                     (crypto press, where everything is digital-asset but most is retail noise)
  - "digital_asset": keep items matching DIGITAL_ASSET_KEYWORDS
                     (banking/payments press, where everything is banking but little is digital-asset)

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


# For general banking / payments / custody press: require a digital-asset nexus.
DIGITAL_ASSET_KEYWORDS = [
    "tokenised", "tokenized", "tokenisation", "tokenization", "tokenise", "tokenize",
    "token", "tokens", "deposit token", "stablecoin", "stablecoins", "cbdc", "digital asset",
    "digital assets", "digital currency", "digital pound", "digital euro", "digital dollar",
    "crypto", "cryptocurrency", "blockchain", "dlt", "distributed ledger", "on-chain", "onchain",
    "smart contract", "web3", "kinexys", "fnality", "canton", "partior", "usdc", "rlusd",
]

FEEDS: List[Feed] = [
    # --- Specialist institutional press -----------------------------------
    # Ledger Insights' own feed only ever serves its latest item, and Finextra
    # refuses automated clients, so both are read via site-restricted searches.
    Feed("Ledger Insights", "https://news.google.com/rss/search?q="
         + quote_plus("site:ledgerinsights.com when:7d") + "&hl=en-GB&gl=GB&ceid=GB:en"),
    Feed("Finextra (digital assets)", "https://news.google.com/rss/search?q="
         + quote_plus("site:finextra.com (tokenisation OR tokenised OR stablecoin OR CBDC OR "
                      "blockchain OR DLT OR \"digital assets\") when:7d") + "&hl=en-GB&gl=GB&ceid=GB:en"),

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
    google_news("News: Market infrastructure & FMIs",
                '(Euroclear OR Clearstream OR DTCC OR Swift OR LSEG OR "Deutsche Börse") '
                '(tokenisation OR tokenization OR "digital assets" OR DLT OR blockchain OR stablecoin)'),
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

    # --- Global public sector (verified by feed_check) ---------------------
    Feed("BIS Central Bank Speeches", "https://www.bis.org/doclist/cbspeeches.rss", filter="public_sector"),
    Feed("Federal Reserve Press", "https://www.federalreserve.gov/feeds/press_all.xml",
         filter="public_sector"),
    Feed("FSB", "https://www.fsb.org/feed/", filter="public_sector"),
    Feed("ESMA", "https://www.esma.europa.eu/rss.xml", filter="public_sector"),

    # --- Banking, payments & custody press (verified by feed_check) --------
    Feed("Banking Dive", "https://www.bankingdive.com/feeds/news/", filter="digital_asset"),
    Feed("Payments Dive", "https://www.paymentsdive.com/feeds/news/", filter="digital_asset"),
    Feed("Global Custodian", "https://www.globalcustodian.com/feed/", filter="digital_asset"),

    # --- Candidates (probed by feed_check.py, not ingested yet) -----------
    Feed("HKMA Press", "https://www.hkma.gov.hk/eng/other-information/rss/rss_press-release.xml",
         filter="public_sector", candidate=True),
    Feed("EBA News", "https://www.eba.europa.eu/news-press/news/rss.xml", filter="public_sector",
         candidate=True),
    Feed("IOSCO", "https://www.iosco.org/rss/rss.xml", filter="public_sector", candidate=True),
    Feed("BIS FSI", "https://www.bis.org/doclist/bis_fsi_publs.rss", filter="public_sector", candidate=True),
    Feed("BIS Management Speeches", "https://www.bis.org/doclist/mgmtspeeches.rss", filter="public_sector",
         candidate=True),
]

# Pages scanned by feed_check.py to discover feed URLs we don't know yet.
DISCOVERY_PAGES = [
    "https://www.dtcc.com/rss-feeds",
    "https://www.mas.gov.sg/rss",
]


def active_feeds() -> List[Feed]:
    return [f for f in FEEDS if not f.candidate]

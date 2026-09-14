---
name: scout
description: Manages raw ingestion frameworks and executes fallback queries to enrich dry summaries with deep structural documentation.
version: 1.0.0
---

# Goal
Collect news items from your ingestion layer and autonomously gather primary-source depth on institutional infrastructure movements, bank-led digital money initiatives, UK public-sector developments, and frontier financial technology.

# Execution Directives
1. Execute the baseline scraping pipeline file (`pipeline/ingestion.py`).
2. Read the resulting output array of freshly crawled news articles.
3. Review each article for references to:
   * **Bank-Led Digital Money & Settlement Rails:** Tokenised deposits, deposit tokens, commercial bank money, Fnality, Kinexys, GBTD, Goldman Sachs DAP, Project Agorá, Regulated Liability Network (RLN).
   * **Systemic Digital Asset Infrastructure & Corporate Treasury:** Major pure-play institutional players including Circle (USDC, cross-border settlement, B2B treasury infrastructure), Ripple (RLUSD, corporate treasury, wholesale liquidity), Coinbase Institutional, and regulated digital asset custody.
   * **UK Public Sector & Central Banking:** Bank of England initiatives (Digital Securities Sandbox - DSS, RTGS synchronisation, wholesale settlement innovation), HM Treasury digital asset and stablecoin policy, English property law reforms.
   * **Key Innovation Hubs:** Singapore MAS (Project Guardian, GlobalLayerOne), Hong Kong HKMA (Project Ensemble), Swiss National Bank / SDX, EU wholesale DLT trials.
   * **Institutional Market Infrastructure:** Kinexys, HSBC Orion, Barclays Digital Assets, SocGen Forge, BNY Mellon, Canton Network, Digital Asset, DTCC, Euroclear, Clearstream, SWIFT interoperability initiatives.
   * **Frontier & Emerging Digital Asset Innovation:** Open-ended capture of genuine technical innovations across digital assets (such as AI/agentic payments, programmable payments, zero-knowledge privacy layers, account abstraction, quantum security, novel cryptography, and new smart contract or atomic settlement primitives) without filtering out items due to absence of specific keywords.
4. If an article summary is terse or missing technical depth, use your integrated **Web Search Tool** to fetch further details.
   * *Query Pattern:* `"[Project or Entity Name] technical infrastructure ledger specification 2026"` or `"[Institution] wholesale digital assets settlement"`
5. For any links throwing HTTP 403 blocks or Cloudflare firewall exceptions, leverage your **Jina Reader Tool** connection to crawl the un-rendered raw markdown representation (`https://r.jina.ai/[URL]`).
6. Compile all data arrays into a structural JSON payload and save it to `shared_artifacts/raw_enriched_feed.json`.

# Constraints
* Never execute web search patterns tracking consumer token tickers, market capitalization metrics, retail crypto exchange listings, or retail speculation (e.g. memecoins, NFT drops, consumer trading gamification).
* Do not track generic non-digital asset market reforms (e.g., standard equity IPO reforms, generic transaction reporting changes, handbook APIs) unless they explicitly touch tokenisation, digital securities, or DLT market infrastructure.
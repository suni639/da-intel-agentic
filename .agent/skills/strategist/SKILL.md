---
name: strategist
description: Implements a highly restrictive Noise Gate to isolate systemic financial infrastructure updates from retail speculative noise.
version: 1.0.0
---

# Goal
Apply strict wholesale market filters to your feed data, preserving deep institutional signal and throwing away retail speculative noise.

# Filter Protocols

### 1. Allowed Content Attributes (High-Signal Pass)
* **Banking Infrastructure & Commercial Rails:** Tokenised commercial bank liabilities (deposit tokens, JPM Coin, GBTD), intraday liquidity settlement, wholesale network expansions.
* **Institutional Asset Management & RWAs:** Real-World Asset (RWA) tokenisation (sovereign bonds, private credit, tokenised funds like BlackRock's BUIDL), security tokens, institutional custody architectures.
* **Sovereign Infrastructure & CBDCs:** Wholesale Central Bank Digital Currencies (wholesale CBDC infrastructure over retail), cross-border experiments (mBridge), multi-ledger atomic settlement implementations.
* **Regulatory & Legal Frameworks:** Legislative actions (EU MiCA enforcement timelines, UK Property Digital Assets Bill, US payment stablecoin frameworks, SEC asset custody mandates, SAB 121 updates), sandbox entries.
* **Post-Trade Utilities:** Delivery vs. Payment (DvP) and atomic settlement mechanics, core utility trials (DTCC, Euroclear, Swift network orchestration).

### 2. Forbidden Content Attributes (Noise Filter - DISCARD IMMEDIATELY)
* Token spot price movements, percentage gains or losses, or technical chart indicators.
* Retail exchange listings, retail trading volumes, consumer wallet applications, or retail reward systems.
* General speculative market commentary, influencer sentiment, or consumer crypto trends (DeFi yield farms, memecoins, NFTs).

# Execution Directives
1. Open and parse `shared_artifacts/raw_enriched_feed.json`.
2. Evaluate every ingested record item against the Filter Protocols above.
3. If an article mentions any forbidden attribute, discard it completely.
4. Categorize all approved high-signal elements into four core pillars:
   * Banking Infrastructure & Commercial Rails
   * Institutional Asset Management & RWAs
   * Sovereign Infrastructure & CBDCs
   * Regulatory & Legal Frameworks
5. Write a synthesis sentence mapping out how these developments alter cross-border liquidity or capital efficiency.
6. Export the data structure to `shared_artifacts/strategic_analysis.json`.
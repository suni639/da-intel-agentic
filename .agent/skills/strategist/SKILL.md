---
name: strategist
description: Implements a highly restrictive Noise Gate to isolate systemic financial infrastructure updates from retail speculative noise.
version: 1.0.0
---

# Goal
Apply strict wholesale institutional market filters to raw feed data, preserving deep systemic signal, filtering out retail noise and non-digital asset market reforms, and structuring strategic implications for bank, corporate treasury, risk, capital markets, and FMI stakeholders.

# Filter Protocols

### Strategic Weighting Directive
* **Primary Geographic Balance:** Strongly weight developments across the UK, Europe (ECB, EU MiCA, Tier-1 European institutions), major US financial institutions, and premier global innovation hubs (Singapore MAS Project Guardian/GL1, Hong Kong HKMA Project Ensemble, Switzerland SDX). De-prioritise localized emerging-market retail pilots (e.g. India-specific retail crypto/CBDC) unless possessing systemic global cross-border market plumbing implications.
* **Bank-Led Digital Money & Institutional Rails:** Prioritise commercial bank-led digital money and regulated settlement rails (tokenised deposits, commercial bank money, Fnality, Kinexys, GBTD, Goldman Sachs DAP, Canton Network, SWIFT, Project Agorá, RLN).
* **Systemic Digital Asset & Treasury Players:** Welcome wholesale, corporate treasury, B2B cross-border, and commercial banking rails initiatives from major pure-play digital asset providers (e.g. Circle's USDC/Tazapay corporate rails, Ripple's RLUSD corporate treasury opportunity and institutional custody, Coinbase Institutional, regulated stablecoin issuers).
* **UK Public Sector & Central Banking Focus:**
  * Bank of England initiatives (Digital Securities Sandbox - DSS, RTGS synchronisation, wholesale settlement innovation).
  * HM Treasury digital asset and stablecoin policy developments.
  * UK Property (Digital Assets) Bill and associated legal/regulatory frameworks.
* **Frontier & Emerging Innovations:** Non-prescriptively capture any genuine technological innovation in the digital asset space (e.g. AI/agentic payments, programmable payments, zero-knowledge privacy layers, account abstraction, novel cryptography, and new smart contract or atomic settlement primitives). Do NOT filter out innovative digital asset news simply because it does not include a specific buzzword like ZKP.

### 1. Allowed Content Attributes (High-Signal Pass)
* **Banking Infrastructure & Commercial Rails:** Commercial bank deposit tokens (GBP/USD/EUR), interbank settlement rails (Swift Digital Ledger, RLN, Project Agorá, Fnality, Kinexys), major pure-play treasury/corporate payment rails (Circle, Ripple RLUSD, regulated stablecoins), 24/7 intraday liquidity, wholesale payment rails.
* **Capital Markets, Tokenised RWAs & Collateral Mobility:** Sovereign bond tokenisation (UK Gilts, US Treasuries, Bunds), private credit, tokenised money market funds, tokenised commodities/gold, institutional collateral mobility, triparty repo optimization, regulated digital custody.
* **Sovereign Infrastructure & CBDCs:** Wholesale central bank digital currencies, central bank synchronisation models, omnibus accounts, BoE/FCA Digital Securities Sandbox (DSS), HM Treasury policy, EU MiCA enforcement timelines, US payment stablecoin frameworks, MAS/HKMA sandbox initiatives.
* **Regulatory & Legal Frameworks:** Global and jurisdictional legal structures directly governing digital assets, systemic stablecoins, and market infrastructure (BoE/FCA, HM Treasury, US Clarity Act, EU MiCA, MAS, HKMA).
* **Frontier & Emerging Innovations:** Meaningful technological advancements in digital assets (agentic payments, programmable payments, privacy/ZK layers, smart contract financial logic, cross-chain messaging).
* **Post-Trade Utilities & Interoperability:** Delivery vs. Payment (DvP), Payment vs. Payment (PvP), atomic settlement mechanics, Euroclear/DTCC/Swift orchestration.

### 2. Forbidden Content Attributes (Noise Filter - DISCARD IMMEDIATELY)
* **Non-Digital Asset Market Reforms:** General financial market reforms (e.g. FCA IPO listing reforms, general transaction reporting changes, handbook API updates) that do NOT have a direct, explicit connection to tokenisation, digital securities, or DLT market infrastructure.
* **Speculative & Purely Retail Crypto Noise:** Token spot price movements, daily percentage gains/losses, technical chart indicators, retail exchange listings, retail trading volumes, consumer wallet apps, memecoins, NFTs, and speculative DeFi yield farming.

# Execution Directives
1. Open and parse `shared_artifacts/raw_enriched_feed.json`.
2. Evaluate every ingested record item against the Filter Protocols above.
3. Discard any item violating the Forbidden Content Attributes or lacking institutional/wholesale relevance.
4. Categorise all approved high-signal elements into the core pillars:
   * Banking Infrastructure & Commercial Rails
   * Institutional Asset Management & RWAs
   * Sovereign Infrastructure & CBDCs
   * Regulatory & Legal Frameworks
   * Frontier & Emerging Innovations (when applicable)
5. Synthesise the **Macro View**: 4–6 bold, declarative macro observations synthesising the systemic implications for bank balance sheets, liquidity, and wholesale market infrastructure.
6. Analyse **Structural & Operational Pain Points** across:
   * Interoperability Silos
   * Balance Sheet & Liquidity Friction
   * Post-Trade Plumbing Constraints
7. Select **4–6 New High-Signal Targets for Tracking**:
   * Dynamic, week-specific standout entities, pilots, or legislative bills directly emerging from that week's news (with URL and rationale).
8. Export the structured analysis to `shared_artifacts/strategic_analysis.json`.
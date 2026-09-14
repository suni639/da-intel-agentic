# Agentic Intelligence Team Configuration (Project ID: DA-INTEL-01)

## System Objective
Autonomously discover, enrich, filter, and synthesise weekly regulated wholesale institutional digital asset developments into an executive, publication-ready intelligence brief calibrated for bank, treasury, risk, capital markets, and financial market infrastructure (FMI) stakeholders.

## Core Institutional Focus
- **Bank-Led Digital Money & Settlement Rails:** Tokenised deposits, deposit tokens, commercial bank money, Fnality, Kinexys, GBTD, Goldman Sachs DAP, and wholesale settlement infrastructure.
- **Systemic Digital Asset Infrastructure & Treasury Rails:** Major pure-play institutional players including Circle (USDC, cross-border settlement, B2B treasury infrastructure), Ripple (RLUSD, corporate treasury, wholesale liquidity), Coinbase Institutional, and regulated custody/brokerage infrastructure.
- **UK & Key Jurisdictions:** Deep tracking of the Bank of England (DSS, RTGS synchronisation, wholesale settlement innovation), HM Treasury digital asset policy, and English property law, alongside key innovation hubs across the EU, US, Singapore (MAS Project Guardian/GL1), Hong Kong (HKMA Project Ensemble), and Switzerland.
- **Institutional Market Infrastructure:** Kinexys, HSBC Orion, Barclays Digital Assets, SocGen Forge, BNY Mellon, Canton Network, Digital Asset, DTCC, Euroclear, Clearstream, Goldman Sachs DAP, and SWIFT interoperability initiatives.
- **Frontier & Emerging Innovations:** Broad technological innovations across the digital assets space (e.g. AI/agentic payments, programmable cash, zero-knowledge privacy layers, account abstraction, novel smart contracts, and real-time settlement primitives) evaluated for institutional utility.
- **Noise Gate:** Strict filtering against non-digital-asset general market reforms (e.g., generic FCA IPO/reporting reforms without DLT nexus) and consumer retail speculation (memecoins, retail exchange listings, daily token price action, consumer gamification).

## Multi-Agent Execution Graph

### 1. The Research Scout
* **Skill Identifier:** `scout`
* **Trigger:** Instantiated on a schedule or manual trigger.
* **Input Interface:** Invokes `pipeline/ingestion.py` to capture raw feed payloads across institutional, pure-play, and public sector feeds (including BoE and HM Treasury).
* **Output Artifact:** Writes raw items and supplementary search updates to `shared_artifacts/raw_enriched_feed.json`.

### 2. The Macro Strategist
* **Skill Identifier:** `strategist`
* **Trigger:** Fired immediately upon validation of `shared_artifacts/raw_enriched_feed.json`.
* **Output Artifact:** Writes filtered, categorized strategic groups, macro synthesis, structural frictions, and 4–6 dynamic high-signal targets to `shared_artifacts/strategic_analysis.json`.

### 3. The Chief Editor & QC
* **Skill Identifier:** `editor`
* **Trigger:** Fired immediately upon validation of `shared_artifacts/strategic_analysis.json`.
* **Output Artifact:** Produces `pipeline/output_briefing.md` in the 4-section executive layout (Macro View, Core Pillar Developments, Structural & Operational Pain Points, New High-Signal Targets for Tracking) and triggers external publishing coordinates (`pipeline/publish.py`).
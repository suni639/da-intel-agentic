# Digital Asset Intelligence Engine (Project ID: DA-INTEL-01)

An automated, multi-agent pipeline designed to discover, enrich, filter, and synthesise weekly regulated wholesale institutional digital asset developments into a publication-ready brief. 

Outputs are delivered directly as a styled HTML newsletter to my Gmail and auto-deployed as a markdown post to my Hugo-based website.

---

## Multi-Agent Execution Graph

The engine runs as a sequence of three virtual agents, followed by an automated publishing coordinator:

```mermaid
graph TD
    A[1. Research Scout] -->|raw_enriched_feed.json| B[2. Macro Strategist]
    B -->|strategic_analysis.json| C[3. Chief Editor & QC]
    C -->|output_briefing.md| D[4. External Publisher]
    D -->|SMTP| E((Gmail Inbox))
    D -->|Git Push| F((Hugo Website))
```

1. **The Research Scout (`scout`)**
   - **Trigger**: Instantiated via scheduler or manually.
   - **Action**: Invokes `pipeline/ingestion.py` to scrape high-signal RSS feeds (CoinDesk, The Block, the Bank for International Settlements, Ledger Insights, the European Central Bank, and the Bank of England).
   - **Feeds**: CoinDesk, The Block, BIS and Ledger Insights are ingested unfiltered; Bank of England, FCA, HM Treasury and ECB feeds are gated by an institutional digital-asset keyword list. Per-feed HTTP status and item counts are logged to stderr so a blocked or empty feed is visible in the run log.
   - **Output**: Writes combined raw/enriched feed items to `shared_artifacts/raw_enriched_feed.json`.

2. **The Macro Strategist (`strategist`)**
   - **Trigger**: Fired immediately upon validation of the raw feed.
   - **Action**: Applies a strict institutional "Noise Gate" filter to remove retail speculative noise (spot prices, memecoins, consumer wallets, and retail volumes).
   - **Categorisation**: Organises approved developments into four core pillars and synthesises their impact on cross-border liquidity and capital efficiency.
   - **Schema**: Gemini is called with a Pydantic `response_schema` (`pipeline/schema.py`), and the response is validated before use. Pillar names are an enum, and URLs must be copied from the ingested feed.
   - **Output**: Writes the structured payload to `shared_artifacts/strategic_analysis.json`.

3. **The Chief Editor & QC (`editor`)**
   - **Trigger**: Fired immediately upon validation of the strategic analysis.
   - **Action**: Rewrites only the *prose* fields of the analysis JSON (British English, no hedging). Its output is merged back with URLs, titles and names taken from the strategist, so the editor cannot alter links. If the editor fails or changes the structure, the strategist prose is used.
   - **Rendering & QC** (`pipeline/render.py`): The Markdown brief is rendered deterministically from the JSON, so the 4-section layout is fixed in code. Before rendering:
     - any link not present in the ingested feed is replaced with a Google Search fallback, which stops hallucinated URLs from being published;
     - `-ize`/`-yze` spellings in prose are converted to British `-ise`/`-yse` (source headlines and proper nouns are left verbatim);
     - hedging phrases are flagged in the log.
   - **Output**: Writes the compiled briefing file to `pipeline/output_briefing.md`.

4. **The External Publisher (`publisher`)**
   - **Action**: Invokes `pipeline/publish.py` to convert the markdown briefing into an HTML newsletter, sends it via SMTP Gmail, prepends YAML frontmatter, and commits/pushes the new post to the Hugo website directory.

---

## File Structure

```text
da-intel-agentic/
├── .agent/
│   └── agents.md          # Multi-agent execution graph definition
├── .github/
│   └── workflows/
│       └── intelligence_engine.yml # GitHub Actions workflow scheduler
├── pipeline/
│   ├── ingestion.py       # Base feed harvesting and parsing logic
│   ├── common.py          # Shared env/logging helpers
│   ├── schema.py          # Pydantic contract for the strategist/editor JSON
│   ├── render.py          # Deterministic Markdown rendering, link allowlist, British English QC
│   ├── publish.py         # SMTP transmission and Git push automation
│   └── run_pipeline.py    # Main pipeline orchestrator (Gemini API sequence)
├── tests/                 # unittest suite (run in CI)
├── shared_artifacts/      # Intermediate JSON payloads (gitignored)
├── .gitignore             # Local files exclusion configuration
├── requirements.txt       # Python dependencies for local & CI environments
└── README.md              # Project documentation
```

---

## Getting Started

### Prerequisites
- Python 3.11 or higher installed locally.
- Git installed (for committing and pushing changes).

### Environment Configuration
The pipeline loads credentials and configuration options from environment variables. Under Windows, it will fallback to checking your User Environment registry (`HKEY_CURRENT_USER\Environment`). 

Ensure the following variables are configured:
- `GEMINI_API_KEY`: Your Google Gemini API key.
- `SMTP_USER`: Your Gmail address.
- `SMTP_PASS`: Your Gmail App Password (generated via Google Account settings).
- `RECIPIENT_EMAIL`: Destination address(es) for the briefing, comma- or semicolon-separated (defaults to `SMTP_USER` if not set).
- `GEMINI_MODEL` (Optional): Primary model (default `gemini-2.5-flash`).
- `GEMINI_API_VERSION` (Optional): Gemini API version (default `v1beta`, which structured JSON output requires).
- `GEMINI_FALLBACK_MODELS` (Optional): Comma-separated fallback chain used when the primary model is unavailable. Rate-limit and server errors (429/5xx) are retried with backoff; auth errors (401/403) fail immediately.
- `HUGO_DIR` (Optional): Path to your local Hugo site repository directory. If not set, defaults to a sibling folder named `sunilkandola-hugo`.

---

## Execution

### Local Run
To execute the entire pipeline end-to-end (ingest, filter, write, email, and publish to Hugo):
```bash
python pipeline/run_pipeline.py
```

### Tests
```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```
Tests run on every push and pull request (`.github/workflows/tests.yml`), and again before each scheduled pipeline run.

### Dry Run (Testing End-to-End Delivery)
To execute the entire pipeline, including scraping feeds and compiling the briefing locally via Gemini, without making SMTP connections or pushing commits to the live Hugo website:
```bash
python pipeline/run_pipeline.py --dry-run
```

---

## Automated Weekly Deployment

Weekly runs are orchestrated automatically via **GitHub Actions** every Monday morning.

### Required Repository Secrets
To support remote execution, go to your repository settings (`Settings -> Secrets and variables -> Actions`) and add the following repository secrets:
- `GEMINI_API_KEY`
- `SMTP_USER`
- `SMTP_PASS`
- `RECIPIENT_EMAIL`
- `HUGO_REPO_PAT`: A GitHub Personal Access Token (PAT) with write permissions for my `sunilkandola-hugo` site repository.

---

## Quality Control (QC) Directives
All briefings generated by the engine must adhere to the following compliance rules:
* **No AI Fluff**: Avoid vague, hedging phrases or generic AI-isms. Present facts directly.
* **Primary Source Integrity** *(enforced in code)*: Every link in the brief must be a URL from this run's ingested feed. Anything else, including plausible-looking but invented URLs, is replaced with an absolute Google Search query URL.
* **Strict British English** *(enforced in code for prose)*: `-ize`/`-ization`/`-yze` variants are converted automatically. Quoted source headlines are left as published.
* **Deduplication state**: `system_state.json` records processed URLs and is committed back by the scheduled workflow. Entries older than 120 days are pruned automatically, since RSS feeds no longer serve items that old.

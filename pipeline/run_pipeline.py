import os
import sys
import json
import subprocess
import datetime
import time
from google import genai
from google.genai import types

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERROR_LOG_PATH = os.path.join(WORKSPACE_ROOT, "error_log.txt")

def generate_content_with_retry(client, model, contents, config=None, max_retries=5, initial_delay=2):
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            if config:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
            else:
                response = client.models.generate_content(
                    model=model,
                    contents=contents
                )
            return response
        except Exception as e:
            error_msg = str(e)
            print(f"Gemini API call attempt {attempt} failed: {error_msg}. Retrying in {delay}s...")
            if attempt == max_retries:
                raise e
            time.sleep(delay)
            delay *= 2  # Exponential backoff

def log_error(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] ERROR: {msg}\n")
    print(f"ERROR: {msg}", file=sys.stderr)

def get_env_var(name):
    val = os.environ.get(name)
    if not val and sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
            val, _ = winreg.QueryValueEx(key, name)
            winreg.CloseKey(key)
        except Exception:
            pass
    return val

def run_strategist(client, model, articles):
    print("Executing Macro Strategist (Noise Gate & Categorisation)...")
    
    prompt = f"""
You are the Macro Strategist for the Institutional Digital Asset Intelligence pipeline.
Your job is to apply a strict "Noise Gate" to the raw feed articles below and categorise the high-signal developments.

Allowed Content Attributes (High-Signal):
- Banking Infrastructure & Commercial Rails (Tokenised deposits, JPM Coin, GBTD, intraday settlement, wholesale expansions).
- Institutional Asset Management & RWAs (Real-world asset tokenisation, sovereign bonds, private credit, tokenised funds, custody).
- Sovereign Infrastructure & CBDCs (Wholesale CBDC trials, cross-border multi-ledger platforms, mBridge, Project Cedar).
- Regulatory & Legal Frameworks (EU MiCA, UK Property Digital Assets Bill, US stablecoin rules, SEC mandates, sandboxes).
- Post-Trade Utilities (DvP, atomic settlement, DTCC/Euroclear/Swift orchestration).

Forbidden Content Attributes (Noise - DISCARD IMMEDIATELY):
- Token spot price movements, daily gains/losses, or technical chart analysis.
- Retail exchange listings, retail trading volumes, consumer wallets, or rewards.
- Speculative market commentary, influencer sentiment, memecoins, DeFi yield farms, NFTs.

For the approved articles, group them into the 4 pillars:
1. Banking Infrastructure & Commercial Rails
2. Institutional Asset Management & RWAs
3. Sovereign Infrastructure & CBDCs
4. Regulatory & Legal Frameworks

Write a custom synthesis sentence for each pillar explaining how these developments alter cross-border liquidity or capital efficiency.

Return the result STRICTLY as a JSON object matching this structure (no markdown formatting blocks, no extra text):
{{
  "Banking Infrastructure & Commercial Rails": {{
    "synthesis": "...",
    "developments": [
      {{ "title": "...", "source": "...", "details": "..." }}
    ]
  }},
  "Institutional Asset Management & RWAs": {{
    "synthesis": "...",
    "developments": [
      {{ "title": "...", "source": "...", "details": "..." }}
    ]
  }},
  "Sovereign Infrastructure & CBDCs": {{
    "synthesis": "...",
    "developments": [
      {{ "title": "...", "source": "...", "details": "..." }}
    ]
  }},
  "Regulatory & Legal Frameworks": {{
    "synthesis": "...",
    "developments": [
      {{ "title": "...", "source": "...", "details": "..." }}
    ]
  }}
}}

Raw feed articles:
{json.dumps(articles, indent=2)}
"""

    try:
        response = generate_content_with_retry(
            client=client,
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        log_error(f"Macro Strategist API execution failed: {e}")
        return None

def run_editor(client, model, strategic_analysis):
    print("Executing Chief Editor & QC (Briefing Compilation)...")
    
    prompt = f"""
You are the Chief Editor for the Institutional Digital Asset Intelligence pipeline.
Your job is to parse the strategic analysis JSON below and compile a publication-ready Markdown briefing.

Formatting Rules:
1. DO NOT output a top-level H1 header (e.g. # Header). Start directly with H2 headers.
2. Apply strict British English spelling (e.g., tokenised, tokenisation, utilised, prioritised, standardise, programmes, centre).
3. Embed clean, inline Markdown links back to primary sources (or search terms if URL not present) wherever a project or entity is mentioned.
4. No AI Fluff: Avoid hedging phrases like "appears to", "it is evident that", "underscored by". State the operational facts plainly.

Required Structural Layout:

## 1. MACRO VIEW
[Provide 5-7 punchy bullet points. Each bullet must open with a **bold declarative statement** (the headline), followed by 1-2 sentences of supporting facts. State the fact and why it matters to market plumbing. Write in British English. Scannable and direct.]

## 2. CORE PILLAR DEVELOPMENTS
* **Banking Infrastructure & Commercial Rails:** [Include detailed updates from the JSON]
* **Institutional Asset Management & RWAs:** [Include detailed updates from the JSON]
* **Sovereign Infrastructure & CBDCs:** [Include detailed updates from the JSON]
* **Regulatory & Legal Frameworks:** [Include detailed updates from the JSON]

## 3. STRUCTURAL & OPERATIONAL PAIN POINTS
* **Interoperability Silos:** [Identify where separate systems/ledgers fail to bridge cleanly]
* **Balance Sheet & Liquidity Friction:** [Identify balance sheet fragmentation or capital constraints]
* **Post-Trade Plumbing Constraints:** [Identify custodian or settlement bottleneck frictions]

## 4. NEW HIGH-SIGNAL TARGETS FOR TRACKING
* [List 3-5 hyper-specific project names, working groups, or pieces of legislation discovered this week to add to keyword filters. Include direct markdown source links.]

Strategic Analysis JSON:
{json.dumps(strategic_analysis, indent=2)}
"""

    try:
        response = generate_content_with_retry(
            client=client,
            model=model,
            contents=prompt
        )
        return response.text
    except Exception as e:
        log_error(f"Chief Editor API execution failed: {e}")
        return None

def main():
    print("Pipeline orchestration run started...")
    
    # Ensure directories exist
    os.makedirs(os.path.join(WORKSPACE_ROOT, "shared_artifacts"), exist_ok=True)
    
    gemini_key = get_env_var("GEMINI_API_KEY")
    if not gemini_key:
        log_error("GEMINI_API_KEY environment variable is not set. Pipeline aborted.")
        sys.exit(1)
        
    client = genai.Client(api_key=gemini_key)
    gemini_model = get_env_var("GEMINI_MODEL") or "gemini-2.5-flash"
    
    # Step 1: Run Ingestion
    print("Running Ingestion layer...")
    try:
        raw_feed_str = subprocess.check_output(
            [sys.executable, os.path.join(WORKSPACE_ROOT, "pipeline", "ingestion.py")],
            text=True
        )
        raw_feed = json.loads(raw_feed_str)
    except Exception as e:
        log_error(f"Ingestion script execution failed: {e}")
        sys.exit(1)
        
    if not raw_feed:
        print("No new articles discovered. Stopping pipeline.")
        sys.exit(0)
        
    print(f"Ingested {len(raw_feed)} new articles.")
    
    # Save a temporary raw feed file for the Scout enrichment step representation
    raw_enriched_path = os.path.join(WORKSPACE_ROOT, "shared_artifacts", "raw_enriched_feed.json")
    with open(raw_enriched_path, "w", encoding="utf-8") as f:
        json.dump({"raw_articles": raw_feed}, f, indent=2)
    
    # Step 2: Run Macro Strategist
    strategic_analysis = run_strategist(client, gemini_model, raw_feed)
    if not strategic_analysis:
        log_error("Macro Strategist failed to output analysis.")
        sys.exit(1)
        
    analysis_path = os.path.join(WORKSPACE_ROOT, "shared_artifacts", "strategic_analysis.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(strategic_analysis, f, indent=2)
    print(f"Strategic analysis successfully saved to {analysis_path}")
    
    # Step 3: Run Chief Editor
    briefing = run_editor(client, gemini_model, strategic_analysis)
    if not briefing:
        log_error("Chief Editor failed to output briefing.")
        sys.exit(1)
        
    briefing_path = os.path.join(WORKSPACE_ROOT, "pipeline", "output_briefing.md")
    with open(briefing_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(f"Briefing successfully compiled to {briefing_path}")
    
    # Step 4: Run Publishing Layer
    print("Invoking Publishing layer...")
    try:
        subprocess.run(
            [sys.executable, os.path.join(WORKSPACE_ROOT, "pipeline", "publish.py")],
            check=True
        )
        print("Pipeline run completed successfully.")
    except Exception as e:
        log_error(f"Publishing script failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

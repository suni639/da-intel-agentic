import os
import sys
import json
import subprocess
import datetime
import time

from google import genai
from google.genai import types
from pydantic import ValidationError

from common import WORKSPACE_ROOT, get_env_var, log_error
from render import finalise_briefing
from schema import StrategicAnalysis

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]
# HTTP statuses worth retrying on the same model.
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
# Statuses where another model may succeed but retrying this one will not.
SWITCH_MODEL_STATUS = {400, 404}
STATE_RETENTION_DAYS = 120


def _error_status(exc):
    """Best-effort HTTP status for an SDK exception (None for network errors)."""
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None


def get_fallback_models():
    configured = get_env_var("GEMINI_FALLBACK_MODELS")
    if configured:
        return [m.strip() for m in configured.split(",") if m.strip()]
    return list(DEFAULT_FALLBACK_MODELS)


def generate_content_with_retry(client, model, contents, config=None, max_retries=4,
                                initial_delay=3, fallback_models=None, sleep=time.sleep):
    """Call Gemini with bounded retries and a model fallback chain.

    - 408/429/5xx and network errors: exponential backoff on the same model,
      then move to the next model.
    - 400/404 (bad request for this model, model retired): next model at once.
    - Anything else (401/403 auth, etc.): raise immediately - no other model
      will fix bad credentials.
    """
    if fallback_models is None:
        fallback_models = get_fallback_models()

    models_to_try = [model] + [m for m in fallback_models if m != model]
    kwargs = {"config": config} if config else {}

    last_exception = None
    for current_model in models_to_try:
        delay = initial_delay
        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=current_model, contents=contents, **kwargs
                )
                if current_model != model:
                    print(f"Successfully generated content using fallback model: {current_model}")
                return response
            except Exception as e:
                last_exception = e
                status = _error_status(e)
                print(f"Model {current_model} (attempt {attempt}/{max_retries}) failed "
                      f"[status={status}]: {e}")

                if status in SWITCH_MODEL_STATUS:
                    print(f"Switching from {current_model} to next fallback model...")
                    break
                if status is not None and status not in TRANSIENT_STATUS:
                    raise
                if attempt < max_retries:
                    print(f"Retrying {current_model} in {delay}s...")
                    sleep(delay)
                    delay = min(delay * 2, 30)

    raise last_exception


def make_client(api_key):
    # Structured output (JSON mode / response_schema) is only served on v1beta;
    # newer google-genai releases default to v1, which rejects it with a 400.
    api_version = get_env_var("GEMINI_API_VERSION") or "v1beta"
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version=api_version))


def _strip_code_fences(text):
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def parse_analysis(response):
    """Turn a Gemini response into a validated StrategicAnalysis."""
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, StrategicAnalysis):
        return parsed
    text = _strip_code_fences(response.text)
    try:
        return StrategicAnalysis.model_validate_json(text)
    except ValidationError:
        start = text.find("{")
        if start == -1:
            raise
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return StrategicAnalysis.model_validate(obj)


def _json_config():
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=StrategicAnalysis,
    )


def run_strategist(client, model, articles):
    print("Executing Macro Strategist (Noise Gate & Categorisation)...")
    
    prompt = f"""
You are the Macro Strategist for the Institutional Digital Asset Intelligence pipeline, calibrated for wholesale financial markets with a core focus on commercial banking (e.g. Lloyds Banking Group, Barclays, HSBC), corporate treasury, risk, capital markets, and financial market infrastructure (FMIs).
Your job is to apply a strict "Noise Gate" to the raw feed articles below and categorise the high-signal developments.

Strategic Focus & Weighting Directive:
- **Primary Geographic Balance:** Strongly weight developments across the UK, Europe (ECB, EU MiCA, Tier-1 European institutions), major US financial institutions, and premier global innovation hubs (Singapore MAS Project Guardian/GL1, Hong Kong HKMA Project Ensemble, Switzerland SDX). De-prioritise localized emerging-market retail pilots (e.g. India-specific retail crypto/CBDC) unless possessing systemic global cross-border market plumbing implications.
- **Bank-Led Digital Money & Institutional Rails:** Prioritise commercial bank-led digital money and regulated settlement rails (tokenised deposits, commercial bank money, Fnality, Kinexys, GBTD, Goldman Sachs DAP, Canton Network, SWIFT, Project Agorá, RLN).
- **Systemic Digital Asset & Treasury Players:** Welcome wholesale, corporate treasury, B2B cross-border, and commercial banking rails initiatives from major pure-play digital asset providers (e.g. Circle's USDC/Tazapay corporate rails, Ripple's RLUSD corporate treasury opportunity and institutional custody, Coinbase Institutional, regulated stablecoin issuers).
- **UK Public Sector & Central Banking Focus:**
  * Bank of England initiatives (Digital Securities Sandbox - DSS, RTGS synchronisation, wholesale settlement innovation).
  * HM Treasury digital asset and stablecoin policy developments.
  * UK Property (Digital Assets) Bill and associated legal/regulatory frameworks.
- **Frontier & Emerging Innovations:** Non-prescriptively capture any genuine technological innovation across the digital assets space (e.g. AI/agentic payments, programmable payments, zero-knowledge privacy layers, account abstraction, novel cryptography, and new smart contract or atomic settlement primitives). Do NOT filter out innovative digital asset news simply because it does not include a specific buzzword like ZKP.

Forbidden Content Attributes (Noise Gate - DISCARD IMMEDIATELY):
- **Non-Digital Asset Market Reforms:** General financial market reforms (e.g. FCA IPO listing reforms, general transaction reporting changes, handbook API updates) that do NOT have a direct, explicit connection to tokenisation, digital securities, or DLT market infrastructure.
- **Speculative & Purely Retail Crypto Noise:** Token spot price movements, daily gains/losses, technical chart indicators, retail exchange listings, retail trading volumes, consumer wallet apps, memecoins, NFTs, and speculative DeFi yield farming.

Allowed Content Attributes (High-Signal Pass):
- Banking Infrastructure & Commercial Rails: Commercial bank deposit tokens (GBP/USD/EUR), interbank settlement rails (Swift Digital Ledger, RLN, Project Agorá, Fnality, Kinexys), major pure-play treasury/corporate payment rails (Circle, Ripple RLUSD, regulated stablecoins), 24/7 intraday liquidity, wholesale payment rails.
- Capital Markets, Tokenised RWAs & Collateral Mobility: Sovereign bond tokenisation (UK Gilts, US Treasuries, Bunds), private credit, tokenised money market funds, tokenised commodities/gold, institutional collateral mobility, triparty repo optimization, regulated digital custody.
- Sovereign Infrastructure & CBDCs: Wholesale central bank digital currencies, central bank synchronisation models, omnibus accounts, BoE/FCA Digital Securities Sandbox (DSS), HM Treasury policy, EU MiCA enforcement timelines, US payment stablecoin frameworks, MAS/HKMA sandbox initiatives.
- Regulatory & Legal Frameworks: Global and jurisdictional legal structures directly governing digital assets, systemic stablecoins, and market infrastructure (BoE/FCA, HM Treasury, US Clarity Act, EU MiCA, MAS, HKMA).
- Frontier & Emerging Innovations: Genuine technological advancements in digital assets (agentic payments, programmable payments, privacy/ZK layers, smart contract financial logic, cross-chain messaging).
- Post-Trade Utilities & Interoperability: Delivery vs Payment (DvP), Payment vs Payment (PvP), atomic settlement mechanics, Euroclear/DTCC/Swift orchestration.

Core Pillars:
1. Banking Infrastructure & Commercial Rails
2. Institutional Asset Management & RWAs
3. Sovereign Infrastructure & CBDCs
4. Regulatory & Legal Frameworks
5. Frontier & Emerging Innovations (if applicable)

Write a custom synthesis sentence for each pillar explaining how these developments alter cross-border liquidity, commercial bank balance sheets, or capital efficiency.

Also synthesise the **Macro View**:
Provide 4-6 bold, declarative macro observations synthesising the systemic implications for bank balance sheets, liquidity, and wholesale market infrastructure.

Also analyse **Structural & Operational Pain Points** across:
- interoperability_silos: Where disparate networks, private ledgers, or stablecoin standards fail to bridge cleanly, creating fragmented liquidity pools.
- balance_sheet_and_liquidity_friction: Capital constraints, deposit disintermediation, parallel liquidity systems, or 24/7 liquidity buffer requirements under Basel III.
- post_trade_plumbing_constraints: Settlement bottlenecks, custodian friction, or legacy ledger synchronisation and batch processing limitations.

Also select **4-6 New High-Signal Targets for Tracking**:
Dynamic, week-specific standout entities, pilots, or legislative bills directly emerging from this week's news with URL and 1-2 sentence institutional rationale.

Output contract (the response schema is enforced; follow these content rules):
- "pillars" is a list; each entry's "name" must be one of the five Core Pillars above. Omit a pillar entirely if it has no qualifying developments.
- Every development "url" MUST be copied exactly from the "url" field of a raw feed article below. Never invent, shorten or alter URLs. If a development has no matching feed article, do not include it.
- Every development "source" must be the "source" field of that feed article; "title" should be the article title.
- For "new_high_signal_targets", reuse the feed article URL that introduced the target. If none exists, set "url" to an empty string.
- Do not wrap the JSON in markdown fences.

Raw feed articles:
{json.dumps(articles, indent=2)}
"""

    try:
        response = generate_content_with_retry(
            client=client, model=model, contents=prompt, config=_json_config()
        )
        return parse_analysis(response)
    except Exception as e:
        log_error(f"Macro Strategist API execution failed: {e}")
        return None

EDITOR_PROSE_RULES = """
1. Strict British English spelling (tokenised, tokenisation, utilised, prioritised, standardise, programmes, centre, synchronisation, optimisation).
2. No AI fluff or hedging: never use phrases such as "appears to", "it is evident that", "underscored by", "it is worth noting", "a testament to", "delve". State operational facts plainly.
3. Frame every point through institutional banking, treasury rails, balance-sheet liquidity, collateral mobility and market plumbing, for an audience of executives in systemic commercial banking (e.g. Lloyds Banking Group, Barclays, HSBC), corporate treasury, risk, capital markets and FMIs.
4. Macro view headlines are bold, declarative statements (no trailing full stop needed); details are 1-2 tight sentences.
5. Pillar syntheses are 1-2 sentences. Development details are one or two concise sentences on what happened and why it matters.
6. Targets carry a 1-2 sentence rationale for why banks, treasuries or FMIs should track them.
"""


def run_editor(client, model, strategic_analysis):
    """Polish prose in the analysis JSON. Layout is rendered deterministically later."""
    print("Executing Chief Editor & QC (prose polish)...")

    prompt = f"""
You are the Chief Editor for the Institutional Digital Asset Intelligence pipeline.
Rewrite the prose fields of the strategic analysis JSON below to publication standard, following these rules:
{EDITOR_PROSE_RULES}
Hard constraints:
- Return the SAME JSON structure with the SAME number of items in every list, in the SAME order.
- Do NOT change any "url", "title", "source", pillar "name" or target "name" value. Copy them exactly.
- Only rewrite: macro_view headline/detail, pillar synthesis, development details, structural_pain_points values, target rationale.

Strategic Analysis JSON:
{strategic_analysis.model_dump_json(indent=2)}
"""

    try:
        response = generate_content_with_retry(
            client=client, model=model, contents=prompt, config=_json_config()
        )
        edited = parse_analysis(response)
    except Exception as e:
        log_error(f"Chief Editor API execution failed: {e}. Using unedited strategist prose.")
        return strategic_analysis

    merged = merge_editor_prose(strategic_analysis, edited)
    if merged is None:
        print("WARNING: Editor changed the analysis structure; using unedited strategist prose.",
              file=sys.stderr)
        return strategic_analysis
    return merged


def merge_editor_prose(original, edited):
    """Take prose from ``edited`` but identity fields (urls, titles, names) from ``original``.

    Returns None if the editor altered the shape, so the caller can fall back.
    """
    if (len(original.macro_view) != len(edited.macro_view)
            or len(original.pillars) != len(edited.pillars)
            or len(original.new_high_signal_targets) != len(edited.new_high_signal_targets)):
        return None
    for o_p, e_p in zip(original.pillars, edited.pillars):
        if o_p.name != e_p.name or len(o_p.developments) != len(e_p.developments):
            return None

    result = original.model_copy(deep=True)
    for r, e in zip(result.macro_view, edited.macro_view):
        r.headline, r.detail = e.headline, e.detail
    for r_p, e_p in zip(result.pillars, edited.pillars):
        r_p.synthesis = e_p.synthesis
        for r_d, e_d in zip(r_p.developments, e_p.developments):
            r_d.details = e_d.details
    result.structural_pain_points = edited.structural_pain_points.model_copy()
    for r, e in zip(result.new_high_signal_targets, edited.new_high_signal_targets):
        r.rationale = e.rationale
    return result


def validate_and_normalize_links(markdown_content):
    """Final safety net: rewrite any non-absolute markdown link to a search URL."""
    import re
    from urllib.parse import quote_plus

    # Match markdown links: [text](url)
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    
    def replace_link(match):
        text = match.group(1)
        url = match.group(2).strip()
        
        # If it starts with http://, https://, or is an internal anchor starting with #, preserve it
        if url.startswith("http://") or url.startswith("https://") or url.startswith("#"):
            return match.group(0)
            
        # Otherwise, resolve it to an absolute Google Search URL as a fallback
        search_query = quote_plus(text)
        fallback_url = f"https://www.google.com/search?q={search_query}"
        print(f"WARNING: Normalizing relative/malformed link [{text}]({url}) to [{text}]({fallback_url})")
        return f"[{text}]({fallback_url})"
        
    return link_pattern.sub(replace_link, markdown_content)

def prune_processed_urls(processed, now=None, retention_days=STATE_RETENTION_DAYS):
    """Drop dedup entries older than the retention window.

    RSS feeds only expose recent items, so URLs older than a few months can no
    longer reappear; keeping them just grows the state file forever.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=retention_days)
    kept = {}
    for url, ts in processed.items():
        try:
            seen = datetime.datetime.fromisoformat(ts)
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=datetime.timezone.utc)
        except (TypeError, ValueError):
            kept[url] = ts  # keep anything we can't parse rather than re-publish it
            continue
        if seen >= cutoff:
            kept[url] = ts
    return kept


def update_system_state(raw_feed):
    state_path = os.path.join(WORKSPACE_ROOT, "system_state.json")
    state = {"processed_urls": {}}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load existing system state: {e}. Reinitializing.")
            state = {"processed_urls": {}}
    state.setdefault("processed_urls", {})

    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp = now.isoformat()
    for item in raw_feed:
        url = item.get("url")
        if url:
            state["processed_urls"][url] = timestamp

    before = len(state["processed_urls"])
    state["processed_urls"] = prune_processed_urls(state["processed_urls"], now=now)
    pruned = before - len(state["processed_urls"])

    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print(f"System state updated with {len(raw_feed)} new URLs "
              f"({pruned} expired entries pruned) and saved to {state_path}")
    except Exception as e:
        log_error(f"Failed to save system state: {e}")


def main():
    print("Pipeline orchestration run started...")
    
    # Ensure directories exist
    os.makedirs(os.path.join(WORKSPACE_ROOT, "shared_artifacts"), exist_ok=True)
    
    gemini_key = get_env_var("GEMINI_API_KEY")
    if not gemini_key:
        log_error("GEMINI_API_KEY environment variable is not set. Pipeline aborted.")
        sys.exit(1)
        
    client = make_client(gemini_key)
    gemini_model = get_env_var("GEMINI_MODEL") or DEFAULT_MODEL
    
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
        
    if ("--recompile" in sys.argv or "--force" in sys.argv) and os.path.exists(os.path.join(WORKSPACE_ROOT, "shared_artifacts", "raw_enriched_feed.json")):
        with open(os.path.join(WORKSPACE_ROOT, "shared_artifacts", "raw_enriched_feed.json"), "r", encoding="utf-8") as f:
            cached_data = json.load(f)
            cached_articles = cached_data.get("raw_articles", [])
            seen_urls = {a.get("url") for a in raw_feed if a.get("url")}
            for item in cached_articles:
                if item.get("url") and item.get("url") not in seen_urls:
                    raw_feed.append(item)
                    seen_urls.add(item.get("url"))
            print(f"Recompiling with {len(raw_feed)} total articles (merged fresh + cached)...")
    elif not raw_feed:
        print("No new articles discovered. Stopping pipeline.")
        sys.exit(0)
        
    print(f"Total articles for analysis: {len(raw_feed)}.")
    
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
        f.write(strategic_analysis.model_dump_json(indent=2))
    print(f"Strategic analysis successfully saved to {analysis_path}")

    # Step 3: Chief Editor polishes prose; layout and links are rendered deterministically
    edited_analysis = run_editor(client, gemini_model, strategic_analysis)
    allowed_urls = [a.get("url") for a in raw_feed if a.get("url")]
    briefing = finalise_briefing(edited_analysis, allowed_urls)
    briefing = validate_and_normalize_links(briefing)

    briefing_path = os.path.join(WORKSPACE_ROOT, "pipeline", "output_briefing.md")
    with open(briefing_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(f"Briefing successfully compiled to {briefing_path}")

    # Step 4: Run Publishing Layer
    print("Invoking Publishing layer...")
    publish_args = [sys.executable, os.path.join(WORKSPACE_ROOT, "pipeline", "publish.py")]
    if "--dry-run" in sys.argv:
        publish_args.append("--dry-run")
    try:
        subprocess.run(
            publish_args,
            check=True
        )
        print("Pipeline run completed successfully.")
        
        # Save state only if it was NOT a dry run
        if "--dry-run" not in sys.argv:
            update_system_state(raw_feed)
    except Exception as e:
        log_error(f"Publishing script failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

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
from enrich import evidence_for_prompt, gather_evidence
from feeds import source_quality
from render import (HEDGE_PHRASES, JARGON_SUGGESTIONS, MAX_HEADLINE_WORDS, MAX_WORDS, TARGET_WORDS,
                    brief_word_count, finalise_briefing, find_hedging, long_headlines, prose_text,
                    subject_line)
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


def _is_daily_quota(exc):
    """A per-day quota will not recover within our retry window, unlike per-minute limits."""
    text = str(exc).lower()
    return "perday" in text or "per day" in text


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

                if status == 429 and _is_daily_quota(e):
                    print(f"Daily quota exhausted for {current_model}; switching to next fallback model...")
                    break
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


MAX_OUTPUT_TOKENS = 32768
STRUCTURED_ATTEMPTS = 3


def _json_config():
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=StrategicAnalysis,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def _finish_reason(response):
    try:
        reason = response.candidates[0].finish_reason
        return getattr(reason, "name", None) or str(reason)
    except Exception:
        return None


def generate_analysis(client, model, prompt, label, attempts=STRUCTURED_ATTEMPTS):
    """Generate and validate a StrategicAnalysis, re-asking on truncated/invalid JSON.

    Transport-level retries live in generate_content_with_retry; this loop handles
    the case where the API call succeeds but the payload is cut off or malformed.
    """
    last_error = None
    for attempt in range(1, attempts + 1):
        response = generate_content_with_retry(
            client=client, model=model, contents=prompt, config=_json_config()
        )
        try:
            return parse_analysis(response)
        except (ValueError, ValidationError) as e:  # JSONDecodeError is a ValueError
            last_error = e
            print(f"WARNING: {label} returned unusable JSON (attempt {attempt}/{attempts}, "
                  f"finish_reason={_finish_reason(response)}, "
                  f"length={len(getattr(response, 'text', '') or '')} chars): {e}", file=sys.stderr)
    raise last_error


def index_articles(raw_feed):
    """Assign short ids; return (prompt_articles, id -> article)."""
    by_id, prompt_articles = {}, []
    for i, article in enumerate(raw_feed, start=1):
        aid = f"a{i}"
        by_id[aid] = article
        item = {"id": aid, "title": article.get("title", ""), "source": article.get("source", ""),
                "quality": source_quality(article.get("source", ""))}
        if article.get("published"):
            item["published"] = article["published"][:10]
        if article.get("content"):
            item["content"] = article["content"]
        prompt_articles.append(item)
    return prompt_articles, by_id


def resolve_article_refs(analysis, by_id):
    """Fill title/source/url from the cited feed article; drop developments citing unknown ids."""
    for pillar in analysis.pillars:
        kept = []
        for dev in pillar.developments:
            article = by_id.get(dev.article_id.strip())
            if article is None:
                print(f"WARNING: development '{dev.title or dev.details[:60]}' cites unknown article id "
                      f"{dev.article_id!r}; dropped", file=sys.stderr)
                continue
            dev.title = article.get("title") or dev.title
            dev.source = article.get("source") or dev.source
            dev.url = article.get("url", "")
            kept.append(dev)
        pillar.developments = kept
    for target in analysis.new_high_signal_targets:
        article = by_id.get(target.article_id.strip())
        target.url = article.get("url", "") if article else ""
    return analysis


def run_strategist(client, model, articles):
    print("Executing Macro Strategist (Noise Gate & Categorisation)...")
    articles, by_id = index_articles(articles)
    
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

Core Pillars (file each development under the ONE pillar that fits best):
1. Banking Infrastructure & Commercial Rails: banks' and payment firms' deposit tokens, stablecoins issued or accepted by banks, payment networks (Kinexys, Partior, Swift payments), corporate treasury payments.
2. Institutional Asset Management & RWAs: tokenised funds, bonds, equities and collateral; custody; market infrastructure operators (DTCC, Euroclear, Clearstream, exchanges, CSDs, CCPs) tokenising or settling securities - even when they use new technology.
3. Sovereign Infrastructure & CBDCs: central bank projects and trials (Agorá, Meridian, Ensemble, Pontes, wholesale CBDC, RTGS synchronisation, central bank DLT bonds).
4. Regulatory & Legal Frameworks: rules, consultations, laws, supervisory statements and standards bodies - including central bank or regulator consultations (e.g. a Bank of England consultation is Regulatory, not Asset Management).
5. Frontier & Emerging Innovations: genuinely new technology with a clear digital-asset or payments use (privacy layers, interoperability protocols, agentic payments). Not market infrastructure operators, and not general AI or research tools.

Audience and UK focus:
- Readers are UK corporate and commercial bankers (e.g. Lloyds Banking Group, Barclays, HSBC, NatWest). Put the UK first: Bank of England, FCA, HM Treasury, UK banks and UK firms, UK law and UK market infrastructure.
- Set "uk": true on any development that directly concerns the UK. Always include significant UK developments.
- International items earn a place by what they mean for UK banks: competitor moves (US, EU and Asian banks), standards and rules UK firms must meet or will be compared with, and infrastructure UK banks connect to.

Selection discipline (this is a five-minute executive brief of about 800 words, not a news digest):
- Select AT MOST 12 developments in total, the most significant first, with at most 4 per pillar. Fewer is better than padding.
- Each development must be a distinct event. When several articles cover the same event, cite ONE: prefer "quality": "primary" (central banks, regulators, official press releases), then "trade" (established financial trade press), and only use "aggregator" sources when nothing better covers the event.
- Exclude anything not about digital assets, tokenisation, stablecoins, CBDCs or DLT-based payments and settlement (e.g. general AI research, generic fintech, crypto prices).
- Keep every "details" to at most two sentences.

Also write:
- "macro_view" (shown as "In one minute"): EXACTLY 3 bullets. Each headline is one specific claim about this week (at most 12 words, sentence case); each detail is ONE short sentence on why it matters to a UK bank. Together they should let a reader skip the rest of the brief.
- "uk_implications" (shown as "What it means for UK banks"): 2-3 short, concrete sentences on what this week's news means for UK banks - competitive pressure, regulatory benchmarks, decisions or preparation needed. Name the developments; no generic statements that would be true any week.
- "new_high_signal_targets" (shown as "Worth watching"): up to 3 programmes, firms or upcoming decisions worth tracking that are NOT already among the selected developments (e.g. a consultation deadline, a launch due soon). Leave empty rather than repeat a development.
- "subject_hook": the week's top one or two stories in at most 10 words for the email subject (e.g. "DBS-JPMorgan 24/7 dollar link; OCC stablecoin deadline").
- "synthesis" for each pillar may be a short phrase; it is not shown to readers.

Output contract (the response schema is enforced; follow these content rules):
- "pillars" is a list; each entry's "name" must be one of the five Core Pillars above. Omit a pillar entirely if it has no qualifying developments.
- Each raw feed article has a short "id" (e.g. "a17"). Every development MUST set "article_id" to the id of the article it is based on; when several articles cover the same event, use the most authoritative one. Leave "title", "source" and "url" empty: they are filled in from the feed automatically. Never cite an id that is not in the list below.
- For "new_high_signal_targets", set "article_id" to the article that introduced the target (or an empty string if none) and leave "url" empty.
- Leave "label", "stale" and "exclude" at their defaults; the editor sets them.
- Do not wrap the JSON in markdown fences.

Raw feed articles:
{json.dumps(articles, ensure_ascii=False, separators=(",", ":"))}
"""

    try:
        analysis = generate_analysis(client, model, prompt, "Macro Strategist")
        return resolve_article_refs(analysis, by_id)
    except Exception as e:
        log_error(f"Macro Strategist API execution failed: {e}")
        return None

EDITOR_PROSE_RULES = f"""
Voice: write like a well-edited newspaper brief for a busy senior UK banker. Plain English, short sentences (aim for under 20 words), active voice, one idea per sentence. Domain terms that carry meaning (tokenised deposit, stablecoin, repo, payment-versus-payment) are fine; spell out less-known acronyms on first use (e.g. "Depository Trust & Clearing Corporation (DTCC)"), but not ECB, BIS, FCA, US, UK, EU. No corporate jargon. The whole brief should read in about five minutes (roughly 800 words).

1. Strict British English spelling (tokenised, tokenisation, prioritised, standardise, programmes, centre, synchronisation).
2. Development "details": open with the concrete fact - who did what, with numbers, dates, currencies, counterparties or jurisdictions from the evidence. Add a second short sentence ONLY if it tells a banker something concrete; otherwise stop. Never end with a tacked-on clause such as ", affecting X" or ", enabling Y". No generic benefit claims.
3. Development "label": the link text readers see. Write a short, plain-English label of at most 10 words in British spelling that says what happened (e.g. "DBS and JPMorgan link deposit tokens for 24/7 dollar payments"). Not the original headline, no questions, no clickbait, no publisher name.
4. Never overclaim. Implications must be no stronger than the evidence: a trial "shows" or "could reduce", it does not "prove" or "eliminate". Say "plans to", "is consulting on" or "is testing" when that is what happened.
5. "macro_view" ("In one minute"): 3 bullets. Headline: one specific claim about this week, sentence case, at most 12 words. Detail: ONE short sentence on why it matters to a UK bank. Do not list developments; no headline may be true of any week.
6. "uk_implications" ("What it means for UK banks"): 2-3 short, concrete sentences naming this week's developments and what UK banks should note, decide or prepare for. No generic statements.
7. Target rationales: one sentence on why to track it and what to watch for next (a date, decision or launch).
8. "subject_hook": the top one or two stories in at most 10 words, no full stop.
9. Never mention article ids (such as a17) anywhere in the prose; refer to institutions and events by name.
10. Banned words and phrases (never use them, in any inflection): {", ".join(HEDGE_PHRASES)}.
"""

EVIDENCE_RULES = """
Factual grounding (most important rule):
- The "Evidence" block gives, for each article_id, the headline, publisher and an excerpt of the article.
- A development's "details" may ONLY state facts supported by its own article's headline or excerpt. Remove any claim in the current draft that the evidence does not support (for example an inferred programme, sandbox, amount, date or partner).
- In One minute, UK implications and target rationales, rely only on facts present in the developments' evidence.

Thin or off-topic items:
- Set "exclude" to true when a development would only restate its headline because the evidence gives no further detail, UNLESS it is a UK development (keep UK items, stating only what the headline supports).
- Set "exclude" to true for anything not about digital assets, tokenisation, stablecoins, CBDCs or DLT-based payments and settlement (e.g. general AI or econometrics research).

Freshness:
- Set a development's "stale" to true when its evidence shows the core event happened more than 30 days before the brief date AND the article reports nothing new about it (e.g. a fund that launched months ago, re-reported this week). Otherwise leave "stale" false.
- Do not rely on stale or excluded developments anywhere else in the brief.
"""


def _editor_prompt(strategic_analysis, evidence_block, extra=""):
    return f"""
You are the Chief Editor for the Institutional Digital Asset Intelligence pipeline.
Brief date: {datetime.date.today().isoformat()}.
Rewrite the prose fields of the strategic analysis JSON below to publication standard.
{EVIDENCE_RULES}
Style rules:
{EDITOR_PROSE_RULES}
Hard constraints:
- Return the SAME JSON structure with the SAME number of items in every list, in the SAME order.
- Do NOT change any "article_id", "url", "title", "source", pillar "name" or target "name" value. Copy them exactly.
- Only rewrite: macro_view headline/detail, uk_implications, development details, label, stale and exclude flags, target rationale, subject_hook. "uk_implications" may have 2-3 entries; every other list keeps its length.
{extra}
Evidence:
{json.dumps(evidence_block, ensure_ascii=False, separators=(",", ":"))}

Strategic Analysis JSON:
{strategic_analysis.model_dump_json()}
"""


def run_editor(client, model, strategic_analysis, evidence_block=None, max_revisions=2):
    """Ground and polish prose in the analysis JSON. Layout is rendered deterministically later.

    If banned phrases survive the first pass, the editor is asked once more to
    remove them, naming the offending phrases.
    """
    print("Executing Chief Editor & QC (fact-check and prose polish)...")
    evidence_block = evidence_block or {}

    current, extra = strategic_analysis, ""
    for revision in range(max_revisions + 1):
        try:
            edited = generate_analysis(client, model, _editor_prompt(current, evidence_block, extra),
                                       "Chief Editor")
        except Exception as e:
            log_error(f"Chief Editor API execution failed: {e}. Using previous draft.")
            return current

        merged = merge_editor_prose(strategic_analysis, edited)
        if merged is None:
            print("WARNING: Editor changed the analysis structure; using previous draft.", file=sys.stderr)
            return current
        current = merged

        offending = find_hedging(prose_text(current))
        too_long = long_headlines(current)
        words = brief_word_count(current)
        too_wordy = words > MAX_WORDS
        if not offending and not too_long and not too_wordy:
            return current
        extra = "\nRevision request:"
        if offending:
            print(f"WARNING: editor draft {revision + 1} still uses banned phrases: {', '.join(offending)}",
                  file=sys.stderr)
            hints = "; ".join(f'"{p}" -> {JARGON_SUGGESTIONS[p]}' for p in offending if p in JARGON_SUGGESTIONS)
            extra += (" the previous draft (below) still used these banned phrases: " + ", ".join(offending)
                      + ". Rewrite every sentence containing them in plain, specific English."
                      + (f" Suggested replacements: {hints}." if hints else ""))
        if too_wordy:
            print(f"WARNING: editor draft {revision + 1} renders to {words} words (limit {MAX_WORDS})",
                  file=sys.stderr)
            extra += (f" The brief renders to {words} words; cut it to about {TARGET_WORDS}. Shorten details to "
                      "one sentence where possible and set \"exclude\": true on the least important non-UK items.")
        if too_long:
            print(f"WARNING: editor draft {revision + 1} has {len(too_long)} macro headline(s) over "
                  f"{MAX_HEADLINE_WORDS} words", file=sys.stderr)
            extra += (f" These macro view headlines exceed {MAX_HEADLINE_WORDS} words; shorten each to at most "
                      f"{MAX_HEADLINE_WORDS} words in sentence case: " + " | ".join(too_long) + ".")
        extra += "\n"
    return current


def merge_editor_prose(original, edited):
    """Take prose from ``edited`` but identity fields (urls, titles, names, uk) from ``original``.

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
    if edited.uk_implications:
        result.uk_implications = list(edited.uk_implications)
    for r_p, e_p in zip(result.pillars, edited.pillars):
        r_p.synthesis = e_p.synthesis
        for r_d, e_d in zip(r_p.developments, e_p.developments):
            r_d.details = e_d.details
            r_d.label = e_d.label
            r_d.stale = e_d.stale
            r_d.exclude = e_d.exclude
    for r, e in zip(result.new_high_signal_targets, edited.new_high_signal_targets):
        r.rationale = e.rationale
    if edited.subject_hook:
        result.subject_hook = edited.subject_hook
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

    # Step 3: gather evidence for the selected articles (publisher URLs + excerpts)
    _, by_id = index_articles(raw_feed)
    resolved_urls = []
    evidence = {}
    try:
        evidence, resolved_urls = gather_evidence(strategic_analysis, by_id)
    except Exception as e:
        print(f"WARNING: evidence gathering failed ({e}); editor will rely on headlines only",
              file=sys.stderr)
    evidence_block = evidence_for_prompt(strategic_analysis, by_id, evidence)

    # Step 4: Chief Editor fact-checks and polishes prose; layout and links are rendered in code
    edited_analysis = run_editor(client, gemini_model, strategic_analysis, evidence_block)
    allowed_urls = [a.get("url") for a in raw_feed if a.get("url")] + resolved_urls
    briefing = finalise_briefing(edited_analysis, allowed_urls)
    briefing = validate_and_normalize_links(briefing)

    briefing_path = os.path.join(WORKSPACE_ROOT, "pipeline", "output_briefing.md")
    with open(briefing_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(f"Briefing successfully compiled to {briefing_path}")

    # Short top-story phrase for the email subject (read by publish.py).
    subject_path = os.path.join(WORKSPACE_ROOT, "shared_artifacts", "email_subject.txt")
    with open(subject_path, "w", encoding="utf-8") as f:
        f.write(subject_line(edited_analysis))

    # Step 5: Run Publishing Layer
    print("Invoking Publishing layer...")
    dry_run = "--dry-run" in sys.argv
    publish_args = [sys.executable, os.path.join(WORKSPACE_ROOT, "pipeline", "publish.py")]
    if dry_run:
        publish_args.append("--dry-run")
    result_path = os.path.join(WORKSPACE_ROOT, "shared_artifacts", "publish_result.json")
    if os.path.exists(result_path):
        os.remove(result_path)
    proc = subprocess.run(publish_args)
    result = read_publish_result(result_path)

    exit_code = finalise_run(result, proc.returncode, raw_feed, dry_run)
    sys.exit(exit_code)


def read_publish_result(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def finalise_run(result, publish_returncode, raw_feed, dry_run):
    """Decide state update and exit code from per-channel publish outcomes.

    - If the brief reached ANY channel, record the articles as processed so
      next week's run does not repeat them (even if another channel failed).
    - If ANY channel failed, exit non-zero so the failure is visible/notified.
    """
    delivered = [ch for ch, status in result.items() if status == "ok"]
    failed = [ch for ch, status in result.items() if status == "failed"]
    if not result and publish_returncode != 0:
        failed = ["publisher"]

    if not dry_run and delivered:
        update_system_state(raw_feed)
    elif not dry_run:
        print("Brief was not delivered to any channel; system state left unchanged "
              "so the same articles are retried next run.")

    if failed:
        log_error(f"Publishing failed for: {', '.join(failed)} "
                  f"(delivered: {', '.join(delivered) or 'none'})")
        return 1
    print(f"Pipeline run completed successfully. Channels: {result}")
    return 0


if __name__ == '__main__':
    main()

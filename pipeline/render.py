"""Deterministic briefing rendering and QC.

The LLM produces structured JSON only; this module owns the Markdown layout,
so headers, section order and links are guaranteed rather than requested.
"""
import re
import sys
from typing import Iterable, List, Set
from urllib.parse import quote_plus

from schema import PILLAR_ORDER, PillarName, StrategicAnalysis

SEARCH_FALLBACK = "https://www.google.com/search?q="


# ---------------------------------------------------------------------------
# Link integrity
# ---------------------------------------------------------------------------

def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def search_url(text: str) -> str:
    return SEARCH_FALLBACK + quote_plus(text)


def enforce_link_allowlist(analysis: StrategicAnalysis, allowed_urls: Iterable[str]) -> List[str]:
    """Replace any URL that did not come from the ingested feed with a search link.

    Mutates ``analysis`` in place and returns a list of human-readable warnings.
    This stops hallucinated-but-plausible URLs (e.g. a made-up bis.org path)
    from reaching the email or the website.
    """
    allowed: Set[str] = {_norm_url(u) for u in allowed_urls if u}
    warnings = []

    def check(url: str, label: str) -> str:
        if _norm_url(url) in allowed or (url or "").startswith(SEARCH_FALLBACK):
            return url
        fallback = search_url(label)
        warnings.append(f"Untrusted link for '{label}' ({url!r}) replaced with search fallback")
        return fallback

    for pillar in analysis.pillars:
        for dev in pillar.developments:
            dev.url = check(dev.url, dev.title)
    for target in analysis.new_high_signal_targets:
        target.url = check(target.url, target.name)
    return warnings


# ---------------------------------------------------------------------------
# British English QC
# ---------------------------------------------------------------------------

# Words that legitimately end in -ize / -yze in British English.
_IZE_EXCEPTIONS = {
    "size", "sizes", "sized", "sizing", "resize", "resized", "resizing",
    "downsize", "downsized", "downsizing", "upsize", "oversize", "oversized",
    "undersized", "outsize", "outsized", "capsize", "capsized", "prize", "prizes",
    "prized", "seize", "seizes", "seized", "seizing", "maize", "baize", "assize",
    "pfizer",
}

_AMERICANISM = re.compile(r"\b([A-Za-z]+?)(i|y)z(e|es|ed|er|ers|ing|ation|ations|ational)\b", re.IGNORECASE)

# Hedging and generic filler that adds no information for an executive reader.
HEDGE_PHRASES = [
    "it is evident that", "appears to", "underscored by", "underscores", "it is worth noting",
    "it's worth noting", "in today's", "rapidly evolving", "ever-evolving", "delve", "a testament to",
    "navigating the landscape", "landscape", "game-changer", "game changer",
    "this signals", "signals a shift", "this signifies", "signifies", "this demonstrates",
    "this represents", "represents a significant", "significant step", "a major step",
    "pave the way", "paves the way", "paving the way", "crucial", "pivotal", "poised to",
    "could potentially", "has the potential to", "the potential to", "unlock", "unlocks",
    "seamless", "seamlessly", "streamline", "streamlines", "foster", "fosters", "fostering",
    "robust", "cutting-edge", "transformative", "revolutionise", "revolutionize",
    "ushers in", "a new era", "the future of", "showcases", "highlights the importance",
    "holds importance", "these developments indicate", "these actions aim", "these efforts aim",
    "aims to enhance", "aim to enhance", "strategic move", "notable", "plays a key role",
    "key role", "in the digital asset space", "new approaches",
]


def to_british(text: str) -> str:
    """Convert -ize/-yze spellings (and derivatives) to -ise/-yse."""
    def fix(match):
        word = match.group(0)
        if word.lower() in _IZE_EXCEPTIONS:
            return word
        stem, vowel, suffix = match.group(1), match.group(2), match.group(3)
        z = "S" if match.group(0)[len(stem) + 1] == "Z" else "s"
        return f"{stem}{vowel}{z}{suffix}"
    return _AMERICANISM.sub(fix, text)


def _map_prose(analysis: StrategicAnalysis, fn) -> None:
    for point in analysis.macro_view:
        point.headline, point.detail = fn(point.headline), fn(point.detail)
    for pillar in analysis.pillars:
        pillar.synthesis = fn(pillar.synthesis)
        for dev in pillar.developments:
            dev.details = fn(dev.details)
    pp = analysis.structural_pain_points
    pp.interoperability_silos = fn(pp.interoperability_silos)
    pp.balance_sheet_and_liquidity_friction = fn(pp.balance_sheet_and_liquidity_friction)
    pp.post_trade_plumbing_constraints = fn(pp.post_trade_plumbing_constraints)
    for target in analysis.new_high_signal_targets:
        target.rationale = fn(target.rationale)


def apply_british_english(analysis: StrategicAnalysis) -> None:
    """Normalise spelling in prose fields only.

    Source titles and entity names are left verbatim: they are quotations of
    third-party headlines and proper nouns (e.g. a US "Tokenization Act").
    """
    for point in analysis.macro_view:
        point.headline = to_british(point.headline)
        point.detail = to_british(point.detail)
    for pillar in analysis.pillars:
        pillar.synthesis = to_british(pillar.synthesis)
        for dev in pillar.developments:
            dev.details = to_british(dev.details)
    pp = analysis.structural_pain_points
    pp.interoperability_silos = to_british(pp.interoperability_silos)
    pp.balance_sheet_and_liquidity_friction = to_british(pp.balance_sheet_and_liquidity_friction)
    pp.post_trade_plumbing_constraints = to_british(pp.post_trade_plumbing_constraints)
    for target in analysis.new_high_signal_targets:
        target.rationale = to_british(target.rationale)


# Corporate jargon: replace with plain words (suggestions are given to the editor).
JARGON_SUGGESTIONS = {
    "utilise": "use", "utilises": "uses", "utilised": "used", "utilising": "using",
    "leverage": "use", "leverages": "uses", "leveraging": "using",
    "facilitate": "allow / help", "facilitates": "allows / helps", "facilitating": "allowing",
    "enhance": "improve", "enhances": "improves", "enhanced": "improved", "enhancing": "improving",
    "optimise": "improve", "optimises": "improves", "optimising": "improving",
    "synergy": "(cut)", "synergies": "(cut)", "paradigm": "model", "holistic": "(cut)",
    "ecosystem": "market / network", "stakeholders": "banks / firms (name them)",
    "going forward": "(cut)", "best-in-class": "(cut)", "value proposition": "benefit",
    "operationalise": "put into practice", "capabilities": "(say what it can do)",
    "solution": "product / service / system", "solutions": "products / services",
    "foundational": "core", "proliferation": "growth", "necessitate": "require",
    "necessitates": "requires", "impacting": "affecting", "inaugural": "first",
    "concurrently": "at the same time", "in order to": "to", "a range of": "several",
    # Payments-insider shorthand: fine for specialists, opaque for a wider executive audience.
    "nostro": "accounts banks pre-fund abroad", "vostro": "accounts held for foreign banks",
    "earmark": "set aside", "earmarks": "sets aside", "earmarked": "set aside",
    "earmarking": "setting aside", "rails": "networks / systems", "plumbing": "infrastructure",
    "second-level": "in seconds", "multi-chain": "on several blockchains",
    ", affecting": "(end the sentence, or say concretely what changes)",
    ", enabling": "(end the sentence, or say concretely what changes)",
    ", impacting": "(end the sentence, or say concretely what changes)",
}
HEDGE_PHRASES += [j for j in JARGON_SUGGESTIONS if j not in HEDGE_PHRASES]

# Exact one-for-one swaps that are always safe to apply deterministically.
_SAFE_SWAPS = {
    "utilise": "use", "utilises": "uses", "utilised": "used", "utilising": "using",
    "inaugural": "first", "concurrently": "at the same time", "in order to": "to",
}


def plain_english(text: str) -> str:
    def swap(match):
        word = match.group(0)
        repl = _SAFE_SWAPS[word.lower()]
        return repl[0].upper() + repl[1:] if word[0].isupper() else repl
    pattern = r"\b(" + "|".join(re.escape(w) for w in _SAFE_SWAPS) + r")\b"
    return re.sub(pattern, swap, text, flags=re.IGNORECASE)


_HEDGE_RE = [(p, re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE)) for p in HEDGE_PHRASES]


# ---------------------------------------------------------------------------
# Headline QC: sentence case, at most MAX_HEADLINE_WORDS words
# ---------------------------------------------------------------------------

MAX_HEADLINE_WORDS = 12
_SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with", "&"}


def _is_title_case(headline: str) -> bool:
    words = [w for w in headline.split() if w.lower() not in _SMALL_WORDS and w[:1].isalpha()]
    if len(words) < 3:
        return False
    capitalised = sum(1 for w in words[1:] if w[0].isupper())
    return capitalised / max(len(words) - 1, 1) >= 0.6


def to_sentence_case(headline: str, reference_text: str) -> str:
    """Lower-case Title Case headline words that are ordinary words elsewhere in the brief.

    Proper nouns are kept: a word stays capitalised if it is an acronym or
    mixed-case (DBS, JPMorgan), if the capitalised phrase it belongs to appears
    verbatim in the body (Bank of England, Project Faro), or if the word never
    appears in lower case in the body.
    """
    if not _is_title_case(headline):
        return headline
    lowercase_words = set(re.findall(r"\b[a-z][a-z]*\b", reference_text))
    # Words written capitalised mid-sentence in the body are likely proper nouns.
    midsentence_caps = set(re.findall(r"(?<=[a-z0-9,] )([A-Z][a-z]+)", reference_text))
    tokens = headline.split(" ")
    # Capitalised runs (allowing 'of', '&', 'and' inside) that appear verbatim in the body.
    protected = set()
    i = 0
    while i < len(tokens):
        if tokens[i][:1].isupper():
            j = i
            while j + 1 < len(tokens) and (tokens[j + 1][:1].isupper()
                                           or tokens[j + 1] in ("of", "&", "and")):
                j += 1
            for start in range(i, j + 1):
                for end in range(j, start, -1):
                    phrase = " ".join(tokens[start:end + 1]).strip(".,:;")
                    if re.search(r"(?<![A-Za-z])" + re.escape(phrase) + r"(?![A-Za-z])", reference_text):
                        protected.update(range(start, end + 1))
                        break
            i = j + 1
        else:
            i += 1

    def is_proper(part):
        if not part[:1].isupper():
            return True  # already lower case / number: leave as is
        if part.isupper() or any(c.isupper() for c in part[1:]):  # DBS, FX, JPMorgan
            return True
        low = part.lower()
        seen_lower = {low, low + "s", low.rstrip("s")} & lowercase_words
        return part in midsentence_caps and not seen_lower

    out = []
    for idx, tok in enumerate(tokens):
        if idx == 0 or idx in protected:
            out.append(tok)
            continue
        m = re.match(r"^(\W*)(.*?)(\W*)$", tok)
        lead, core, trail = m.group(1), m.group(2), m.group(3)
        parts = core.split("-")
        parts = [p if is_proper(p) else p.lower() for p in parts]
        out.append(lead + "-".join(parts) + trail)
    return " ".join(out)


def apply_sentence_case_headlines(analysis: StrategicAnalysis) -> None:
    reference = prose_text(analysis)
    for point in analysis.macro_view:
        point.headline = to_sentence_case(point.headline, reference)


def long_headlines(analysis: StrategicAnalysis) -> List[str]:
    return [p.headline for p in analysis.macro_view
            if len(p.headline.split()) > MAX_HEADLINE_WORDS]


def find_hedging(text: str) -> List[str]:
    return [p for p, rx in _HEDGE_RE if rx.search(text)]


def prose_text(analysis: StrategicAnalysis) -> str:
    """All model-written prose (not titles or names), for QC checks."""
    parts = []
    for point in analysis.macro_view:
        parts += [point.headline, point.detail]
    for pillar in analysis.pillars:
        parts.append(pillar.synthesis)
        parts += [dev.details for dev in pillar.developments]
    pp = analysis.structural_pain_points
    parts += [pp.interoperability_silos, pp.balance_sheet_and_liquidity_friction,
              pp.post_trade_plumbing_constraints]
    parts += [t.rationale for t in analysis.new_high_signal_targets]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _link_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").strip()


def _link_url(url: str) -> str:
    return url.strip().replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def _link(text: str, url: str, bold: bool = False) -> str:
    label = _link_text(text)
    if bold:
        label = f"**{label}**"
    return f"[{label}]({_link_url(url)})"


# Internal article ids (a17) must never reach readers, e.g. "(a128)" or "(a2, a49)".
_ARTICLE_ID_RE = re.compile(r"\s*[\(\[]\s*(?:articles?(?:[_ ]ids?)?:?\s*)?a\d+(?:(?:\s*[,;/&]\s*(?:and\s+)?|\s+and\s+)a\d+)*\s*[\)\]]")


def strip_article_ids(text: str) -> str:
    text = _ARTICLE_ID_RE.sub("", text or "")
    return re.sub(r"\s+([.,;:])", r"\1", text)


def _oneline(text: str) -> str:
    return " ".join(strip_article_ids(text).split())


# Reader-facing titles. The schema/prompt names stay stable; only the display changes.
SECTION_TITLES = {
    "macro": "The week in brief",
    "pillars": "What happened",
    "pain_points": "What is holding things back",
    "targets": "Worth watching",
}
PILLAR_TITLES = {
    PillarName.BANKING: "Banks and payments",
    PillarName.ASSET_MANAGEMENT: "Funds and tokenised assets",
    PillarName.SOVEREIGN: "Central banks and public infrastructure",
    PillarName.REGULATORY: "Regulation and law",
    PillarName.FRONTIER: "New technology",
}
PAIN_POINT_LABELS = {
    "interop": "Separate networks that don't connect",
    "liquidity": "Liquidity and balance sheets",
    "post_trade": "Settlement and post-trade",
}


def render_briefing(analysis: StrategicAnalysis) -> str:
    lines: List[str] = []

    lines.append(f"## {SECTION_TITLES['macro']}")
    for point in analysis.macro_view:
        headline = _oneline(point.headline).strip("* ")
        if headline and headline[-1] not in ".!?:":
            headline += "."
        lines.append(f"* **{headline}** {_oneline(point.detail)}")
    lines.append("")

    lines.append(f"## {SECTION_TITLES['pillars']}")
    lines.append("")
    by_name = {}
    for pillar in analysis.pillars:
        # Merge duplicates defensively if the model repeats a pillar.
        existing = by_name.get(pillar.name)
        if existing:
            existing.developments.extend(pillar.developments)
        else:
            by_name[pillar.name] = pillar.model_copy(deep=True)

    for name in PILLAR_ORDER:
        pillar = by_name.get(name)
        if pillar:
            pillar.developments = [d for d in pillar.developments if not d.stale]
        if not pillar or not pillar.developments:
            continue
        lines.append(f"### {PILLAR_TITLES.get(name, name.value)}")
        if pillar.synthesis.strip():
            lines.append(_oneline(pillar.synthesis).strip("* "))
        lines.append("")
        for dev in pillar.developments:
            source = _oneline(dev.source)
            attribution = f" *({source})*" if source and source.lower() not in dev.title.lower() else ""
            lines.append(f"* {_link(dev.title, dev.url)}{attribution}: {_oneline(dev.details)}")
        lines.append("")

    pp = analysis.structural_pain_points
    lines.append(f"## {SECTION_TITLES['pain_points']}")
    lines.append(f"* **{PAIN_POINT_LABELS['interop']}:** {_oneline(pp.interoperability_silos)}")
    lines.append(f"* **{PAIN_POINT_LABELS['liquidity']}:** {_oneline(pp.balance_sheet_and_liquidity_friction)}")
    lines.append(f"* **{PAIN_POINT_LABELS['post_trade']}:** {_oneline(pp.post_trade_plumbing_constraints)}")
    lines.append("")

    lines.append(f"## {SECTION_TITLES['targets']}")
    for target in analysis.new_high_signal_targets:
        lines.append(f"* {_link(target.name, target.url, bold=True)}: {_oneline(target.rationale)}")
    lines.append("")

    return "\n".join(lines)


def finalise_briefing(analysis: StrategicAnalysis, allowed_urls: Iterable[str]) -> str:
    """Run all QC steps and render. Mutates ``analysis``."""
    for pillar in analysis.pillars:
        for dev in pillar.developments:
            if dev.stale:
                print(f"WARNING: dropping stale development '{dev.title}' (event predates this week)",
                      file=sys.stderr)
    for warning in enforce_link_allowlist(analysis, allowed_urls):
        print(f"WARNING: {warning}", file=sys.stderr)
    apply_british_english(analysis)
    _map_prose(analysis, plain_english)
    apply_sentence_case_headlines(analysis)
    markdown_text = render_briefing(analysis)
    hedges = find_hedging(prose_text(analysis))
    if hedges:
        print(f"WARNING: QC hedging phrases present: {', '.join(hedges)}", file=sys.stderr)
    return markdown_text


__all__ = [
    "PillarName", "enforce_link_allowlist", "to_british", "apply_british_english",
    "find_hedging", "render_briefing", "finalise_briefing", "search_url",
]

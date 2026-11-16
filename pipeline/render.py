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

HEDGE_PHRASES = [
    "it is evident that", "appears to", "underscored by", "it is worth noting",
    "it's worth noting", "in today's rapidly evolving", "delve", "a testament to",
    "navigating the landscape", "game-changer", "game changer",
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


def find_hedging(markdown_text: str) -> List[str]:
    lowered = markdown_text.lower()
    return [p for p in HEDGE_PHRASES if p in lowered]


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


def _oneline(text: str) -> str:
    return " ".join((text or "").split())


def render_briefing(analysis: StrategicAnalysis) -> str:
    lines: List[str] = []

    lines.append("## 1. MACRO VIEW")
    for point in analysis.macro_view:
        headline = _oneline(point.headline).strip("* ")
        lines.append(f"* **{headline}** {_oneline(point.detail)}")
    lines.append("")

    lines.append("## 2. CORE PILLAR DEVELOPMENTS")
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
        if not pillar or not pillar.developments:
            continue
        lines.append(f"### {name.value}")
        if pillar.synthesis.strip():
            lines.append(f"*{_oneline(pillar.synthesis).strip('* ')}*")
        lines.append("")
        for dev in pillar.developments:
            lines.append(f"* {_link(dev.title, dev.url)}: {_oneline(dev.details)}")
        lines.append("")

    pp = analysis.structural_pain_points
    lines.append("## 3. STRUCTURAL & OPERATIONAL PAIN POINTS")
    lines.append(f"* **Interoperability Silos:** {_oneline(pp.interoperability_silos)}")
    lines.append(f"* **Balance Sheet & Liquidity Friction:** {_oneline(pp.balance_sheet_and_liquidity_friction)}")
    lines.append(f"* **Post-Trade Plumbing Constraints:** {_oneline(pp.post_trade_plumbing_constraints)}")
    lines.append("")

    lines.append("## 4. NEW HIGH-SIGNAL TARGETS FOR TRACKING")
    for target in analysis.new_high_signal_targets:
        lines.append(f"* {_link(target.name, target.url, bold=True)}: {_oneline(target.rationale)}")
    lines.append("")

    return "\n".join(lines)


def finalise_briefing(analysis: StrategicAnalysis, allowed_urls: Iterable[str]) -> str:
    """Run all QC steps and render. Mutates ``analysis``."""
    for warning in enforce_link_allowlist(analysis, allowed_urls):
        print(f"WARNING: {warning}", file=sys.stderr)
    apply_british_english(analysis)
    markdown_text = render_briefing(analysis)
    hedges = find_hedging(markdown_text)
    if hedges:
        print(f"WARNING: QC hedging phrases present: {', '.join(hedges)}", file=sys.stderr)
    return markdown_text


__all__ = [
    "PillarName", "enforce_link_allowlist", "to_british", "apply_british_english",
    "find_hedging", "render_briefing", "finalise_briefing", "search_url",
]

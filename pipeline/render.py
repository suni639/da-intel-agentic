"""Deterministic briefing rendering and QC.

The LLM produces structured JSON only; this module owns the Markdown layout,
so headers, section order and links are guaranteed rather than requested.
"""
import re
import sys
from typing import Iterable, List, Set
from urllib.parse import quote_plus

from schema import PILLAR_ORDER, Development, PillarName, StrategicAnalysis, Target

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
    """Apply ``fn`` to every editor-written prose field (not titles or names)."""
    for point in analysis.macro_view:
        point.headline, point.detail = fn(point.headline), fn(point.detail)
    analysis.uk_implications = [fn(x) for x in analysis.uk_implications]
    for pillar in analysis.pillars:
        pillar.synthesis = fn(pillar.synthesis)
        for dev in pillar.developments:
            dev.details = fn(dev.details)
            dev.label = fn(dev.label)
    for target in analysis.new_high_signal_targets:
        target.rationale = fn(target.rationale)
    analysis.subject_hook = fn(analysis.subject_hook)


def apply_british_english(analysis: StrategicAnalysis) -> None:
    """Normalise spelling in prose fields only.

    Source titles and entity names are left verbatim: they are quotations of
    third-party headlines and proper nouns (e.g. a US "Tokenization Act").
    """
    _map_prose(analysis, to_british)


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
    # Overclaiming: a trial or announcement rarely "eliminates" or "proves" anything.
    "eliminates": "reduces (only if the evidence says so)", "eliminate": "reduce",
    "eliminating": "reducing", "guarantees": "is designed to", "guarantee": "aim to",
    "proves": "shows", "prove": "show", "proved": "showed", "removes the need": "reduces the need",
    "game-changing": "(cut)", "unprecedented": "(cut unless the source says so)",
    # The brief is factual: no advice, recommendations or commentary.
    "should": "(state the fact instead of advising)", "need to": "(state the fact)",
    "needs to": "(state the fact)", "may need": "(state the fact)", "will need": "(state the fact)",
    "monitor": "(say what happens and when)", "keep an eye": "(say what happens and when)",
    "closely watch": "(say what happens and when)", "worth watching": "(say what happens and when)",
    "consider": "(state the fact)", "this shows": "(give the concrete fact)",
    "this confirms": "(give the concrete fact)", "this suggests": "(give the concrete fact)",
    "this means": "(give the concrete fact)", "this highlights": "(give the concrete fact)",
    "competitive benchmark": "(state the fact)", "regulatory clarity": "(say what the rule or proposal does)",
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


def _body_text(analysis: StrategicAnalysis) -> str:
    """Sentence-case prose only (no headlines, titles or labels).

    Used as the reference for deciding which headline words are proper nouns.
    Headlines must be excluded: a Title Case headline would otherwise "find
    itself" in the reference and every word would look like a proper noun.
    """
    parts = [p.detail for p in analysis.macro_view] + list(analysis.uk_implications)
    for pillar in analysis.pillars:
        parts += [d.details for d in pillar.developments]
    parts += [t.rationale for t in analysis.new_high_signal_targets]
    return "\n".join(parts)


def apply_sentence_case_headlines(analysis: StrategicAnalysis) -> None:
    reference = _body_text(analysis)
    for point in analysis.macro_view:
        point.headline = to_sentence_case(point.headline, reference)


def long_headlines(analysis: StrategicAnalysis) -> List[str]:
    return [p.headline for p in analysis.macro_view
            if len(p.headline.split()) > MAX_HEADLINE_WORDS]


def find_hedging(text: str) -> List[str]:
    return [p for p, rx in _HEDGE_RE if rx.search(text)]


def prose_text(analysis: StrategicAnalysis) -> str:
    """All rendered, model-written prose (not titles or names), for QC checks."""
    parts = []
    for point in analysis.macro_view[:MAX_ONE_MINUTE]:
        parts += [point.headline, point.detail]
    parts += analysis.uk_implications[:MAX_UK_IMPLICATIONS]
    for pillar in analysis.pillars:
        for dev in pillar.developments:
            if not (dev.stale or dev.exclude):
                parts += [dev.details, dev.label]
    parts += [t.rationale for t in analysis.new_high_signal_targets]
    parts.append(analysis.subject_hook)
    return "\n".join(p for p in parts if p)


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
    "one_minute": "In one minute",
    "uk": "The UK angle",
    "happened": "What happened",
    "targets": "Worth watching",
}
UK_SUBHEADING = "UK"
PILLAR_TITLES = {
    PillarName.BANKING: "Banks and payments",
    PillarName.ASSET_MANAGEMENT: "Funds, securities and market infrastructure",
    PillarName.SOVEREIGN: "Central banks",
    PillarName.REGULATORY: "Regulation and law",
    PillarName.FRONTIER: "New technology",
}

# Size limits that keep the brief to roughly a five-minute read (~800 words).
MAX_ONE_MINUTE = 3
MAX_UK_IMPLICATIONS = 3
MAX_ITEMS = 12
# The UK heading is a reading aid, not a quota: at most this many UK items are
# pulled to the top, so global institutional news keeps most of the slots.
MAX_UK_FIRST = 4
MAX_TARGETS = 3
TARGET_WORDS = 800
MAX_WORDS = 950


# Backstop for the strategist's "uk" flag: obvious UK signals in the title/details/source.
_UK_PATTERNS = re.compile(
    r"\b(UK|U\.K\.|United Kingdom|Britain|sterling|GBP|gilts?|"
    r"Bank of England|BoE|FCA|Financial Conduct Authority|PRA|HM Treasury|Prudential Regulation Authority|"
    r"Lloyds|Barclays|NatWest|HSBC UK|Santander UK|Nationwide|Monument Bank|Standard Chartered UK|"
    r"Digital Securities Sandbox|LSEG|London Stock Exchange)\b")


def is_uk(dev: Development) -> bool:
    return dev.uk or bool(_UK_PATTERNS.search(" ".join([dev.title, dev.label, dev.details, dev.source])))


def _keep_thin(dev: Development) -> bool:
    from feeds import source_quality
    return is_uk(dev) or source_quality(dev.source) in ("primary", "trade")


def _one_minute_ids(analysis: StrategicAnalysis) -> set:
    return {p.article_id for p in analysis.macro_view[:MAX_ONE_MINUTE] if p.article_id}


def selected_developments(analysis: StrategicAnalysis):
    """Developments that will be shown: UK first, then pillar order; capped.

    Returns a list of (pillar_name, development). Stale/excluded items and
    duplicate citations of the same article are dropped.
    """
    by_name = {}
    for pillar in analysis.pillars:
        by_name.setdefault(pillar.name, []).extend(pillar.developments)
    headline_ids = _one_minute_ids(analysis)
    ordered, seen = [], set()
    for name in PILLAR_ORDER:
        for dev in by_name.get(name, []):
            if dev.stale or dev.exclude or dev.article_id in seen:
                continue
            # A story summarised in "In one minute" is always shown in the body.
            if dev.thin and not _keep_thin(dev) and dev.article_id not in headline_ids:
                continue
            seen.add(dev.article_id)
            dev.uk = is_uk(dev)
            ordered.append((name, dev))
    uk_items = [x for x in ordered if x[1].uk]
    uk_first, uk_extra = uk_items[:MAX_UK_FIRST], uk_items[MAX_UK_FIRST:]
    # Global items keep the strategist's significance order within pillar order;
    # UK items beyond the cap only fill space that global news leaves free.
    rest = [x for x in ordered if not x[1].uk] + uk_extra
    # Stories cited in "In one minute" must survive the item cap.
    rest.sort(key=lambda x: x[1].article_id not in headline_ids)
    chosen = (uk_first + rest)[:MAX_ITEMS]
    # Items shown under a pillar heading rather than "UK" are rendered as non-UK.
    for _, dev in rest:
        dev.uk = False
    return chosen


_DATE_SIGNAL = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Q[1-4]|H[12]|20\d\d|year-end|end of the year|"
    r"next week|next month|this month|this week)\b", re.IGNORECASE)
_ENTITY_RE = re.compile(r"\b(?:[A-Z][a-z]*[A-Z][A-Za-z]*|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b")
_GENERIC_ENTITIES = {"The", "This", "It", "A", "An", "In", "On", "By", "UK", "US", "EU", "Bank",
                     "January", "February", "March", "April", "May", "June", "July", "August",
                     "September", "October", "November", "December"}


def _entities(text: str) -> set:
    """Distinctive capitalised words (organisations, programmes), one word at a time."""
    words = set()
    for entity in _ENTITY_RE.findall(text or ""):
        words |= {w for w in entity.split() if w not in _GENERIC_ENTITIES}
    return words


def selected_targets(analysis: StrategicAnalysis, chosen) -> List[Target]:
    """'Worth watching': dated upcoming events the reader has not just read about.

    Dropped: targets with no source article (vague themes), targets without a
    date or timeframe, and targets about an organisation/programme already
    covered in the body (e.g. a second DTCC item).
    """
    cited = {dev.article_id for _, dev in chosen}
    shown_entities = set()
    for _, dev in chosen:
        shown_entities |= _entities(f"{dev.label} {dev.title}")
    out = []
    for target in analysis.new_high_signal_targets:
        if not target.article_id or target.url.startswith(SEARCH_FALLBACK):
            continue
        if target.article_id in cited:
            continue
        if not _DATE_SIGNAL.search(f"{target.name} {target.rationale}"):
            continue
        if _entities(target.name) & shown_entities:
            continue
        out.append(target)
    return out[:MAX_TARGETS]


def repetitive_one_minute(analysis: StrategicAnalysis) -> List[str]:
    """'In one minute' bullets whose sentence just repeats the headline."""
    def content_words(text):
        return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in _STOPWORDS}

    out = []
    for point in analysis.macro_view[:MAX_ONE_MINUTE]:
        h, d = content_words(point.headline), content_words(point.detail)
        if d and len(h & d) / len(d) >= 0.5:
            out.append(point.headline)
    return out


_STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "via", "using", "by",
              "at", "from", "its", "their", "is", "are", "was", "were", "has", "have", "this", "that", "it"}


def display_publisher(source: str) -> str:
    """Clean publisher name for display: 'www.tokenpost.com' -> 'tokenpost.com'."""
    s = _oneline(source)
    s = re.sub(r"^https?://", "", s).rstrip("/")
    return s[4:] if s.lower().startswith("www.") else s


def _item_line(dev: Development) -> str:
    text = _oneline(dev.label) or _oneline(dev.title)
    source = display_publisher(dev.source)
    attribution = f" *({source})*" if source and source.lower() not in text.lower() else ""
    return f"* {_link(text, dev.url)}{attribution}: {_oneline(dev.details)}"


def render_briefing(analysis: StrategicAnalysis) -> str:
    lines: List[str] = []

    lines.append(f"## {SECTION_TITLES['one_minute']}")
    for point in analysis.macro_view[:MAX_ONE_MINUTE]:
        headline = _oneline(point.headline).strip("* ")
        if headline and headline[-1] not in ".!?:":
            headline += "."
        lines.append(f"* **{headline}** {_oneline(point.detail)}")
    lines.append("")

    implications = [_oneline(x) for x in analysis.uk_implications[:MAX_UK_IMPLICATIONS] if x.strip()]
    if implications:
        lines.append(f"## {SECTION_TITLES['uk']}")
        lines += [f"* {x}" for x in implications]
        lines.append("")

    chosen = selected_developments(analysis)
    lines.append(f"## {SECTION_TITLES['happened']}")
    lines.append("")
    uk_items = [dev for _, dev in chosen if dev.uk]
    if uk_items:
        lines.append(f"### {UK_SUBHEADING}")
        lines += [_item_line(dev) for dev in uk_items]
        lines.append("")
    for name in PILLAR_ORDER:
        items = [dev for pname, dev in chosen if pname == name and not dev.uk]
        if not items:
            continue
        lines.append(f"### {PILLAR_TITLES.get(name, name.value)}")
        lines += [_item_line(dev) for dev in items]
        lines.append("")

    targets = selected_targets(analysis, chosen)
    if targets:
        lines.append(f"## {SECTION_TITLES['targets']}")
        for target in targets:
            lines.append(f"* {_link(target.name, target.url, bold=True)}: {_oneline(target.rationale)}")
        lines.append("")

    return "\n".join(lines)


def word_count(markdown_text: str) -> int:
    """Words a reader sees (link URLs and markup excluded)."""
    text = re.sub(r"\]\([^)]*\)", "]", markdown_text)
    return len(re.findall(r"\w[\w'’.,/-]*", text))


def brief_word_count(analysis: StrategicAnalysis) -> int:
    return word_count(render_briefing(analysis))


def subject_line(analysis: StrategicAnalysis, max_chars: int = 80) -> str:
    """Short top-story phrase for the email subject (empty if none)."""
    hook = _oneline(analysis.subject_hook).strip(" .")
    if len(hook) > max_chars:
        hook = hook[:max_chars].rsplit(" ", 1)[0]
    return hook


def finalise_briefing(analysis: StrategicAnalysis, allowed_urls: Iterable[str]) -> str:
    """Run all QC steps and render. Mutates ``analysis``."""
    for pillar in analysis.pillars:
        for dev in pillar.developments:
            if dev.stale:
                print(f"WARNING: dropping stale development '{dev.title}' (event predates this week)",
                      file=sys.stderr)
            elif dev.exclude:
                print(f"WARNING: dropping off-topic development '{dev.title}'", file=sys.stderr)
            elif dev.thin and not _keep_thin(dev):
                print(f"WARNING: dropping thin development from a weak source '{dev.title}'", file=sys.stderr)
    for warning in enforce_link_allowlist(analysis, allowed_urls):
        print(f"WARNING: {warning}", file=sys.stderr)
    apply_british_english(analysis)
    _map_prose(analysis, plain_english)
    apply_sentence_case_headlines(analysis)
    markdown_text = render_briefing(analysis)
    hedges = find_hedging(prose_text(analysis))
    if hedges:
        print(f"WARNING: QC hedging phrases present: {', '.join(hedges)}", file=sys.stderr)
    words = word_count(markdown_text)
    print(f"Brief length: {words} words (target ~{TARGET_WORDS})")
    if words > MAX_WORDS:
        print(f"WARNING: brief is {words} words, over the {MAX_WORDS}-word limit", file=sys.stderr)
    return markdown_text


__all__ = [
    "PillarName", "enforce_link_allowlist", "to_british", "apply_british_english",
    "find_hedging", "render_briefing", "finalise_briefing", "search_url",
]

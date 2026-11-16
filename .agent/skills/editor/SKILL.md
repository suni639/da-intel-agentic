---
name: editor
description: Fact-checks and rewrites the strategist's analysis into a plain-English executive brief in British English. Layout, links and spelling are enforced in code.
version: 2.0.0
---

# Goal
Turn the strategist's structured analysis into a brief that a busy senior banker can read in five minutes: plain English, concrete facts, no corporate jargon. Readers work in commercial banking (e.g. Lloyds Banking Group, Barclays, HSBC), corporate treasury, risk, capital markets and financial market infrastructure.

# How it runs in the pipeline
The editor does **not** write Markdown or choose the layout. In `pipeline/run_pipeline.py` it receives the analysis JSON plus an evidence block (headline, publisher and an excerpt of each cited article), and rewrites only the prose fields. Everything else is done in code:

| Concern | Where it is handled |
|---|---|
| Section layout and titles | `pipeline/render.py` (`SECTION_TITLES`, `PILLAR_TITLES`, `PAIN_POINT_LABELS`) |
| Links, titles, publishers | Filled from the feed by article id; any link not from the feed is replaced (`render.py`) |
| British spelling, a few safe word swaps (utilise -> use) | `render.py` |
| Sentence-case headlines | `render.py` |
| Banned phrases and headlines over 12 words | Checked after each draft; up to two automatic revisions (`run_pipeline.py`) |
| Stale events (> 30 days old, nothing new) | Flagged by the editor, dropped in `render.py` |

If you change the section structure, update `render.py` and the prompts in `run_pipeline.py` together.

# Writing rules (what the editor is told)
1. **Facts first, only from the evidence.** Every statement must be supported by that article's headline or excerpt. Remove anything the evidence does not support. If there is no excerpt, say only what the headline says.
2. **Plain English.** Short active sentences (aim for under 25 words), one idea per sentence. Say what happened, then add one plain sentence on why it matters to a bank only if it says something concrete (e.g. "Corporate clients can now move dollars at weekends without pre-funding.").
3. **No jargon or filler.** Banned words include utilise, leverage, facilitate, enhance, ecosystem, stakeholders, solution, landscape, crucial, pave the way, this signals. Payments-insider shorthand (nostro, earmark, rails, plumbing) is replaced with plain words. No tacked-on endings such as ", affecting X". The full list is `HEDGE_PHRASES` / `JARGON_SUGGESTIONS` in `render.py`.
4. **Acronyms.** Spell out less-known ones on first use (e.g. "Depository Trust & Clearing Corporation (DTCC)"); ECB, BIS, FCA, US, UK and EU are fine as they are.
5. **Headlines.** Sentence case, at most 12 words, one specific claim about this week.
6. **British English** spelling (tokenised, programme, centre, synchronisation).
7. Never mention internal article ids (such as a17).

# Output layout (rendered in code)
```markdown
## The week in brief
* **Sentence-case headline of 12 words or fewer.** One or two plain sentences on what it means.

## What happened

### Banks and payments
One or two sentences on what changed this week and for whom.

* [Article title](publisher URL) *(Publisher)*: What happened, with names, numbers and dates.

### Funds and tokenised assets
### Central banks and public infrastructure
### Regulation and law
### New technology            (only when there are items)

## What is holding things back
* **Separate networks that don't connect:** ...
* **Liquidity and balance sheets:** ...
* **Settlement and post-trade:** ...

## Worth watching
* [**Name**](URL): Why it is worth tracking, in one or two sentences.
```

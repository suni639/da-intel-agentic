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
2. **Factual only.** Report what happened with names, numbers and dates. No advice, recommendations, predictions or commentary ("should", "need to", "this shows", "monitor"). A second sentence is only for a further fact (e.g. "Ant International is the first client.").
2a. **Plain English.** Short active sentences (aim for under 20 words), one idea per sentence.
3. **No jargon or filler.** Banned words include utilise, leverage, facilitate, enhance, ecosystem, stakeholders, solution, landscape, crucial, pave the way, this signals. Payments-insider shorthand (nostro, earmark, rails, plumbing) is replaced with plain words. No tacked-on endings such as ", affecting X". The full list is `HEDGE_PHRASES` / `JARGON_SUGGESTIONS` in `render.py`.
4. **Acronyms.** Spell out less-known ones on first use (e.g. "Depository Trust & Clearing Corporation (DTCC)"); ECB, BIS, FCA, US, UK and EU are fine as they are.
5. **Headlines.** Sentence case, at most 12 words, one specific claim about this week.
5a. **No overclaiming.** A trial "shows" or "could reduce"; it does not "prove" or "eliminate".
5b. **Link labels.** A short plain-English sentence with a subject and verb (at most 10 words), e.g. "Marex to offer tokenised Treasury financing after hours" - not a list of names.
5d. **Freshness.** The editor records each item's `event_date`. Items whose event is more than 14 days old are dropped; "In one minute" only covers events from the past 7 days.
5c. **Off-topic items** are marked `exclude`; **headline-only items** are marked `thin` and dropped only when they come from weak sources and are not UK or headlined in "In one minute".
6. **British English** spelling (tokenised, programme, centre, synchronisation).
7. Never mention internal article ids (such as a17).

# Output layout (rendered in code)
About 800 words, a five-minute read. Limits are enforced in `render.py` (`MAX_ONE_MINUTE`, `MAX_UK_IMPLICATIONS`, `MAX_ITEMS`, `MAX_TARGETS`, `MAX_WORDS`); a draft over the word limit is sent back to the editor to cut.

```markdown
## In one minute                      (3 bullets: the week's biggest stories, global or UK)
* **Sentence-case headline, 12 words or fewer.** One further concrete fact (not a repeat, not commentary).

## The UK angle                       (UK firms'/authorities' roles in international stories; never repeats the UK items; omitted if none)
* ...

## What happened                      (at most 12 items; up to 4 UK items first, global news keeps the rest)

### UK
* [Short plain-English label](publisher URL) *(Publisher)*: The fact, with names, numbers and dates.

### Banks and payments
### Funds, securities and market infrastructure
### Central banks
### Regulation and law
### New technology                   (only items involving tokenised money/assets, stablecoins, CBDCs or a DLT ledger)

## Worth watching                     (up to 3 dated upcoming events, not about anything covered above)
* [**Name**](URL): What happens next and when.
```

The email subject is "Digital Asset Digest, <date>: <top one or two stories>".

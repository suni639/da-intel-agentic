# Agentic Intelligence Team Configuration (Project ID: DA-INTEL-01)

## System Objective
Autonomously discover, enrich, filter, and synthesise weekly regulated wholesale institutional digital asset developments into a publication-ready brief.

## Multi-Agent Execution Graph

### 1. The Research Scout
* **Skill Identifier:** `scout`
* **Trigger:** Instantiated on a schedule or manual trigger.
* **Input Interface:** Invokes `pipeline/ingestion.py` to capture raw feed payloads.
* **Output Artifact:** Writes raw items and supplementary search updates to `shared_artifacts/raw_enriched_feed.json`.

### 2. The Macro Strategist
* **Skill Identifier:** `strategist`
* **Trigger:** Fired immediately upon validation of `shared_artifacts/raw_enriched_feed.json`.
* **Output Artifact:** Writes filtered, categorized strategic groups to `shared_artifacts/strategic_analysis.json`.

### 3. The Chief Editor & QC
* **Skill Identifier:** `editor`
* **Trigger:** Fired immediately upon validation of `shared_artifacts/strategic_analysis.json`.
* **Output Artifact:** Produces `pipeline/output_briefing.md` and triggers external publishing coordinates (`pipeline/publish.py`).
"""Typed contract for the Macro Strategist / Chief Editor JSON payload.

The same models are passed to Gemini as ``response_schema`` (so the model is
constrained to emit this shape) and used to validate whatever comes back.
"""
from enum import Enum
from typing import List

from pydantic import BaseModel, model_validator


class PillarName(str, Enum):
    BANKING = "Banking Infrastructure & Commercial Rails"
    ASSET_MANAGEMENT = "Institutional Asset Management & RWAs"
    SOVEREIGN = "Sovereign Infrastructure & CBDCs"
    REGULATORY = "Regulatory & Legal Frameworks"
    FRONTIER = "Frontier & Emerging Innovations"


# Render order in the briefing.
PILLAR_ORDER = list(PillarName)


class MacroPoint(BaseModel):
    """One 'In one minute' bullet: a short headline plus one factual sentence."""
    headline: str
    detail: str
    # The development this bullet summarises; it is always shown in the body.
    article_id: str = ""


class Development(BaseModel):
    # The model cites the input article by id; title/source/url are then
    # filled in by code from the feed (see run_pipeline.resolve_article_refs),
    # so long opaque URLs never have to be copied by the model.
    article_id: str
    title: str = ""
    source: str = ""
    url: str = ""
    details: str
    # Short plain-English link text written by the editor (raw headlines are
    # often long, US-spelt or clickbait). Falls back to the title if empty.
    label: str = ""
    # Set by the strategist when the development directly concerns the UK
    # (UK banks, BoE, FCA, HM Treasury, UK law/market); shown first.
    uk: bool = False
    # Set by the editor when the evidence shows the underlying event is old
    # news (e.g. a launch months ago re-reported this week); not rendered.
    stale: bool = False
    # Set by the editor for items that are off-topic for a digital-asset brief;
    # never rendered.
    exclude: bool = False
    # Set by the editor when the evidence gives nothing beyond the headline.
    # Thin items are dropped only when they come from weak sources and are not UK.
    thin: bool = False


class Pillar(BaseModel):
    name: PillarName
    synthesis: str = ""  # kept for context; no longer rendered
    developments: List[Development]


class Target(BaseModel):
    name: str
    article_id: str = ""
    url: str = ""
    rationale: str


class StrategicAnalysis(BaseModel):
    # Rendered as "In one minute" (at most 3 bullets).
    macro_view: List[MacroPoint]
    # Rendered as "What it means for UK banks" (2-3 plain sentences).
    uk_implications: List[str] = []
    pillars: List[Pillar]
    # Rendered as "Worth watching": only targets not already covered above.
    new_high_signal_targets: List[Target]
    # A few words naming the week's top story, used in the email subject.
    subject_hook: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_pillar_mapping(cls, data):
        # Earlier versions emitted ``pillars`` as {name: {synthesis, developments}}.
        if isinstance(data, dict) and isinstance(data.get("pillars"), dict):
            data = dict(data)
            data["pillars"] = [
                {"name": name, **(body or {})} for name, body in data["pillars"].items()
            ]
        return data

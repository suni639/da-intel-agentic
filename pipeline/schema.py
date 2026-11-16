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
    headline: str
    detail: str


class Development(BaseModel):
    # The model cites the input article by id; title/source/url are then
    # filled in by code from the feed (see run_pipeline.resolve_article_refs),
    # so long opaque URLs never have to be copied by the model.
    article_id: str
    title: str = ""
    source: str = ""
    url: str = ""
    details: str
    # Set by the editor when the evidence shows the underlying event is old
    # news (e.g. a launch months ago re-reported this week); not rendered.
    stale: bool = False


class Pillar(BaseModel):
    name: PillarName
    synthesis: str
    developments: List[Development]


class PainPoints(BaseModel):
    interoperability_silos: str
    balance_sheet_and_liquidity_friction: str
    post_trade_plumbing_constraints: str


class Target(BaseModel):
    name: str
    article_id: str = ""
    url: str = ""
    rationale: str


class StrategicAnalysis(BaseModel):
    macro_view: List[MacroPoint]
    pillars: List[Pillar]
    structural_pain_points: PainPoints
    new_high_signal_targets: List[Target]

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

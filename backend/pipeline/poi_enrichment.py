from __future__ import annotations

from backend.integrations.gemini_client import GeminiClient, GeminiUnavailable
from backend.pipeline.types import LandmarkEraVisualFacts, ResolvedLandmark


async def enrich_poi(
    *,
    gemini: GeminiClient,
    landmark: ResolvedLandmark,
    facts: list[LandmarkEraVisualFacts],
) -> str:
    if gemini.settings.fast_poi_enrichment:
        address = f" at {landmark.resolved_address}" if landmark.resolved_address else ""
        return (
            f"{landmark.display_name}{address} is one of the grounded places used to anchor this generated view. "
            "For this hackathon build, historical detail is generated from the mapped place identity, current street-level reference imagery, and era-specific visual constraints."
        )

    relevant = [fact for fact in facts if fact.landmark_id == landmark.id]
    source_lines = "\n".join(
        f"{fact.era}: confidence={fact.overall_confidence}; sources={', '.join(fact.sources_cited[:3])}"
        for fact in relevant
    )
    prompt = f"""
Write a 2-3 sentence historical context blurb for this Singapore landmark.
Name: {landmark.display_name}
Address: {landmark.resolved_address or "unknown"}
Evidence by era:
{source_lines}

Be specific, grounded, and avoid unsupported claims.
"""
    try:
        text = await gemini.generate_text(model=gemini.poi_model, prompt=prompt)
    except GeminiUnavailable:
        text = ""
    except Exception:
        text = ""
    return text.strip() or f"{landmark.display_name} is one of the grounded structures identified in this view. Historical detail is limited until source research completes."

from __future__ import annotations

from pydantic import RootModel

from backend.integrations.gemini_client import GeminiClient, GeminiUnavailable
from backend.pipeline.types import LandmarkEraVisualFacts, ResearchDump, VisualFact


class FactsSchema(LandmarkEraVisualFacts):
    pass


EXTRACT_PROMPT = """
Extract visual facts for historical image generation from the research dump.
Only include facts that are specific to the target landmark/address and era.
Every medium/low confidence fact must have a source_url or be omitted.
Return structured JSON matching the schema.
"""


async def extract_visual_facts(gemini: GeminiClient, dump: ResearchDump) -> LandmarkEraVisualFacts:
    if not dump.text.strip():
        return _insufficient(dump)
    prompt = f"{EXTRACT_PROMPT}\n\nLandmark: {dump.landmark_name}\nEra: {dump.era}\nResearch dump:\n{dump.text}"
    try:
        result = await gemini.generate_json(model=gemini.extraction_model, prompt=prompt, response_schema=FactsSchema)
    except GeminiUnavailable:
        return _insufficient(dump)
    except Exception:
        return _insufficient(dump)
    facts = result if isinstance(result, LandmarkEraVisualFacts) else LandmarkEraVisualFacts.model_validate(result)
    facts.landmark_id = dump.landmark_id
    facts.landmark_name = dump.landmark_name
    facts.era = dump.era
    facts.era_label = _era_label(dump.era)
    facts.sources_cited = list(dict.fromkeys([*facts.sources_cited, *dump.sources]))
    _drop_weak_unsourced(facts)
    return facts


def _insufficient(dump: ResearchDump) -> LandmarkEraVisualFacts:
    return LandmarkEraVisualFacts(
        landmark_id=dump.landmark_id,
        landmark_name=dump.landmark_name,
        era=dump.era,
        era_label=_era_label(dump.era),
        overall_confidence="insufficient",
        existed_in_era=True,
        sources_cited=dump.sources,
    )


def _drop_weak_unsourced(facts: LandmarkEraVisualFacts) -> None:
    for field in (
        "appearance",
        "architectural_details",
        "signage",
        "surrounding_context",
        "distinctive_features",
        "explicitly_absent",
    ):
        values = getattr(facts, field)
        setattr(
            facts,
            field,
            [
                fact
                for fact in values
                if fact.confidence == "high" or fact.source_url or (facts.overall_confidence in {"high", "medium"})
            ],
        )


def _era_label(era: int) -> str:
    if era >= 2020:
        return "the present day"
    return f"around {era}"

from __future__ import annotations

import math

from backend.pipeline.types import GateDecision, LandmarkEraVisualFacts, ResolvedLandmark


def decide_gate(
    landmarks: list[ResolvedLandmark],
    facts: list[LandmarkEraVisualFacts],
    requested_eras: list[int],
) -> GateDecision:
    total_landmarks = max(1, len(landmarks))
    threshold = max(2, math.ceil(0.5 * total_landmarks))
    qualified: list[int] = []
    grounded_ids: set[str] = set()
    for era in requested_eras:
        era_facts = [fact for fact in facts if fact.era == era]
        documented = [
            fact for fact in era_facts if fact.overall_confidence in {"high", "medium"} and fact.existed_in_era
        ]
        if len(documented) >= threshold:
            qualified.append(era)
            grounded_ids.update(fact.landmark_id for fact in documented)

    if not qualified:
        return GateDecision(
            proceed=False,
            reason=(
                "We found less than half the visible structures documented for any era at this location. "
                "Try a more historically documented area like Chinatown, Kampong Glam, or Boat Quay."
            ),
            eras_to_generate=[],
            landmarks_to_ground=[],
        )
    if len(qualified) == 1 and max(requested_eras) not in qualified:
        return GateDecision(
            proceed=False,
            reason="Only one historical era qualified, and the current-day reference era was not sufficiently grounded.",
            eras_to_generate=[],
            landmarks_to_ground=[],
        )
    partial = set(qualified) != set(requested_eras)
    reason = "Proceeding with grounded eras only." if partial else "Proceeding with grounded landmark evidence."
    return GateDecision(
        proceed=True,
        reason=reason,
        eras_to_generate=qualified,
        landmarks_to_ground=sorted(grounded_ids),
    )

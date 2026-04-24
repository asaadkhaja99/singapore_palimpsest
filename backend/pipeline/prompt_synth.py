from __future__ import annotations

from backend.pipeline.types import Direction, FrameInventory, LandmarkEraVisualFacts


def synth_prompt(
    *,
    inventory: FrameInventory,
    facts: list[LandmarkEraVisualFacts],
    era: int,
    direction: Direction,
) -> tuple[str, list[str], list[str]]:
    era_label = "the present day" if era >= 2020 else f"around {era}"
    direction_text = {"N": "north", "E": "east", "S": "south", "W": "west"}[direction]
    by_landmark = {fact.landmark_id: fact for fact in facts if fact.era == era}
    lines: list[str] = []
    grounded_ids: list[str] = []
    absent: list[str] = []
    historical_refs: list[str] = []

    for landmark in sorted(inventory.landmarks, key=lambda item: item.estimated_distance_m):
        fact = by_landmark.get(landmark.id)
        if not fact or fact.overall_confidence not in {"high", "medium"}:
            continue
        grounded_ids.append(landmark.id)
        historical_refs.extend([fact.historical_reference_image_url] if fact.historical_reference_image_url else [])
        fact_text = _facts_text(fact)
        existed = "appeared as" if fact.existed_in_era else "did not yet exist; leave this position as documented surrounding streetscape"
        address = f" at {landmark.resolved_address}" if landmark.resolved_address else ""
        lines.append(
            f"- {landmark.display_name}{address}, visible in the {landmark.detection.frame_position}, "
            f"bearing {landmark.bearing_from_camera_deg:.0f} degrees from camera: in {era_label}, this {existed}. {fact_text}"
        )
        absent.extend(item.fact for item in fact.explicitly_absent)

    structure_text = "\n".join(lines) if lines else "- No sufficiently grounded named structures for this era."
    absent_text = "\n".join(f"- {item}" for item in sorted(set(absent))) if absent else "- Watermarks, captions, invented landmarks, fantasy architecture."
    prompt = f"""
A photorealistic documentary photograph of a Singapore street, taken in {era_label}.

The viewpoint is from a camera mounted approximately 2 meters above street level. The camera is facing {direction_text}.
Wide-angle lens, approximately 90-degree field of view. 16:9 framing. Sharp focus, documentary style.

The attached image is a present-day KartaView/OpenStreetCam street-level reference from this camera position.
Maintain the same road alignment, vanishing point, and overall composition as the reference. Only the era-appropriate
appearance of buildings and streetscape should change.

Structures in this scene, positions as in the reference:
{structure_text}

Street-level context should be historically plausible for Singapore in {era_label}, but do not add named structures
that are not listed above. Any unspecified area should remain ordinary urban texture.

CRITICAL - the scene must NOT include:
{absent_text}

Style: Documentary realism. Single coherent photograph. No watermarks, text overlays, borders, or captions.
""".strip()
    return prompt, historical_refs[:4], grounded_ids


def _facts_text(fact: LandmarkEraVisualFacts) -> str:
    snippets: list[str] = []
    for values in (
        fact.appearance,
        fact.architectural_details,
        fact.signage,
        fact.surrounding_context,
        fact.distinctive_features,
    ):
        snippets.extend(item.fact for item in values[:3])
    return " ".join(snippets[:8]) or "No detailed visual facts beyond existence and location were documented."

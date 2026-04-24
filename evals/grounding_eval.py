from __future__ import annotations

from backend.pipeline.gate import decide_gate
from backend.pipeline.types import FrameLandmarkDetection, LandmarkEraVisualFacts, ResolvedLandmark


def _landmark(idx: int) -> ResolvedLandmark:
    return ResolvedLandmark(
        id=f"lm_{idx}",
        detection=FrameLandmarkDetection(
            bbox_2d=[100, 100 + idx * 20, 400, 180 + idx * 20],
            label=f"Landmark {idx}",
            frame_position="foreground",
            detection_confidence="high",
        ),
        resolved_name=f"Landmark {idx}",
        resolved_lat=1.28,
        resolved_lng=103.84,
        bearing_from_camera_deg=0,
        estimated_distance_m=10,
        resolution_confidence="high",
        source="vision+places",
    )


def _fact(landmark_id: str, era: int, confidence: str = "high") -> LandmarkEraVisualFacts:
    return LandmarkEraVisualFacts(
        landmark_id=landmark_id,
        landmark_name=landmark_id,
        era=era,
        era_label=str(era),
        overall_confidence=confidence,
        existed_in_era=confidence != "insufficient",
    )


def main() -> None:
    eras = [1900, 1950, 1980, 2026]
    landmarks = [_landmark(1), _landmark(2), _landmark(3), _landmark(4)]

    easy_facts = [_fact(landmark.id, era) for landmark in landmarks for era in eras]
    easy = decide_gate(landmarks, easy_facts, eras)
    assert easy.proceed is True
    assert easy.eras_to_generate == eras

    medium_facts = [
        _fact(landmark.id, era)
        for landmark in landmarks
        for era in [1950, 1980, 2026]
    ] + [_fact("lm_1", 1900), _fact("lm_2", 1900, "low")]
    medium = decide_gate(landmarks, medium_facts, eras)
    assert medium.proceed is True
    assert len(medium.eras_to_generate) >= 3

    hard_facts = [_fact(landmark.id, era, "insufficient") for landmark in landmarks for era in eras]
    hard = decide_gate(landmarks, hard_facts, eras)
    assert hard.proceed is False
    assert "visible structures" in hard.reason

    print("grounding eval passed")


if __name__ == "__main__":
    main()

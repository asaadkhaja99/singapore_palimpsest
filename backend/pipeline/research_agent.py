from __future__ import annotations

from backend.integrations.gemini_client import GeminiClient, GeminiUnavailable
from backend.pipeline.types import ResolvedLandmark, ResearchDump


async def research_landmark_era(gemini: GeminiClient, landmark: ResolvedLandmark, era: int) -> ResearchDump:
    name = landmark.display_name
    address = landmark.resolved_address or "unknown address in Singapore"
    prompt = f"""
You are researching the historical appearance of a specific address or named landmark in Singapore.
Target: {name}
Address: {address}
Era: {era}

Return concise grounded notes about this building or structure at this address in this era only.
Prioritize National Archives of Singapore, NLB PictureSG, URA Conservation Portal, roots.gov.sg,
Wikipedia, and academic/local history sites. Include source URLs inline. If the structure did not
exist or has no documented appearance for this era, say so explicitly. Do not generalize from the
district unless it is clearly about adjacent streetscape context.
"""
    try:
        text = await gemini.generate_text(model=gemini.research_model, prompt=prompt, use_google_search=True)
    except GeminiUnavailable:
        text = ""
    except Exception as exc:
        text = f"Research failed: {exc}"
    return ResearchDump(
        landmark_id=landmark.id,
        landmark_name=name,
        era=era,
        text=text,
        sources=_extract_urls(text),
        historical_reference_image_url=None,
    )


def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for token in text.replace(")", " ").replace("]", " ").split():
        if token.startswith("http://") or token.startswith("https://"):
            urls.append(token.rstrip(".,;"))
    return list(dict.fromkeys(urls))

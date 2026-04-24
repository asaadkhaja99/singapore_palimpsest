from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import httpx

from backend.config import Settings
from backend.pipeline.types import ResolvedLandmark


USER_AGENT = "PalimpsestHackathon/0.1 (contact: local-dev@example.invalid)"


@dataclass
class AreaResearch:
    area_name: str
    text: str
    sources: list[str]


async def research_area(
    *,
    settings: Settings,
    tour_name: str,
    landmarks: list[ResolvedLandmark],
) -> AreaResearch:
    queries = _area_queries(tour_name, landmarks)
    sources: list[str] = []
    sections: list[str] = []

    async with httpx.AsyncClient(
        timeout=settings.area_research_timeout_s,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        for query in queries[:6]:
            key = query.replace(" ", "_")
            title = query
            summary = await _wikipedia_summary(client, key)
            if not summary:
                page = await _search_wikipedia_page(client, query)
                if not page:
                    continue
                title = page.get("title") or query
                key = page.get("key") or title.replace(" ", "_")
                summary = await _wikipedia_summary(client, key)
            if not summary:
                continue
            title = summary.get("title") or title
            url = _summary_url(summary, key)
            extract = (summary.get("extract") or "").strip()
            if not extract:
                continue
            sources.append(url)
            sections.append(f"Wikipedia - {title}\nURL: {url}\n{extract}")
            if len(sections) >= 3:
                break

    source_targets = _singapore_source_targets(queries[0])
    sources.extend(item["url"] for item in source_targets)
    target_lines = "\n".join(f"- {item['name']}: {item['url']} ({item['use']})" for item in source_targets)
    body = "\n\n".join(sections) if sections else "No matching Wikipedia area page was found in the fast area lookup."
    text = f"""
Area-level research for {queries[0]}.

{body}

Singapore-specific sources to verify or extend this area context:
{target_lines}

Use this as area-level grounding, not as proof that every nearby POI has individual historical documentation.
The image prompt must preserve the current reference geometry and avoid inventing named landmarks outside the mapped POI list.
""".strip()
    return AreaResearch(area_name=queries[0], text=text[: settings.area_research_max_chars], sources=list(dict.fromkeys(sources)))


async def _search_wikipedia_page(client: httpx.AsyncClient, query: str) -> dict[str, Any] | None:
    response = await client.get(
        "https://api.wikimedia.org/core/v1/wikipedia/en/search/page",
        params={"q": query, "limit": 5},
    )
    if response.status_code >= 400:
        return None
    pages = response.json().get("pages") or []
    if not pages:
        return None
    pages.sort(key=lambda page: _page_score(query, page), reverse=True)
    return pages[0]


async def _wikipedia_summary(client: httpx.AsyncClient, key: str) -> dict[str, Any] | None:
    response = await client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(key)}")
    if response.status_code >= 400:
        return None
    return response.json()


def _summary_url(summary: dict[str, Any], key: str) -> str:
    urls = summary.get("content_urls") or {}
    desktop = urls.get("desktop") or {}
    return desktop.get("page") or f"https://en.wikipedia.org/wiki/{quote_plus(key)}"


def _page_score(query: str, page: dict[str, Any]) -> int:
    title = str(page.get("title") or "")
    description = str(page.get("description") or "")
    haystack = f"{title} {description}".lower()
    query_lower = query.lower()
    score = 0
    if title.lower() == query_lower:
        score += 10
    if query_lower in title.lower():
        score += 7
    if "singapore" in haystack:
        score += 4
    if "street" in haystack or "road" in haystack:
        score += 3
    if "temple" in haystack or "mosque" in haystack or "heritage" in haystack:
        score += 2
    if "mrt station" in haystack:
        score -= 6
    return score


def _area_queries(tour_name: str, landmarks: list[ResolvedLandmark]) -> list[str]:
    values = [tour_name]
    streets = [landmark.resolved_street for landmark in landmarks if landmark.resolved_street]
    values.extend(streets)
    values.extend(_street_from_address(landmark.resolved_address or "") for landmark in landmarks)
    values.extend(landmark.display_name for landmark in landmarks[:3])
    cleaned = [_clean_query(value) for value in values if value]
    return list(dict.fromkeys(query for query in cleaned if query))


def _clean_query(value: str) -> str:
    value = re.sub(r"\bSingapore\b.*$", "Singapore", value, flags=re.IGNORECASE).strip(" ,")
    return value


def _street_from_address(address: str) -> str:
    match = re.search(r"([A-Za-z' -]+(?:Street|Road|Avenue|Lane|Drive|Way))", address)
    return match.group(1).strip() if match else ""


def _singapore_source_targets(query: str) -> list[dict[str, str]]:
    encoded = quote_plus(query)
    return [
        {
            "name": "NLB Infopedia",
            "url": f"https://www.nlb.gov.sg/main/search?query={encoded}",
            "use": "street, landmark, and Singapore-history background",
        },
        {
            "name": "Roots.gov.sg",
            "url": f"https://www.roots.gov.sg/search?query={encoded}",
            "use": "NHB heritage trails, monuments, and landmark writeups",
        },
        {
            "name": "National Archives of Singapore",
            "url": f"https://www.nas.gov.sg/archivesonline/photographs/search-result?search-type=basic&keywords={encoded}",
            "use": "historical photographs and visual reference records",
        },
        {
            "name": "URA Conservation Portal",
            "url": "https://www.ura.gov.sg/Conservation-Portal/Explore/",
            "use": "conservation-area and shophouse context",
        },
    ]

"""GitHub solutions finder — searches for ready-to-use repositories and libraries.

Strategy: prefer existing solutions over writing from scratch.
After finding candidates, the dependency optimizer trims them to minimum required deps.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


@dataclass
class RepositoryCandidate:
    name: str
    full_name: str
    description: str
    stars: int
    url: str
    language: str | None
    topics: list[str]
    license_name: str | None


class GitHubFinder:
    """Searches GitHub for repositories matching a functional requirement."""

    def __init__(self, github_token: str | None = None, max_results: int = 10) -> None:
        self._token = github_token
        self._max_results = max_results
        self._headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            self._headers["Authorization"] = f"Bearer {github_token}"

    async def search(
        self,
        query: str,
        language: str | None = None,
        min_stars: int = 100,
    ) -> list[RepositoryCandidate]:
        q = query
        if language:
            q += f" language:{language}"
        if min_stars:
            q += f" stars:>={min_stars}"

        params = {
            "q": q,
            "sort": "stars",
            "order": "desc",
            "per_page": self._max_results,
        }
        log.info("github_search", query=q)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                GITHUB_SEARCH_URL, params=params, headers=self._headers
            )
            if response.status_code == 403:
                log.warning("github_rate_limited")
                return []
            response.raise_for_status()
            data = response.json()

        return [
            RepositoryCandidate(
                name=item["name"],
                full_name=item["full_name"],
                description=item.get("description") or "",
                stars=item["stargazers_count"],
                url=item["html_url"],
                language=item.get("language"),
                topics=item.get("topics", []),
                license_name=item.get("license", {}).get("spdx_id") if item.get("license") else None,
            )
            for item in data.get("items", [])
        ]

    async def get_readme(self, full_name: str) -> str:
        """Fetch repository README for deeper analysis."""
        url = f"https://api.github.com/repos/{full_name}/readme"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers={
                **self._headers,
                "Accept": "application/vnd.github.v3.raw",
            })
            if response.status_code != 200:
                return ""
            return response.text

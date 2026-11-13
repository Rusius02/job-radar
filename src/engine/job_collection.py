from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

from src.collectors.html_scraper import HtmlScraper, ScrapingNotAllowedError
from src.engine.job_analyzer import JobAnalyzer, JobProfile
from src.storage.database import JobRadarDatabase


ScraperFactory = Callable[[], HtmlScraper]


def collect_enabled_sites(
    database: JobRadarDatabase,
    *,
    scraper_factory: ScraperFactory | None = None,
) -> dict[str, Any]:
    profile_data = database.get_profile()
    preferences = profile_data["preferences"]
    profile = JobProfile(
        desired_titles=tuple(preferences["desired_titles"]),
        skills=tuple(skill["name"] for skill in profile_data["skills"]),
        locations=tuple(preferences["desired_locations"]),
        keywords=tuple(preferences["keywords"]),
        remote_only=preferences["remote_only"],
    )
    profile_configured = any((
        profile.desired_titles,
        profile.skills,
        profile.locations,
        profile.keywords,
        profile.remote_only is not None,
    ))
    sites = database.list_job_sites()
    factory = scraper_factory or (
        lambda: HtmlScraper("JobRadar/1.0 (manual local job search)", min_interval=1.0)
    )
    scraper = factory()
    analyzer = JobAnalyzer()
    results: list[dict[str, Any]] = []

    for site in sites:
        if not site["is_enabled"]:
            continue
        if not site["terms_reviewed"]:
            results.append({
                "site": site["name"],
                "status": "skipped",
                "message": "Active site skipped: review its rules and terms in Settings first.",
                "offers_found": 0,
                "offers_saved": 0,
            })
            continue

        try:
            html = scraper.fetch(site["url"], terms_reviewed=True)
            analysis = analyzer.analyze(html, profile, page_url=site["url"], top_n=500)
            saved = 0
            warnings = list(analysis.warnings)
            for match in analysis.matches:
                posting_url = urljoin(site["url"], match.offer.url or site["url"])
                if not _is_http_url(posting_url):
                    warnings.append(f"Skipped offer with an invalid URL: {match.offer.title}.")
                    continue
                try:
                    offer_data: dict[str, Any] = {
                        "title": match.offer.title,
                        "description": match.offer.description,
                        "organization": match.offer.organization,
                        "source_name": site["name"],
                        "source_url": posting_url,
                        "application_url": posting_url,
                        "date_posted": match.offer.date_posted,
                        "date_found": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "locations": list(match.offer.locations),
                        "skills": list(match.offer.skills),
                        "employment_type": list(match.offer.employment_type),
                        "is_remote": match.offer.is_remote,
                    }
                    if profile_configured:
                        offer_data["score"] = match.score
                        offer_data["reasons"] = list(match.reasons)
                    database.save_offer(offer_data)
                    saved += 1
                except (ValueError, sqlite3.Error) as error:
                    warnings.append(f"Could not save {match.offer.title}: {error}")

            results.append({
                "site": site["name"],
                "status": "success",
                "offers_found": analysis.offers_found,
                "offers_saved": saved,
                "warnings": warnings,
            })
        except ScrapingNotAllowedError as error:
            results.append({
                "site": site["name"],
                "status": "blocked",
                "message": str(error),
                "offers_found": 0,
                "offers_saved": 0,
            })
        except (OSError, ValueError, sqlite3.Error) as error:
            results.append({
                "site": site["name"],
                "status": "error",
                "message": str(error),
                "offers_found": 0,
                "offers_saved": 0,
            })

    return {
        "sites_attempted": sum(result["status"] in {"success", "blocked", "error"} for result in results),
        "offers_found": sum(result["offers_found"] for result in results),
        "offers_saved": sum(result["offers_saved"] for result in results),
        "warnings": (
            [] if profile_configured
            else ["No profile preferences configured; offers were collected without relevance scores."]
        ),
        "results": results,
    }


def _is_http_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)

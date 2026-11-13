import json
import tempfile
import unittest
from pathlib import Path

from src.collectors.html_scraper import ScrapingNotAllowedError
from src.engine.job_collection import collect_enabled_sites
from src.storage.database import JobRadarDatabase


def job_page() -> str:
    job = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Python engineer",
        "description": "Build services with Python.",
        "hiringOrganization": {"name": "Example"},
        "url": "https://jobs.example.test/offer/1",
        "skills": ["Python"],
    }
    return f'<script type="application/ld+json">{json.dumps(job)}</script>'


class FakeScraper:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.fetched: list[tuple[str, bool]] = []

    def fetch(self, url: str, *, terms_reviewed: bool = False) -> str:
        self.fetched.append((url, terms_reviewed))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class JobCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = JobRadarDatabase(Path(self.temporary_directory.name) / "job-radar.sqlite3")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_fetches_only_reviewed_active_sites_and_saves_structured_jobs(self) -> None:
        active = self.database.add_job_site(
            "Example",
            "https://example.test/jobs",
            terms_reviewed=True,
            is_enabled=True,
        )
        self.database.add_job_site(
            "Unreviewed",
            "https://unreviewed.test/jobs",
            terms_reviewed=False,
            is_enabled=True,
        )
        self.database.add_job_site(
            "Paused",
            "https://paused.test/jobs",
            terms_reviewed=True,
            is_enabled=False,
        )
        scraper = FakeScraper(job_page())

        report = collect_enabled_sites(self.database, scraper_factory=lambda: scraper)

        self.assertEqual(scraper.fetched, [(active["url"], True)])
        self.assertEqual(report["sites_attempted"], 1)
        self.assertEqual(report["offers_found"], 1)
        self.assertEqual(report["offers_saved"], 1)
        self.assertEqual(report["results"][0]["status"], "success")
        offer = self.database.list_recent_offers()[0]
        self.assertEqual(offer["title"], "Python engineer")
        self.assertEqual(offer["source_name"], "Example")
        self.assertIsNone(offer["score"])
        self.assertEqual(offer["skills"], ["Python"])

    def test_reports_robots_or_permission_blocks_without_suppressing_error(self) -> None:
        site = self.database.add_job_site(
            "Blocked",
            "https://blocked.test/jobs",
            terms_reviewed=True,
        )
        scraper = FakeScraper(
            ScrapingNotAllowedError("robots.txt disallows scraping this URL.")
        )

        report = collect_enabled_sites(self.database, scraper_factory=lambda: scraper)

        self.assertEqual(report["results"], [{
            "site": site["name"],
            "status": "blocked",
            "message": "robots.txt disallows scraping this URL.",
            "offers_found": 0,
            "offers_saved": 0,
        }])


if __name__ == "__main__":
    unittest.main()

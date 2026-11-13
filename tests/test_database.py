import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.storage.database import JobRadarDatabase


class JobRadarDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = JobRadarDatabase(Path(self.temporary_directory.name) / "test.sqlite3")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_initializes_normalized_profile_and_offer_tables(self) -> None:
        connection = sqlite3.connect(self.database.path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            connection.close()

        self.assertTrue({
            "profiles",
            "app_metadata",
            "profile_preferences",
            "profile_skills",
            "experiences",
            "educations",
            "certifications",
            "profile_languages",
            "profile_links",
            "projects",
            "project_skills",
            "job_sites",
            "offers",
            "offer_locations",
            "offer_skills",
            "offer_employment_types",
            "offer_matches",
        }.issubset(tables))
        self.assertEqual(self.database.get_profile()["id"], 1)

    def test_upgrades_an_existing_schema_version(self) -> None:
        connection = sqlite3.connect(self.database.path)
        try:
            connection.execute("DROP TABLE project_skills")
            connection.execute("DROP TABLE projects")
            connection.execute("PRAGMA user_version = 2")
            connection.commit()
        finally:
            connection.close()

        upgraded = JobRadarDatabase(self.database.path)

        self.assertIn("projects", upgraded.get_profile())
        connection = sqlite3.connect(self.database.path)
        try:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)
        finally:
            connection.close()

    def test_saves_and_reloads_complete_profile(self) -> None:
        profile = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "headline": "Data engineer",
            "email": "ada@example.com",
            "phone": "+33123456789",
            "location": "Paris",
            "summary": "Builds reliable data products.",
            "linkedin_url": "https://linkedin.com/in/ada",
            "portfolio_url": "https://example.com",
            "resume_url": "https://example.com/cv.pdf",
            "preferences": {
                "remote_only": True,
                "salary_min": 60000,
                "salary_currency": "EUR",
                "desired_titles": ["Data engineer"],
                "desired_locations": ["Paris"],
                "keywords": ["Python"],
                "employment_types": ["FULL_TIME"],
            },
            "skills": [{"name": "Python", "proficiency": "Expert", "years_experience": 8}],
            "experiences": [{
                "title": "Senior engineer",
                "company": "Example",
                "location": "Paris",
                "employment_type": "FULL_TIME",
                "description": "Led the platform team.",
                "start_date": "2020-01-01",
                "end_date": None,
                "is_current": True,
                "sort_order": 0,
            }],
            "education": [{
                "institution": "University",
                "degree": "MSc",
                "field_of_study": "Computer Science",
                "location": "London",
                "description": "",
                "start_date": "2015-09-01",
                "end_date": "2017-06-30",
                "sort_order": 0,
            }],
            "certifications": [{
                "name": "Cloud architect",
                "issuer": "Cloud Corp",
                "credential_id": "ABC-123",
                "credential_url": "https://example.com/cert",
                "issue_date": "2024-01-01",
                "expiry_date": "2027-01-01",
                "sort_order": 0,
            }],
            "languages": [{"language": "French", "proficiency": "Native"}],
            "links": [{"label": "GitHub", "url": "https://github.com/ada"}],
            "projects": [{
                "name": "Job Radar",
                "role": "Creator",
                "description": "Built a job matching tool.",
                "url": "https://example.com/job-radar",
                "skills": ["Python", "SQLite"],
            }],
        }

        saved = self.database.save_profile(profile)

        self.assertEqual(saved["first_name"], "Ada")
        self.assertEqual(saved["preferences"]["salary_min"], 60000)
        self.assertEqual(saved["skills"][0]["years_experience"], 8.0)
        self.assertTrue(saved["experiences"][0]["is_current"])
        self.assertEqual(saved["education"][0]["institution"], "University")
        self.assertEqual(saved["certifications"][0]["credential_id"], "ABC-123")
        self.assertEqual(saved["languages"][0]["language"], "French")
        self.assertEqual(saved["links"][0]["label"], "GitHub")
        self.assertEqual(saved["projects"][0]["name"], "Job Radar")
        self.assertEqual(saved["projects"][0]["skills"], ["Python", "SQLite"])

    def test_profile_save_is_atomic(self) -> None:
        self.database.save_profile({"first_name": "Before"})

        with self.assertRaises(ValueError):
            self.database.save_profile({
                "first_name": "After",
                "experiences": ["not an object"],
            })

        self.assertEqual(self.database.get_profile()["first_name"], "Before")

    def test_upserts_offers_and_returns_five_latest_with_match_details(self) -> None:
        for day in range(1, 8):
            self.database.save_offer({
                "title": f"Offer {day}",
                "url": f"https://example.com/jobs/{day}",
                "date_found": f"2026-11-{day:02d}T12:00:00+01:00",
                "locations": ["Paris"],
                "skills": ["Python"],
                "employment_type": ["FULL_TIME"],
                "score": 80 + day,
                "reasons": ["Python matches"],
            })

        latest = self.database.list_recent_offers()

        self.assertEqual(len(latest), 5)
        self.assertEqual(latest[0]["title"], "Offer 7")
        self.assertEqual(latest[0]["url"], "https://example.com/jobs/7")
        self.assertEqual(latest[0]["score"], 87)
        self.assertEqual(latest[0]["reasons"], ["Python matches"])
        self.assertEqual(latest[0]["locations"], ["Paris"])
        self.assertEqual(latest[0]["employment_type"], ["FULL_TIME"])

        offer_id = self.database.save_offer({
            "title": "Updated title",
            "url": "https://example.com/jobs/7",
            "score": 92,
            "reasons": ["New score"],
        })
        refreshed = self.database.list_recent_offers()
        self.assertEqual(len(refreshed), 5)
        self.assertEqual(refreshed[0]["id"], offer_id)
        self.assertEqual(refreshed[0]["title"], "Updated title")
        self.assertEqual(refreshed[0]["score"], 92)
        self.assertEqual(refreshed[0]["locations"], ["Paris"])
        self.assertEqual(refreshed[0]["skills"], ["Python"])

        connection = sqlite3.connect(self.database.path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM offers").fetchone()[0], 7)
        finally:
            connection.close()

    def test_invalid_offer_rolls_back_without_partial_update(self) -> None:
        self.database.save_offer({
            "title": "Original",
            "url": "https://example.com/jobs/1",
        })

        with self.assertRaises(ValueError):
            self.database.save_offer({
                "title": "Invalid update",
                "url": "https://example.com/jobs/1",
                "score": 101,
            })

        self.assertEqual(self.database.list_recent_offers()[0]["title"], "Original")

    def test_job_sites_can_be_added_paused_and_removed(self) -> None:
        site = self.database.add_job_site(
            "Example Careers",
            "HTTPS://EXAMPLE.COM/jobs/",
            terms_reviewed=True,
        )
        self.assertEqual(site["url"], "https://example.com/jobs")
        self.assertTrue(site["is_enabled"])
        self.assertTrue(site["terms_reviewed"])

        paused = self.database.update_job_site_enabled(site["id"], False)
        self.assertFalse(paused["is_enabled"])
        self.assertEqual(self.database.list_job_sites(), [paused])

        self.assertTrue(self.database.delete_job_site(site["id"]))
        self.assertFalse(self.database.delete_job_site(site["id"]))
        self.assertEqual(self.database.list_job_sites(), [])

    def test_job_sites_validate_urls_and_reject_duplicates(self) -> None:
        with self.assertRaises(ValueError):
            self.database.add_job_site("Invalid", "file:///etc/passwd")

        self.database.add_job_site("Example", "https://example.com/jobs")
        with self.assertRaises(ValueError):
            self.database.add_job_site("Duplicate", "https://EXAMPLE.com/jobs/")


if __name__ == "__main__":
    unittest.main()

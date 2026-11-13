import json
import unittest

from src.engine.job_analyzer import JobAnalyzer, JobPageAnalysisError, JobProfile


def page_with_jobs(*jobs: dict) -> str:
    return (
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@graph": list(jobs)})
        + "</script>"
    )


class JobAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = JobAnalyzer()

    def test_extracts_and_ranks_job_postings(self) -> None:
        page = page_with_jobs(
            {
                "@type": "JobPosting",
                "title": "Python developer",
                "description": "<p>Build an API with Python and Django.</p>",
                "skills": ["Python", "Django"],
                "hiringOrganization": {"name": "Good Jobs"},
                "jobLocation": {
                    "address": {
                        "addressLocality": "Paris",
                        "addressCountry": "France",
                    }
                },
                "url": "https://example.com/python",
                "jobLocationType": "TELECOMMUTE",
            },
            {
                "@type": "https://schema.org/JobPosting",
                "title": "Sales assistant",
                "description": "Work with customers.",
                "url": "https://example.com/sales",
            },
        )
        profile = JobProfile(
            desired_titles=("Python developer",),
            skills=("Python", "Django"),
            locations=("Paris",),
            keywords=("API",),
            remote_only=True,
        )

        result = self.analyzer.analyze(page, profile, top_n=1)

        self.assertEqual(result.offers_found, 2)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].offer.organization, "Good Jobs")
        self.assertEqual(result.matches[0].offer.locations, ("Paris, France",))
        self.assertEqual(result.matches[0].score, 100)
        self.assertIn("Skills found: Python, Django", result.matches[0].reasons)

    def test_reports_when_page_has_no_supported_structured_data(self) -> None:
        result = self.analyzer.analyze("<html><p>Job listing</p></html>", JobProfile(skills=("Python",)))

        self.assertEqual(result.offers_found, 0)
        self.assertTrue(result.warnings)

    def test_empty_profile_is_valid_for_extraction_and_top_n_is_validated(self) -> None:
        result = self.analyzer.analyze(
            "<html></html>",
            JobProfile(),
        )
        self.assertEqual(result.offers_found, 0)
        with self.assertRaises(JobPageAnalysisError):
            self.analyzer.analyze("", JobProfile(skills=("Python",)), top_n=-1)


if __name__ == "__main__":
    unittest.main()

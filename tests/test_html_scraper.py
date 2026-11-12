import unittest
from email.message import Message
from unittest.mock import patch

from src.collectors.html_scraper import HtmlScraper, ScrapingNotAllowedError


class FakeResponse:
    def __init__(self, body: bytes, url: str, content_type: str = "text/plain") -> None:
        self.body = body
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def getcode(self):
        return 200

    def geturl(self):
        return self.url

    def read(self, size=-1):
        return self.body[:size]


class HtmlScraperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scraper = HtmlScraper("JobRadarBot/1.0 (contact: admin@example.com)", min_interval=0)

    def test_requires_explicit_terms_review(self) -> None:
        with self.assertRaises(ScrapingNotAllowedError):
            self.scraper.fetch("https://example.com/jobs")

    @patch.object(HtmlScraper, "_open")
    def test_refuses_url_disallowed_by_robots_txt(self, open_request) -> None:
        open_request.return_value = FakeResponse(
            b"User-agent: *\nDisallow: /jobs",
            "https://example.com/robots.txt",
        )

        with self.assertRaises(ScrapingNotAllowedError):
            self.scraper.fetch("https://example.com/jobs", terms_reviewed=True)
        open_request.assert_called_once()

    @patch.object(HtmlScraper, "_open")
    def test_fetches_html_when_allowed_by_robots_txt(self, open_request) -> None:
        open_request.side_effect = [
            FakeResponse(
                b"User-agent: *\nAllow: /",
                "https://example.com/robots.txt",
            ),
            FakeResponse(
                b"<html>ok</html>",
                "https://example.com/jobs",
                "text/html; charset=utf-8",
            ),
        ]

        result = self.scraper.fetch("https://example.com/jobs", terms_reviewed=True)

        self.assertEqual(result, "<html>ok</html>")
        self.assertEqual(open_request.call_count, 2)


if __name__ == "__main__":
    unittest.main()

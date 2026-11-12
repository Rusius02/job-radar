import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.storage.database import JobRadarDatabase
from src.ui.server import JobRadarHandler, JobRadarServer, import_legacy_offers


class LegacyOfferImportTests(unittest.TestCase):
    def test_imports_legacy_json_into_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "offers.json"
            source.write_text(json.dumps([{
                "title": "Python developer",
                "url": "https://example.com/jobs/python",
                "organization": "Example",
                "date_found": "2026-11-12T10:00:00+01:00",
            }]), encoding="utf-8")
            database = JobRadarDatabase(root / "job-radar.sqlite3")

            imported = import_legacy_offers(database, source)
            repeated_import = import_legacy_offers(database, source)

            self.assertEqual(imported, 1)
            self.assertEqual(repeated_import, 0)
            self.assertEqual(len(database.list_recent_offers()), 1)
            self.assertEqual(
                database.list_recent_offers()[0]["url"],
                "https://example.com/jobs/python",
            )

    def test_missing_legacy_file_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = JobRadarDatabase(root / "job-radar.sqlite3")
            self.assertEqual(import_legacy_offers(database, root / "missing.json"), 0)


class JobRadarApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = JobRadarDatabase(Path(self.temporary_directory.name) / "api.sqlite3")
        self.server = JobRadarServer(("127.0.0.1", 0), JobRadarHandler)
        self.server.database = self.database
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def request_json(self, path: str, method: str = "GET", data: dict | None = None):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read())
            finally:
                error.close()

    def test_profile_and_offers_are_served_from_sqlite(self) -> None:
        status, saved_profile = self.request_json(
            "/api/profile",
            "PUT",
            {
                "first_name": "Ada",
                "preferences": {"desired_titles": ["Engineer"]},
                "experiences": [{"title": "Engineer", "company": "Example"}],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved_profile["experiences"][0]["company"], "Example")

        status, result = self.request_json(
            "/api/offers",
            "POST",
            {
                "title": "Python engineer",
                "url": "https://example.com/job/1",
                "score": 90,
                "reasons": ["Python skill"],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["id"], 1)

        status, offers = self.request_json("/api/offers")
        self.assertEqual(status, 200)
        self.assertEqual(offers[0]["title"], "Python engineer")
        self.assertEqual(offers[0]["score"], 90)

        status, profile = self.request_json("/api/profile")
        self.assertEqual(status, 200)
        self.assertEqual(profile["first_name"], "Ada")

    def test_invalid_offer_is_reported_as_bad_request(self) -> None:
        status, result = self.request_json(
            "/api/offers",
            "POST",
            {"title": "", "url": "https://example.com/job/1"},
        )

        self.assertEqual(status, 400)
        self.assertIn("title is required", result["error"])


if __name__ == "__main__":
    unittest.main()

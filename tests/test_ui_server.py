import json
import tempfile
import unittest
from pathlib import Path

from src.ui.server import load_recent_offers


class RecentOffersTests(unittest.TestCase):
    def test_returns_five_most_recent_offers(self) -> None:
        offers = [
            {"title": f"Offer {day}", "date_found": f"2026-11-{day:02d}T12:00:00+00:00"}
            for day in range(1, 9)
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.json"
            path.write_text(json.dumps(offers), encoding="utf-8")

            recent = load_recent_offers(path)

        self.assertEqual([offer["title"] for offer in recent], [
            "Offer 8", "Offer 7", "Offer 6", "Offer 5", "Offer 4",
        ])

    def test_missing_file_is_an_empty_feed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_recent_offers(Path(directory) / "missing.json"), [])

    def test_invalid_feed_shape_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.json"
            path.write_text('{"title": "not a list"}', encoding="utf-8")

            with self.assertRaises(ValueError):
                load_recent_offers(path)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = Path(__file__).resolve().parent
OFFERS_FILE = PROJECT_ROOT / "data" / "offers.json"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/profile.html": ("profile.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/profile.js": ("profile.js", "text/javascript; charset=utf-8"),
}


def _date_sort_value(offer: dict[str, Any]) -> float:
    value = offer.get("date_found") or offer.get("date_posted")
    if not isinstance(value, str):
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.timestamp()
    except ValueError:
        return float("-inf")


def load_recent_offers(path: Path = OFFERS_FILE) -> list[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as file:
            offers = json.load(file)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} contains invalid JSON: {error.msg}.") from error

    if not isinstance(offers, list):
        raise ValueError(f"{path} must contain a JSON array of offers.")
    if any(not isinstance(offer, dict) for offer in offers):
        raise ValueError(f"{path} must contain only JSON objects.")
    return sorted(offers, key=_date_sort_value, reverse=True)[:5]


class JobRadarHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/offers":
            self._send_offers()
            return

        static_file = STATIC_FILES.get(path)
        if static_file is None:
            self.send_error(404, "Not found")
            return

        filename, content_type = static_file
        try:
            content = (UI_ROOT / filename).read_bytes()
        except OSError as error:
            self.send_error(500, f"Could not read UI file: {error}")
            return
        self._send(content, content_type)

    def _send_offers(self) -> None:
        try:
            content = json.dumps(load_recent_offers(), ensure_ascii=False).encode("utf-8")
        except (OSError, ValueError) as error:
            self.send_error(500, str(error))
            return
        self._send(content, "application/json; charset=utf-8")

    def _send(self, content: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    OFFERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not OFFERS_FILE.exists():
        OFFERS_FILE.write_text("[]\n", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 8000), JobRadarHandler)
    print("Job Radar UI available at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Job Radar UI.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

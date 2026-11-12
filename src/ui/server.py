from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from src.storage.database import DEFAULT_DATABASE_PATH, JobRadarDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = Path(__file__).resolve().parent
OFFERS_FILE = PROJECT_ROOT / "data" / "offers.json"
DATABASE_FILE = DEFAULT_DATABASE_PATH
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/profile.html": ("profile.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/profile.js": ("profile.js", "text/javascript; charset=utf-8"),
}


def import_legacy_offers(database: JobRadarDatabase, path: Path = OFFERS_FILE) -> int:
    migration_key = "legacy_offers_json_imported"
    if database.get_metadata(migration_key) == "true":
        return 0
    try:
        with path.open(encoding="utf-8") as file:
            offers = json.load(file)
    except FileNotFoundError:
        return 0
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} contains invalid JSON: {error.msg}.") from error

    if not isinstance(offers, list):
        raise ValueError(f"{path} must contain a JSON array of offers.")
    if any(not isinstance(offer, dict) for offer in offers):
        raise ValueError(f"{path} must contain only JSON objects.")
    imported = sum(1 for offer in offers if database.save_offer(offer))
    database.set_metadata(migration_key, "true")
    return imported


class JobRadarServer(ThreadingHTTPServer):
    database: JobRadarDatabase


class JobRadarHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        server = cast(JobRadarServer, self.server)
        if path == "/api/offers":
            self._send_offers()
            return
        if path == "/api/profile":
            try:
                self._send_json(200, server.database.get_profile())
            except sqlite3.Error as error:
                self._send_json(500, {"error": f"Database error: {error}"})
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

    def do_PUT(self) -> None:
        if urlsplit(self.path).path != "/api/profile":
            self.send_error(404, "Not found")
            return
        try:
            profile = self._read_json_body()
            saved = cast(JobRadarServer, self.server).database.save_profile(profile)
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return
        except sqlite3.Error as error:
            self._send_json(500, {"error": f"Database error: {error}"})
            return
        self._send_json(200, saved)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/offers":
            self.send_error(404, "Not found")
            return
        try:
            offer = self._read_json_body()
            offer_id = cast(JobRadarServer, self.server).database.save_offer(offer)
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return
        except sqlite3.Error as error:
            self._send_json(500, {"error": f"Database error: {error}"})
            return
        self._send_json(201, {"id": offer_id})

    def _send_offers(self) -> None:
        try:
            offers = cast(JobRadarServer, self.server).database.list_recent_offers()
        except (ValueError, sqlite3.Error) as error:
            self._send_json(500, {"error": str(error)})
            return
        self._send_json(200, offers)

    def _read_json_body(self) -> Any:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length must be a positive integer.") from error
        if content_length <= 0 or content_length > 1024 * 1024:
            raise ValueError("Request body must be between 1 byte and 1 MiB.")
        try:
            return json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON: {error.msg}.") from error

    def _send_json(self, status: int, value: Any) -> None:
        content = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _send(self, content: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    database = JobRadarDatabase(DATABASE_FILE)
    imported = import_legacy_offers(database)
    server = JobRadarServer(("127.0.0.1", 8000), JobRadarHandler)
    server.database = database
    if imported:
        print(f"Imported {imported} legacy offer(s) from {OFFERS_FILE}.")
    print("Job Radar UI available at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Job Radar UI.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

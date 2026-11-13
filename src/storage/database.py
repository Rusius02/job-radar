from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "job_radar.sqlite3"

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    headline TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    linkedin_url TEXT NOT NULL DEFAULT '',
    portfolio_url TEXT NOT NULL DEFAULT '',
    resume_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_preferences (
    profile_id INTEGER PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    remote_only INTEGER CHECK (remote_only IN (0, 1) OR remote_only IS NULL),
    salary_min REAL CHECK (salary_min IS NULL OR salary_min >= 0),
    salary_currency TEXT NOT NULL DEFAULT 'EUR',
    desired_titles_json TEXT NOT NULL DEFAULT '[]',
    desired_locations_json TEXT NOT NULL DEFAULT '[]',
    keywords_json TEXT NOT NULL DEFAULT '[]',
    employment_types_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS profile_skills (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    proficiency TEXT NOT NULL DEFAULT '',
    years_experience REAL CHECK (years_experience IS NULL OR years_experience >= 0),
    UNIQUE (profile_id, name)
);

CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    employment_type TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    start_date TEXT,
    end_date TEXT,
    is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS educations (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    institution TEXT NOT NULL,
    degree TEXT NOT NULL DEFAULT '',
    field_of_study TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    start_date TEXT,
    end_date TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS certifications (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    issuer TEXT NOT NULL DEFAULT '',
    credential_id TEXT NOT NULL DEFAULT '',
    credential_url TEXT NOT NULL DEFAULT '',
    issue_date TEXT,
    expiry_date TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profile_languages (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    proficiency TEXT NOT NULL DEFAULT '',
    UNIQUE (profile_id, language)
);

CREATE TABLE IF NOT EXISTS profile_links (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    url TEXT NOT NULL,
    UNIQUE (profile_id, url)
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    client TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    start_date TEXT,
    end_date TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS project_skills (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    PRIMARY KEY (project_id, skill)
);

CREATE TABLE IF NOT EXISTS job_sites (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    terms_reviewed INTEGER NOT NULL DEFAULT 0 CHECK (terms_reviewed IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    organization TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL UNIQUE,
    application_url TEXT NOT NULL DEFAULT '',
    date_posted TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_remote INTEGER NOT NULL DEFAULT 0 CHECK (is_remote IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'saved', 'applied', 'dismissed')),
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS offer_locations (
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    location TEXT NOT NULL,
    PRIMARY KEY (offer_id, location)
);

CREATE TABLE IF NOT EXISTS offer_skills (
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    PRIMARY KEY (offer_id, skill)
);

CREATE TABLE IF NOT EXISTS offer_employment_types (
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    employment_type TEXT NOT NULL,
    PRIMARY KEY (offer_id, employment_type)
);

CREATE TABLE IF NOT EXISTS offer_matches (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    reasons_json TEXT NOT NULL DEFAULT '[]',
    analyzed_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, offer_id)
);

CREATE INDEX IF NOT EXISTS idx_offers_first_seen ON offers(first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_experiences_profile_order ON experiences(profile_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_educations_profile_order ON educations(profile_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_projects_profile_order ON projects(profile_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_job_sites_enabled ON job_sites(is_enabled);
"""

_PROFILE_TEXT_FIELDS = (
    "first_name",
    "last_name",
    "headline",
    "email",
    "phone",
    "location",
    "summary",
    "linkedin_url",
    "portfolio_url",
    "resume_url",
)
_SCHEMA_VERSION = 4


class JobRadarDatabase:
    """Small SQLite persistence layer for a single local Job Radar instance."""

    def __init__(self, path: Path | str = DEFAULT_DATABASE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version > _SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {current_version} is newer than supported "
                    f"version {_SCHEMA_VERSION}."
                )
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            now = _utc_now()
            connection.execute(
                "INSERT OR IGNORE INTO profiles (id, created_at, updated_at) VALUES (1, ?, ?)",
                (now, now),
            )
            connection.execute(
                "INSERT OR IGNORE INTO profile_preferences (profile_id) VALUES (1)"
            )
            connection.commit()

    def get_metadata(self, key: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row is not None else None

    def set_metadata(self, key: str, value: str) -> None:
        with self._connection() as connection, connection:
            connection.execute(
                """INSERT INTO app_metadata (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value),
            )

    def list_job_sites(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM job_sites ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
            return [_record(row, ("is_enabled", "terms_reviewed")) for row in rows]

    def add_job_site(
        self,
        name: str,
        url: str,
        *,
        terms_reviewed: bool = False,
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        site_name = _text(name)
        if not site_name:
            raise ValueError("Site name is required.")
        if len(site_name) > 120:
            raise ValueError("Site name cannot exceed 120 characters.")
        if not isinstance(terms_reviewed, bool) or not isinstance(is_enabled, bool):
            raise ValueError("terms_reviewed and is_enabled must be true or false.")
        normalized_url = _normalize_http_url(url)
        now = _utc_now()
        try:
            with self._connection() as connection, connection:
                cursor = connection.execute(
                    """INSERT INTO job_sites
                       (name, url, is_enabled, terms_reviewed, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        site_name,
                        normalized_url,
                        int(is_enabled),
                        int(terms_reviewed),
                        now,
                        now,
                    ),
                )
                site_id = cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise ValueError("This website is already in your list.") from error
        return self.get_job_site(site_id)

    def get_job_site(self, site_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM job_sites WHERE id = ?", (site_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Website {site_id} does not exist.")
            return _record(row, ("is_enabled", "terms_reviewed"))

    def update_job_site_enabled(self, site_id: int, is_enabled: bool) -> dict[str, Any]:
        if not isinstance(is_enabled, bool):
            raise ValueError("is_enabled must be true or false.")
        with self._connection() as connection, connection:
            cursor = connection.execute(
                "UPDATE job_sites SET is_enabled = ?, updated_at = ? WHERE id = ?",
                (int(is_enabled), _utc_now(), site_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Website {site_id} does not exist.")
        return self.get_job_site(site_id)

    def delete_job_site(self, site_id: int) -> bool:
        with self._connection() as connection, connection:
            cursor = connection.execute("DELETE FROM job_sites WHERE id = ?", (site_id,))
            return cursor.rowcount > 0

    def get_profile(self, profile_id: int = 1) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN")
            profile_row = connection.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            if profile_row is None:
                raise ValueError(f"Profile {profile_id} does not exist.")
            profile = {field: profile_row[field] for field in _PROFILE_TEXT_FIELDS}
            profile["id"] = profile_id
            profile["created_at"] = profile_row["created_at"]
            profile["updated_at"] = profile_row["updated_at"]
            preference = connection.execute(
                "SELECT * FROM profile_preferences WHERE profile_id = ?", (profile_id,)
            ).fetchone()
            profile["preferences"] = {
                "remote_only": None if preference["remote_only"] is None else bool(preference["remote_only"]),
                "salary_min": preference["salary_min"],
                "salary_currency": preference["salary_currency"],
                "desired_titles": _json_list(preference["desired_titles_json"]),
                "desired_locations": _json_list(preference["desired_locations_json"]),
                "keywords": _json_list(preference["keywords_json"]),
                "employment_types": _json_list(preference["employment_types_json"]),
            }
            profile["skills"] = [
                dict(row)
                for row in connection.execute(
                    """SELECT name, proficiency, years_experience
                       FROM profile_skills WHERE profile_id = ? ORDER BY id""",
                    (profile_id,),
                )
            ]
            profile["experiences"] = [
                _record(row, ("is_current",))
                for row in connection.execute(
                    "SELECT * FROM experiences WHERE profile_id = ? ORDER BY sort_order, id",
                    (profile_id,),
                )
            ]
            profile["education"] = [
                _record(row)
                for row in connection.execute(
                    "SELECT * FROM educations WHERE profile_id = ? ORDER BY sort_order, id",
                    (profile_id,),
                )
            ]
            profile["certifications"] = [
                _record(row)
                for row in connection.execute(
                    "SELECT * FROM certifications WHERE profile_id = ? ORDER BY sort_order, id",
                    (profile_id,),
                )
            ]
            profile["languages"] = [
                dict(row)
                for row in connection.execute(
                    "SELECT language, proficiency FROM profile_languages WHERE profile_id = ? ORDER BY id",
                    (profile_id,),
                )
            ]
            profile["links"] = [
                dict(row)
                for row in connection.execute(
                    "SELECT label, url FROM profile_links WHERE profile_id = ? ORDER BY id",
                    (profile_id,),
                )
            ]
            projects = [
                _record(row)
                for row in connection.execute(
                    "SELECT * FROM projects WHERE profile_id = ? ORDER BY sort_order, id",
                    (profile_id,),
                )
            ]
            if projects:
                placeholders = ", ".join("?" for _ in projects)
                project_skills: dict[int, list[str]] = {
                    project["id"]: [] for project in projects
                }
                for row in connection.execute(
                    f"""SELECT project_id, skill FROM project_skills
                        WHERE project_id IN ({placeholders}) ORDER BY rowid""",
                    [project["id"] for project in projects],
                ):
                    project_skills[row["project_id"]].append(row["skill"])
                for project in projects:
                    project["skills"] = project_skills[project["id"]]
            profile["projects"] = projects
            return profile

    def save_profile(self, profile: dict[str, Any], profile_id: int = 1) -> dict[str, Any]:
        if not isinstance(profile, dict):
            raise ValueError("Profile must be a JSON object.")

        preferences = profile.get("preferences", {})
        if not isinstance(preferences, dict):
            raise ValueError("Profile preferences must be an object.")
        now = _utc_now()
        text_values = {field: _text(profile.get(field)) for field in _PROFILE_TEXT_FIELDS}
        remote_only = preferences.get("remote_only")
        if remote_only is not None and not isinstance(remote_only, bool):
            raise ValueError("preferences.remote_only must be true, false or null.")
        salary_min = preferences.get("salary_min")
        if salary_min is not None:
            try:
                salary_min = float(salary_min)
            except (TypeError, ValueError) as error:
                raise ValueError("preferences.salary_min must be a non-negative number.") from error
            if not math.isfinite(salary_min) or salary_min < 0:
                raise ValueError("preferences.salary_min must be a non-negative number.")

        with self._connection() as connection, connection:
            connection.execute(
                """UPDATE profiles SET first_name = :first_name, last_name = :last_name,
                   headline = :headline, email = :email, phone = :phone, location = :location,
                   summary = :summary, linkedin_url = :linkedin_url, portfolio_url = :portfolio_url,
                   resume_url = :resume_url, updated_at = :updated_at WHERE id = :id""",
                {**text_values, "updated_at": now, "id": profile_id},
            )
            if connection.total_changes == 0:
                raise ValueError(f"Profile {profile_id} does not exist.")
            connection.execute(
                """UPDATE profile_preferences SET remote_only = ?, salary_min = ?,
                   salary_currency = ?, desired_titles_json = ?, desired_locations_json = ?,
                   keywords_json = ?, employment_types_json = ? WHERE profile_id = ?""",
                (
                    None if remote_only is None else int(remote_only),
                    salary_min,
                    _text(preferences.get("salary_currency")) or "EUR",
                    _json_dump(_string_list(preferences.get("desired_titles"))),
                    _json_dump(_string_list(preferences.get("desired_locations"))),
                    _json_dump(_string_list(preferences.get("keywords"))),
                    _json_dump(_string_list(preferences.get("employment_types"))),
                    profile_id,
                ),
            )
            self._replace_profile_collection(
                connection,
                "profile_skills",
                profile_id,
                profile.get("skills", []),
                ("name", "proficiency", "years_experience"),
            )
            for table, key, fields in (
                ("experiences", "experiences", ("title", "company", "location", "employment_type",
                                                 "description", "start_date", "end_date", "is_current", "sort_order")),
                ("educations", "education", ("institution", "degree", "field_of_study", "location",
                                              "description", "start_date", "end_date", "sort_order")),
                ("certifications", "certifications", ("name", "issuer", "credential_id", "credential_url",
                                                       "issue_date", "expiry_date", "sort_order")),
                ("profile_languages", "languages", ("language", "proficiency")),
                ("profile_links", "links", ("label", "url")),
            ):
                self._replace_profile_collection(
                    connection, table, profile_id, profile.get(key, []), fields
                )
            self._replace_projects(connection, profile_id, profile.get("projects", []))

        return self.get_profile(profile_id)

    @staticmethod
    def _replace_profile_collection(
        connection: sqlite3.Connection,
        table: str,
        profile_id: int,
        items: Any,
        fields: tuple[str, ...],
    ) -> None:
        if not isinstance(items, list):
            raise ValueError(f"Profile field {table} must be an array.")
        connection.execute(f"DELETE FROM {table} WHERE profile_id = ?", (profile_id,))
        if not items:
            return
        columns = ", ".join(("profile_id", *fields))
        placeholders = ", ".join("?" for _ in range(len(fields) + 1))
        required_fields = {
            "profile_skills": {"name"},
            "experiences": {"title"},
            "educations": {"institution"},
            "certifications": {"name"},
            "profile_languages": {"language"},
            "profile_links": {"label", "url"},
        }[table]
        rows = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"Every item in {table} must be an object.")
            values = [profile_id]
            for field in fields:
                value = item.get(field)
                if field == "is_current":
                    if value is not None and not isinstance(value, bool):
                        raise ValueError("is_current must be true or false.")
                    value = int(value is True)
                elif field == "sort_order":
                    value = _integer(value)
                elif field == "years_experience" and value is not None:
                    try:
                        value = float(value)
                    except (TypeError, ValueError) as error:
                        raise ValueError("years_experience must be a non-negative number.") from error
                    if not math.isfinite(value) or value < 0:
                        raise ValueError("years_experience must be a finite, non-negative number.")
                elif field in {"start_date", "end_date", "issue_date", "expiry_date"}:
                    value = _text(value) if value is not None else None
                else:
                    value = _text(value)
                    if field in required_fields and not value:
                        raise ValueError(f"{table}.{field} is required.")
                values.append(value)
            rows.append(tuple(values))
        connection.executemany(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", rows
        )

    @staticmethod
    def _replace_projects(
        connection: sqlite3.Connection, profile_id: int, projects: Any
    ) -> None:
        if not isinstance(projects, list):
            raise ValueError("Profile field projects must be an array.")
        connection.execute("DELETE FROM projects WHERE profile_id = ?", (profile_id,))
        for sort_order, project in enumerate(projects):
            if not isinstance(project, dict):
                raise ValueError("Every project must be an object.")
            name = _text(project.get("name"))
            if not name:
                raise ValueError("projects.name is required.")
            cursor = connection.execute(
                """INSERT INTO projects
                   (profile_id, name, role, client, description, url, start_date, end_date, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile_id,
                    name,
                    _text(project.get("role")),
                    _text(project.get("client")),
                    _text(project.get("description")),
                    _text(project.get("url")),
                    _text(project.get("start_date")) or None,
                    _text(project.get("end_date")) or None,
                    _integer(project.get("sort_order", sort_order)),
                ),
            )
            skills = _string_list(project.get("skills"))
            if skills:
                connection.executemany(
                    "INSERT INTO project_skills (project_id, skill) VALUES (?, ?)",
                    [(cursor.lastrowid, skill) for skill in skills],
                )

    def save_offer(self, offer: dict[str, Any], profile_id: int = 1) -> int:
        if not isinstance(offer, dict):
            raise ValueError("Offer must be a JSON object.")
        title = _text(offer.get("title"))
        source_url = _text(offer.get("source_url") or offer.get("url"))
        if not title:
            raise ValueError("Offer title is required.")
        if not source_url:
            raise ValueError("Offer source_url or url is required.")

        date_posted = _normalize_date(offer.get("date_posted"))
        discovered = _normalize_date(offer.get("date_found")) or _utc_now()
        now = _utc_now()
        application_url = _text(offer.get("application_url")) or source_url
        remote_value = offer.get("is_remote", False)
        if not isinstance(remote_value, bool):
            raise ValueError("Offer is_remote must be true or false.")
        status = _text(offer.get("status")) or "new"
        if status not in {"new", "saved", "applied", "dismissed"}:
            raise ValueError("Offer status must be new, saved, applied or dismissed.")

        with self._connection() as connection, connection:
            updates = [
                "title = excluded.title",
                "last_seen_at = excluded.last_seen_at",
            ]
            updateable_fields = {
                "description": "description",
                "organization": "organization",
                "company": "organization",
                "source_name": "source_name",
                "application_url": "application_url",
                "date_posted": "date_posted",
                "is_remote": "is_remote",
                "status": "status",
                "notes": "notes",
            }
            updated_columns: set[str] = set()
            for input_field, column in updateable_fields.items():
                if input_field in offer and column not in updated_columns:
                    updates.append(f"{column} = excluded.{column}")
                    updated_columns.add(column)
            connection.execute(
                f"""INSERT INTO offers
                   (title, description, organization, source_name, source_url, application_url,
                    date_posted, first_seen_at, last_seen_at, is_remote, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_url) DO UPDATE SET {", ".join(updates)}""",
                (
                    title,
                    _text(offer.get("description")),
                    _text(offer.get("organization") or offer.get("company")),
                    _text(offer.get("source_name")),
                    source_url,
                    application_url,
                    date_posted,
                    discovered,
                    now,
                    int(remote_value),
                    status,
                    _text(offer.get("notes")),
                ),
            )
            offer_id = connection.execute(
                "SELECT id FROM offers WHERE source_url = ?", (source_url,)
            ).fetchone()["id"]
            for table, field in (
                ("offer_locations", "locations"),
                ("offer_skills", "skills"),
                ("offer_employment_types", "employment_type"),
            ):
                if field not in offer:
                    continue
                connection.execute(f"DELETE FROM {table} WHERE offer_id = ?", (offer_id,))
                values = _string_list(offer.get(field))
                if values:
                    value_column = {
                        "offer_locations": "location",
                        "offer_skills": "skill",
                        "offer_employment_types": "employment_type",
                    }[table]
                    connection.executemany(
                        f"INSERT INTO {table} (offer_id, {value_column}) VALUES (?, ?)",
                        [(offer_id, value) for value in values],
                    )

            if "score" in offer and offer["score"] is not None:
                score = offer["score"]
                if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
                    raise ValueError("Offer score must be an integer between 0 and 100.")
                reasons = _string_list(offer.get("reasons"))
                connection.execute(
                    """INSERT INTO offer_matches
                       (profile_id, offer_id, score, reasons_json, analyzed_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(profile_id, offer_id) DO UPDATE SET score = excluded.score,
                        reasons_json = excluded.reasons_json, analyzed_at = excluded.analyzed_at""",
                    (profile_id, offer_id, score, _json_dump(reasons), now),
                )
            return int(offer_id)

    def list_recent_offers(self, limit: int = 5, profile_id: int = 1) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit cannot be negative.")
        with self._connection() as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                """SELECT o.*, m.score, m.reasons_json
                   FROM offers AS o
                   LEFT JOIN offer_matches AS m
                    ON m.offer_id = o.id AND m.profile_id = ?
                   ORDER BY o.first_seen_at DESC, o.id DESC LIMIT ?""",
                (profile_id, limit),
            ).fetchall()
            offers = [_record(row, ("is_remote",)) for row in rows]
            for offer in offers:
                offer["url"] = offer["source_url"]
                offer["date_found"] = offer.pop("first_seen_at")
                offer.pop("last_seen_at", None)
                offer["reasons"] = _json_list(offer.pop("reasons_json", None))
            ids = [offer["id"] for offer in offers]
            if ids:
                placeholders = ", ".join("?" for _ in ids)
                for table, field, output_field in (
                    ("offer_locations", "location", "locations"),
                    ("offer_skills", "skill", "skills"),
                    ("offer_employment_types", "employment_type", "employment_type"),
                ):
                    grouped: dict[int, list[str]] = {offer_id: [] for offer_id in ids}
                    related = connection.execute(
                        f"SELECT offer_id, {field} FROM {table} WHERE offer_id IN ({placeholders}) ORDER BY rowid",
                        ids,
                    )
                    for row in related:
                        grouped[row["offer_id"]].append(row[field])
                    for offer in offers:
                        offer[output_field] = grouped[offer["id"]]
            return offers


def _record(row: sqlite3.Row, boolean_fields: tuple[str, ...] = ()) -> dict[str, Any]:
    result = dict(row)
    for field in boolean_fields:
        result[field] = bool(result[field])
    return result


def _text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        raise ValueError("Text fields must be strings or numbers.")
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (tuple, list)):
        raise ValueError("Expected an array of strings.")
    result = []
    for item in value:
        text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _json_dump(value: list[str]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def _integer(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError("Sort order must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Sort order must be an integer.") from error


def _normalize_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Dates must be ISO 8601 strings.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid ISO 8601 date: {value!r}.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _normalize_http_url(value: Any) -> str:
    url = _text(value)
    if not url or len(url) > 2048:
        raise ValueError("Website URL must be between 1 and 2048 characters.")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("Website URL is invalid.") from error
    if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
        raise ValueError("Website URL must use http or https and include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Website URLs containing credentials are not allowed.")
    netloc = hostname.casefold()
    if ":" in netloc and not netloc.startswith("["):
        netloc = f"[{netloc}]"
    if port is not None:
        netloc = f"{netloc}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit(
        (parsed.scheme.casefold(), netloc, path, parsed.query, "")
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

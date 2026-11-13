from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


class JobPageAnalysisError(ValueError):
    """Raised when the requested analysis parameters are invalid."""


@dataclass(frozen=True)
class JobProfile:
    desired_titles: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    remote_only: bool | None = None


@dataclass(frozen=True)
class JobOffer:
    title: str
    description: str
    organization: str
    locations: tuple[str, ...]
    url: str
    date_posted: str
    employment_type: tuple[str, ...]
    skills: tuple[str, ...]
    is_remote: bool


@dataclass(frozen=True)
class JobMatch:
    offer: JobOffer
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class JobAnalysisResult:
    matches: tuple[JobMatch, ...]
    offers_found: int
    warnings: tuple[str, ...]


class _JsonLdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.documents: list[str] = []
        self._active = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "script":
            return
        attributes = {key.casefold(): value for key, value in attrs}
        if (attributes.get("type") or "").split(";", 1)[0].strip().casefold() == "application/ld+json":
            self._active = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._active:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._active:
            self.documents.append("".join(self._parts))
            self._parts = []
            self._active = False


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class JobAnalyzer:
    """Extract Schema.org JobPosting records and rank them against a profile."""

    def analyze(
        self,
        html: str,
        profile: JobProfile,
        *,
        page_url: str = "",
        top_n: int = 10,
    ) -> JobAnalysisResult:
        if top_n < 0:
            raise JobPageAnalysisError("top_n cannot be negative.")

        collector = _JsonLdCollector()
        collector.feed(html)

        offers: list[JobOffer] = []
        warnings: list[str] = []
        seen: set[tuple[str, str, str]] = set()
        for document in collector.documents:
            try:
                data = json.loads(document)
            except json.JSONDecodeError as error:
                warnings.append(f"An invalid JSON-LD block was ignored: {error.msg}.")
                continue

            for posting in self._find_postings(data):
                offer = self._to_offer(posting, page_url)
                key = (_normalize(offer.url), _normalize(offer.title), _normalize(offer.organization))
                if key not in seen:
                    offers.append(offer)
                    seen.add(key)

        if not offers and not warnings:
            warnings.append(
                "No Schema.org JobPosting data was found; this page may need a site-specific extractor."
            )

        ranked = [self._score(offer, profile) for offer in offers]
        ranked.sort(key=lambda match: (-match.score, _normalize(match.offer.title)))
        return JobAnalysisResult(tuple(ranked[:top_n]), len(offers), tuple(warnings))

    @classmethod
    def _find_postings(cls, value: Any):
        if isinstance(value, list):
            for item in value:
                yield from cls._find_postings(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(_normalize(str(item).rsplit("/", 1)[-1]) == "jobposting" for item in types):
                yield value
                return
            for child in value.values():
                yield from cls._find_postings(child)

    @classmethod
    def _to_offer(cls, posting: dict[str, Any], page_url: str) -> JobOffer:
        organization = posting.get("hiringOrganization", {})
        if isinstance(organization, dict):
            organization = organization.get("name", "")

        raw_types = posting.get("employmentType", ())
        if isinstance(raw_types, str):
            raw_types = (raw_types,)
        elif not isinstance(raw_types, (list, tuple)):
            raw_types = ()

        locations: list[str] = []
        raw_locations = posting.get("jobLocation", ())
        if not isinstance(raw_locations, (list, tuple)):
            raw_locations = (raw_locations,)
        for location in raw_locations:
            if isinstance(location, dict):
                address = location.get("address", location)
                if isinstance(address, dict):
                    parts = [
                        _string(address.get(key))
                        for key in ("addressLocality", "addressRegion", "addressCountry")
                    ]
                    value = ", ".join(part for part in parts if part)
                else:
                    value = _string(address)
            else:
                value = _string(location)
            if value and value not in locations:
                locations.append(value)

        raw_skills = posting.get("skills", ())
        if isinstance(raw_skills, str):
            raw_skills = (raw_skills,)
        elif not isinstance(raw_skills, (list, tuple)):
            raw_skills = ()

        return JobOffer(
            title=_string(posting.get("title")) or "Untitled position",
            description=_plain_text(_string(posting.get("description"))),
            organization=_string(organization),
            locations=tuple(locations),
            url=_string(posting.get("url")) or page_url,
            date_posted=_string(posting.get("datePosted")),
            employment_type=tuple(filter(None, (_string(item) for item in raw_types))),
            skills=tuple(filter(None, (_string(item) for item in raw_skills))),
            is_remote=_normalize(_string(posting.get("jobLocationType"))) == "telecommute",
        )

    @classmethod
    def _score(cls, offer: JobOffer, profile: JobProfile) -> JobMatch:
        score_parts: list[int] = []
        max_score = 0
        reasons: list[str] = []

        title_match = _best_term_match(profile.desired_titles, offer.title)
        if title_match is not None:
            max_score += 40
            score_parts.append(40 if title_match[1] else 0)
            if title_match[1]:
                reasons.append(f"Title matches: {title_match[0]}")

        skill_matches = _matching_terms(profile.skills, " ".join((offer.title, offer.description, *offer.skills)))
        if profile.skills:
            max_score += 35
            score_parts.append(35 * len(skill_matches) // len(profile.skills))
            if skill_matches:
                reasons.append(f"Skills found: {', '.join(skill_matches)}")

        location_match = _best_term_match(profile.locations, " ".join(offer.locations))
        if location_match is not None:
            max_score += 15
            score_parts.append(15 if location_match[1] else 0)
            if location_match[1]:
                reasons.append(f"Location matches: {location_match[0]}")

        keyword_matches = _matching_terms(profile.keywords, " ".join((offer.title, offer.description)))
        if profile.keywords:
            max_score += 10
            score_parts.append(10 * len(keyword_matches) // len(profile.keywords))
            if keyword_matches:
                reasons.append(f"Keywords found: {', '.join(keyword_matches)}")

        if profile.remote_only is not None:
            is_match = offer.is_remote if profile.remote_only else True
            max_score += 10
            score_parts.append(10 if is_match else 0)
            if is_match and offer.is_remote:
                reasons.append("Remote work")

        score = round(sum(score_parts) * 100 / max_score) if max_score else 0
        return JobMatch(offer, score, tuple(reasons))


def _string(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("@value", value.get("name", ""))
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    return ""


def _plain_text(value: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(value)
    return " ".join(" ".join(extractor.parts).split())


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", without_accents).split())


def _matching_terms(terms: tuple[str, ...], text: str) -> list[str]:
    normalized_text = f" {_normalize(text)} "
    return [
        term
        for term in terms
        if _normalize(term) and f" {_normalize(term)} " in normalized_text
    ]


def _best_term_match(terms: tuple[str, ...], text: str) -> tuple[str, bool] | None:
    if not terms:
        return None
    matched = _matching_terms(terms, text)
    return (matched[0], True) if matched else (terms[0], False)

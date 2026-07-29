"""Exact and fuzzy duplicate matching helpers."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from openleadkit.models import Business, DuplicateMatchType
from openleadkit.schemas import BusinessRecord


@dataclass(frozen=True)
class DuplicateMatch:
    match_type: DuplicateMatchType
    similarity_score: float
    explanation: str


def fuzzy_name_score(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def exact_match(record: BusinessRecord, candidate: Business) -> DuplicateMatch | None:
    if record.osm_type == candidate.osm_type and record.osm_id == candidate.osm_id:
        return DuplicateMatch(DuplicateMatchType.OSM_IDENTITY, 1, "Same OpenStreetMap object")
    if record.normalized_domain and record.normalized_domain == candidate.normalized_domain:
        return DuplicateMatch(DuplicateMatchType.DOMAIN, 1, "Same website domain")
    if record.normalized_phone and record.normalized_phone == candidate.normalized_phone:
        return DuplicateMatch(DuplicateMatchType.PHONE, 1, "Same normalized phone number")
    return None


def potential_name_match(
    record: BusinessRecord, candidate: Business, threshold: float
) -> DuplicateMatch | None:
    same_area = bool(
        (record.city and candidate.city and record.city.casefold() == candidate.city.casefold())
        or (
            record.district
            and candidate.district
            and record.district.casefold() == candidate.district.casefold()
        )
    )
    if not same_area:
        return None
    score = fuzzy_name_score(record.normalized_name, candidate.normalized_name)
    if score < threshold:
        return None
    return DuplicateMatch(
        DuplicateMatchType.NAME_CITY,
        score,
        f"Similar name ({score:.0%}) in the same city or district",
    )


def canonical_pair(left_id: object, right_id: object) -> tuple[object, object]:
    return tuple(sorted((left_id, right_id), key=str))  # type: ignore[return-value]

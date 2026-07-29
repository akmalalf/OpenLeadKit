"""Transparent, non-AI lead suggestion score."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualificationInputs:
    has_website: bool
    website_available: bool | None
    has_phone: bool
    has_public_email: bool
    mobile_viewport_found: bool | None
    https_enabled: bool | None
    contact_page_found: bool
    complete_address: bool
    search_count: int


@dataclass(frozen=True)
class ScoreSuggestion:
    score: int
    explanation: tuple[str, ...]


def calculate_suggestion(inputs: QualificationInputs) -> ScoreSuggestion:
    score = 0
    reasons: list[str] = []
    signals = (
        (not inputs.has_website, 20, "No website URL is available"),
        (inputs.website_available is False, 15, "The website was unavailable when checked"),
        (inputs.has_phone, 15, "A public phone number is available"),
        (inputs.has_public_email, 15, "A public business email is available"),
        (inputs.mobile_viewport_found is False, 10, "No mobile viewport was found"),
        (inputs.https_enabled is False, 10, "The website does not use HTTPS"),
        (inputs.contact_page_found, 5, "A contact page was found"),
        (inputs.complete_address, 5, "The address is sufficiently complete"),
        (inputs.search_count > 1, 5, "The business appeared in more than one search"),
    )
    for condition, points, reason in signals:
        if condition:
            score += points
            reasons.append(f"+{points}: {reason}")
    return ScoreSuggestion(score=min(score, 100), explanation=tuple(reasons))

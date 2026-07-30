"""Validation and normalization for manual lead-review edits."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from openleadkit.services.normalization import (
    normalize_instagram,
    normalize_phone,
    normalize_url,
    normalize_whitespace,
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INSTAGRAM_PATTERN = re.compile(r"^[A-Za-z0-9._]{1,30}$")


class LeadReviewDetails(BaseModel):
    """Editable business details submitted with a review decision."""

    business_name: str = Field(min_length=1, max_length=500)
    website_url: str | None = Field(default=None, max_length=2_048)
    phone: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=320)
    instagram: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=2_000)
    city: str | None = Field(default=None, max_length=500)
    district: str | None = Field(default=None, max_length=500)
    province: str | None = Field(default=None, max_length=500)
    postcode: str | None = Field(default=None, max_length=32)
    opening_hours: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5_000)

    @field_validator(
        "business_name",
        "website_url",
        "phone",
        "email",
        "instagram",
        "address",
        "city",
        "district",
        "province",
        "postcode",
        "opening_hours",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_whitespace(value)
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_url(value)
        if normalized is None:
            raise ValueError("Enter a valid HTTP or HTTPS website URL")
        return normalized

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None and normalize_phone(value) is None:
            raise ValueError("Enter a phone number containing digits")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and EMAIL_PATTERN.fullmatch(value) is None:
            raise ValueError("Enter a valid public business email address")
        return value

    @field_validator("instagram")
    @classmethod
    def validate_instagram(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_instagram(value)
        if normalized is None or INSTAGRAM_PATTERN.fullmatch(normalized) is None:
            raise ValueError("Enter a valid Instagram username or profile URL")
        return normalized

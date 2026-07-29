"""Validated business discovery schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class CategoryTag(BaseModel):
    model_config = {"extra": "forbid"}

    amenity: str | None = None
    healthcare: str | None = None
    shop: str | None = None
    craft: str | None = None
    office: str | None = None
    tourism: str | None = None
    leisure: str | None = None
    beauty: str | None = None
    hairdresser: str | None = None

    @model_validator(mode="after")
    def require_tag(self) -> CategoryTag:
        if not any(value for value in self.model_dump().values()):
            raise ValueError("A category mapping requires at least one tag")
        return self


class Category(BaseModel):
    model_config = {"extra": "forbid"}

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    label: str = Field(min_length=2, max_length=160)
    tags: list[CategoryTag] = Field(min_length=1)


class BoundingBox(BaseModel):
    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def validate_order_and_size(self) -> BoundingBox:
        if self.south >= self.north or self.west >= self.east:
            raise ValueError("The bounding-box coordinate order is invalid")
        if self.north - self.south > 5 or self.east - self.west > 5:
            raise ValueError("The bounding box is too large; the maximum is 5° per side")
        return self

    @property
    def query_value(self) -> str:
        return f"{self.south:.7f},{self.west:.7f},{self.north:.7f},{self.east:.7f}"

    @property
    def approximate_area_km2(self) -> float:
        width = (self.east - self.west) * 111
        height = (self.north - self.south) * 111
        return abs(width * height)


class BusinessRecord(BaseModel):
    osm_type: str = Field(pattern=r"^(node|way|relation)$")
    osm_id: int = Field(gt=0)
    business_name: str = Field(min_length=1, max_length=500)
    normalized_name: str
    category_key: str
    category_label: str
    city: str | None = None
    district: str | None = None
    province: str | None = None
    postcode: str | None = None
    country_code: str | None = None
    address: str | None = None
    source_url: str
    website_url: str | None = None
    normalized_domain: str | None = None
    phone: str | None = None
    normalized_phone: str | None = None
    email: str | None = None
    instagram: str | None = None
    opening_hours: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    raw_element: dict[str, Any]

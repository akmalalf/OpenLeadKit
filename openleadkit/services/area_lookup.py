"""One-off, cached-compatible Nominatim area lookup."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from openleadkit.config import Settings
from openleadkit.exceptions import AreaLookupError
from openleadkit.models import AreaCache
from openleadkit.schemas import BoundingBox

_last_request_at = 0.0


@dataclass(frozen=True)
class AreaResult:
    display_name: str
    bounding_box: BoundingBox
    raw_response: dict[str, Any]


class AreaLookupClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            timeout=settings.http_read_timeout_seconds,
            headers={"User-Agent": f"{settings.http_user_agent} ({settings.app_project_url})"},
        )

    def search(self, query: str, *, country_codes: str | None = None) -> list[AreaResult]:
        global _last_request_at
        query = " ".join(query.split())
        if not query or len(query) > 300:
            raise AreaLookupError("The area name is invalid")
        normalized_country_codes: str | None = None
        if country_codes:
            codes = [code.strip().casefold() for code in country_codes.split(",") if code.strip()]
            if not codes or any(not re.fullmatch(r"[a-z]{2}", code) for code in codes):
                raise AreaLookupError(
                    "Country codes must be comma-separated ISO 3166-1 alpha-2 codes"
                )
            normalized_country_codes = ",".join(dict.fromkeys(codes))
        wait = 1 - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        params: dict[str, str | int] = {
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "addressdetails": 1,
        }
        if normalized_country_codes:
            params["countrycodes"] = normalized_country_codes
        try:
            response = self.client.get(
                f"{str(self.settings.nominatim_api_url).rstrip('/')}/search", params=params
            )
            _last_request_at = time.monotonic()
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AreaLookupError("Area search failed") from exc
        if not isinstance(payload, list):
            raise AreaLookupError("The area-search response is invalid")
        results: list[AreaResult] = []
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("boundingbox"), list):
                continue
            try:
                south, north, west, east = (float(value) for value in item["boundingbox"])
                bbox = BoundingBox(south=south, west=west, north=north, east=east)
                results.append(
                    AreaResult(
                        display_name=str(item.get("display_name", query)),
                        bounding_box=bbox,
                        raw_response=item,
                    )
                )
            except (TypeError, ValueError):
                continue
        return results


def cache_selected_area(
    session: Session,
    query: str,
    result: AreaResult,
    *,
    country_codes: str | None = None,
    provider: str = "Nominatim",
) -> None:
    normalized_query = _area_cache_key(query, country_codes)
    bbox = result.bounding_box
    values = {
        "query": query,
        "normalized_query": normalized_query,
        "display_name": result.display_name,
        "south": bbox.south,
        "west": bbox.west,
        "north": bbox.north,
        "east": bbox.east,
        "provider": provider,
        "raw_response": result.raw_response,
        "expires_at": datetime.now(UTC) + timedelta(days=30),
    }
    session.execute(
        insert(AreaCache)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_area_query_provider",
            set_={key: value for key, value in values.items() if key != "normalized_query"},
        )
    )


def cached_area(
    session: Session,
    query: str,
    *,
    country_codes: str | None = None,
    provider: str = "Nominatim",
) -> AreaResult | None:
    normalized_query = _area_cache_key(query, country_codes)
    cached = session.scalar(
        select(AreaCache).where(
            AreaCache.normalized_query == normalized_query,
            AreaCache.provider == provider,
            AreaCache.expires_at > datetime.now(UTC),
        )
    )
    if cached is None:
        return None
    return AreaResult(
        display_name=cached.display_name,
        bounding_box=BoundingBox(
            south=cached.south,
            west=cached.west,
            north=cached.north,
            east=cached.east,
        ),
        raw_response=cached.raw_response,
    )


def _area_cache_key(query: str, country_codes: str | None) -> str:
    normalized_query = " ".join(query.split()).casefold()
    normalized_codes = ",".join(
        code.strip().casefold() for code in (country_codes or "").split(",") if code.strip()
    )
    return f"{normalized_query}|countries:{normalized_codes}"

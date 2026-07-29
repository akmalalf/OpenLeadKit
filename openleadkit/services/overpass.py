"""Safe Overpass query generation and request client."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from time import sleep
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from openleadkit.config import Settings
from openleadkit.exceptions import OverpassError, RateLimitError
from openleadkit.schemas import BoundingBox, Category
from openleadkit.services.normalization import extract_osm_element

logger = logging.getLogger(__name__)
TEMPORARY_STATUSES = {429, 500, 502, 503, 504}


def escape_overpass_value(value: str) -> str:
    if len(value) > 200:
        raise ValueError("The query value is too long")
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def build_overpass_query(
    category: Category,
    bbox: BoundingBox,
    maximum_results: int,
    *,
    require_phone: bool = False,
    require_website: bool = False,
) -> str:
    if maximum_results < 1 or maximum_results > 5_000:
        raise ValueError("The result limit is invalid")
    selectors: list[str] = []
    suffix = ""
    if require_phone:
        suffix += '[~"^(phone|contact:phone)$"~"."]'
    if require_website:
        suffix += '[~"^(website|contact:website)$"~"."]'
    for tag_set in category.tags:
        conditions = "".join(
            f'["{escape_overpass_value(key)}"="{escape_overpass_value(value)}"]'
            for key, value in tag_set.model_dump(exclude_none=True).items()
        )
        for osm_type in ("node", "way", "relation"):
            selectors.append(f"  {osm_type}{conditions}{suffix}({bbox.query_value});")
    return (
        f"[out:json][timeout:60];\n(\n{chr(10).join(selectors)}\n);\n"
        f"out center tags {maximum_results};"
    )


def query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OverpassResult:
    records: list[Any]
    raw_metadata: dict[str, Any]
    received: int


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After")
    if not value:
        return 0
    try:
        return min(float(value), 60)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value) - parsedate_to_datetime(response.headers["Date"])
            return max(0, min(delay.total_seconds(), 60))
        except (KeyError, TypeError, ValueError):
            return 0


class OverpassClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=settings.http_connect_timeout_seconds,
                read=settings.http_read_timeout_seconds,
                write=settings.http_connect_timeout_seconds,
                pool=settings.http_connect_timeout_seconds,
            ),
            headers={
                "User-Agent": f"{settings.http_user_agent} ({settings.app_project_url})",
                "Accept": "application/json",
            },
        )

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RateLimitError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def execute(self, query: str, category: Category) -> OverpassResult:
        try:
            with self.client.stream(
                "POST", str(self.settings.overpass_api_url), data={"data": query}
            ) as response:
                if response.status_code in TEMPORARY_STATUSES:
                    delay = _retry_after_seconds(response)
                    if delay:
                        sleep(delay)
                    raise RateLimitError(
                        f"Overpass is temporarily unavailable: HTTP {response.status_code}"
                    )
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.settings.http_max_response_bytes:
                        raise OverpassError("The Overpass response exceeds the size limit")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise OverpassError("The Overpass request failed") from exc
        try:
            payload = json.loads(b"".join(chunks))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OverpassError("The Overpass response is not valid JSON") from exc
        elements = payload.get("elements")
        if not isinstance(elements, list):
            raise OverpassError("The Overpass response does not contain an elements list")
        records = [
            record
            for element in elements
            if isinstance(element, dict)
            if (record := extract_osm_element(element, category)) is not None
        ]
        return OverpassResult(
            records=records,
            raw_metadata={
                "generator": payload.get("generator"),
                "osm3s": payload.get("osm3s", {}),
                "response_bytes": size,
            },
            received=len(elements),
        )

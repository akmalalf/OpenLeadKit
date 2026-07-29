"""Pure normalization and OpenStreetMap extraction functions."""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from openleadkit.schemas import BusinessRecord, Category

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
BUSINESS_SUFFIXES = {
    "cv",
    "inc",
    "llc",
    "ltd",
    "pt",
    "pte",
    "tbk",
}


def normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def normalize_unicode(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def normalize_business_name(value: str) -> str:
    text = normalize_unicode(value).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    words = [word for word in text.split() if word not in BUSINESS_SUFFIXES]
    return " ".join(words)


def _first_phone(value: str) -> str:
    return re.split(r"\s*(?:/|;|,|\bor\b)\s*", value, maxsplit=1)[0]


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    first = _first_phone(normalize_unicode(value).strip())
    has_plus = first.startswith(("+", "00"))
    digits = re.sub(r"\D", "", first)
    if not digits:
        return None
    if first.startswith("00"):
        digits = digits[2:]
    return f"+{digits}" if has_plus else digits


def normalize_url(value: str | None) -> str | None:
    if not value:
        return None
    raw = normalize_unicode(value.strip())
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
            return None
        hostname = parts.hostname.encode("idna").decode("ascii").casefold()
        port = parts.port
    except (UnicodeError, ValueError):
        return None
    if port and not (
        (parts.scheme.casefold() == "http" and port == 80)
        or (parts.scheme.casefold() == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname
    if parts.username or parts.password:
        return None
    query = urlencode(
        [
            (key, val)
            for key, val in parse_qsl(parts.query)
            if key.casefold() not in TRACKING_PARAMETERS
        ]
    )
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.casefold(), netloc, path, query, ""))


def extract_domain(value: str | None) -> str | None:
    normalized = normalize_url(value)
    if not normalized:
        return None
    hostname = urlsplit(normalized).hostname
    if hostname and hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def normalize_instagram(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if "instagram.com" in text.casefold():
        path = urlsplit(normalize_url(text) or "").path.strip("/")
        text = path.split("/")[0] if path else ""
    return re.sub(r"^@", "", text).split("?")[0] or None


def assemble_address(tags: dict[str, Any]) -> str | None:
    if full := normalize_whitespace(str(tags.get("addr:full", ""))):
        return full
    street = normalize_whitespace(
        " ".join(
            part
            for part in (str(tags.get("addr:street", "")), str(tags.get("addr:housenumber", "")))
            if part
        )
    )
    parts = [
        street,
        normalize_whitespace(str(tags.get("addr:suburb", ""))),
        normalize_whitespace(str(tags.get("addr:district", ""))),
        normalize_whitespace(str(tags.get("addr:city", ""))),
        normalize_whitespace(str(tags.get("addr:province", ""))),
        normalize_whitespace(str(tags.get("addr:postcode", ""))),
    ]
    result = ", ".join(part for part in parts if part)
    return result or None


def extract_osm_element(element: dict[str, Any], category: Category) -> BusinessRecord | None:
    tags = element.get("tags") or {}
    name = normalize_whitespace(tags.get("name") or tags.get("brand"))
    if not name:
        return None
    osm_type = str(element.get("type", ""))
    osm_id = element.get("id")
    center = element.get("center") or element
    lat, lon = center.get("lat"), center.get("lon")
    if osm_type not in {"node", "way", "relation"} or not isinstance(osm_id, int):
        return None
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    country_code = normalize_whitespace(tags.get("addr:country"))
    phone = normalize_whitespace(tags.get("contact:phone") or tags.get("phone"))
    website = normalize_url(tags.get("contact:website") or tags.get("website"))
    return BusinessRecord(
        osm_type=osm_type,
        osm_id=osm_id,
        business_name=name,
        normalized_name=normalize_business_name(name),
        category_key=category.key,
        category_label=category.label,
        city=normalize_whitespace(tags.get("addr:city") or tags.get("addr:town")),
        district=normalize_whitespace(tags.get("addr:district") or tags.get("addr:suburb")),
        province=normalize_whitespace(tags.get("addr:province") or tags.get("addr:state")),
        postcode=normalize_whitespace(tags.get("addr:postcode")),
        country_code=country_code.casefold() if country_code else None,
        address=assemble_address(tags),
        source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        website_url=website,
        normalized_domain=extract_domain(website),
        phone=phone,
        normalized_phone=normalize_phone(phone),
        email=normalize_whitespace(tags.get("contact:email") or tags.get("email")),
        instagram=normalize_instagram(tags.get("contact:instagram") or tags.get("instagram")),
        opening_hours=normalize_whitespace(tags.get("opening_hours")),
        latitude=float(lat),
        longitude=float(lon),
        raw_element=element,
    )

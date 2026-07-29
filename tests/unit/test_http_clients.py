import json

import httpx
import pytest

from openleadkit.config import Settings
from openleadkit.exceptions import AreaLookupError, OverpassError
from openleadkit.schemas import Category
from openleadkit.services.area_lookup import AreaLookupClient
from openleadkit.services.overpass import OverpassClient
from openleadkit.services.website_checker import WebsiteChecker


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1/openleadkit",
        app_project_url="https://github.com/akmalalf/OpenLeadKit",
        http_max_response_bytes=10_000,
    )


def test_default_clients_identify_the_github_repository() -> None:
    config = settings()
    area = AreaLookupClient(config)
    overpass = OverpassClient(config)
    website = WebsiteChecker(config)
    try:
        expected = str(config.app_project_url)
        assert expected in area.client.headers["User-Agent"]
        assert expected in overpass.client.headers["User-Agent"]
        assert expected in website.safe_client.client.headers["User-Agent"]
    finally:
        area.client.close()
        overpass.client.close()
        website.safe_client.client.close()


def test_area_lookup_supports_optional_country_filters_without_auto_selecting() -> None:
    payload = [
        {
            "display_name": "London, Greater London, England, United Kingdom",
            "boundingbox": ["51.2868", "51.6919", "-0.5103", "0.3340"],
        },
        {
            "display_name": "London, Ontario, Canada",
            "boundingbox": ["42.8247", "43.0732", "-81.3907", "-81.1071"],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["countrycodes"] == "gb"
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = AreaLookupClient(settings(), client).search("London", country_codes="GB")
    assert len(results) == 2
    assert results[0].display_name.startswith("London, Greater London")


def test_area_lookup_rejects_bad_inputs_and_responses() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"bad": True}))
    )
    area = AreaLookupClient(settings(), client)
    with pytest.raises(AreaLookupError):
        area.search("")
    with pytest.raises(AreaLookupError):
        area.search("London")
    with pytest.raises(AreaLookupError, match="ISO 3166-1"):
        area.search("London", country_codes="United Kingdom")


def test_overpass_client_parses_and_caps_response() -> None:
    payload = {
        "generator": "Overpass",
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": -6.2,
                "lon": 106.8,
                "tags": {"name": "Arunika Coffee"},
            }
        ],
    }
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
        )
    )
    category = Category(key="cafe", label="Cafe", tags=[{"amenity": "cafe"}])
    result = OverpassClient(settings(), client).execute("[out:json];", category)
    assert result.received == 1
    assert result.records[0].business_name == "Arunika Coffee"


def test_overpass_client_rejects_invalid_json_and_large_response() -> None:
    category = Category(key="cafe", label="Cafe", tags=[{"amenity": "cafe"}])
    invalid = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not json"))
    )
    with pytest.raises(OverpassError, match="JSON"):
        OverpassClient(settings(), invalid).execute("query", category)
    tiny_settings = settings().model_copy(update={"http_max_response_bytes": 10_000})
    large = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 10_001))
    )
    with pytest.raises(OverpassError, match="size"):
        OverpassClient(tiny_settings, large).execute("query", category)

from typing import Any

import httpx
import pytest

from openleadkit.exceptions import UnsafeURLError, WebsiteCheckError
from openleadkit.security.safe_http import (
    SafeHttpClient,
    is_public_ip,
    validate_public_url,
)
from openleadkit.services.website_checker import extract_website_fields


def resolver_for(address: str) -> Any:
    def resolve(host: str, port: int) -> list[Any]:
        return [(2, 1, 6, "", (address, port))]

    return resolve


def test_private_and_special_addresses_are_blocked() -> None:
    for address in ("127.0.0.1", "10.0.0.1", "169.254.1.1", "::1", "224.0.0.1"):
        assert not is_public_ip(address)
        with pytest.raises(UnsafeURLError):
            validate_public_url("https://example.com", resolver_for(address))
    assert is_public_ip("93.184.216.34")


def test_invalid_and_localhost_urls_are_blocked() -> None:
    with pytest.raises(UnsafeURLError):
        validate_public_url("javascript:alert(1)", resolver_for("93.184.216.34"))
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://localhost/admin", resolver_for("93.184.216.34"))


def test_redirect_is_revalidated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://private.invalid/"})

    safe = SafeHttpClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        max_bytes=1000,
        resolver=lambda host, port: resolver_for(
            "10.0.0.1" if host == "private.invalid" else "93.184.216.34"
        )(host, port),
    )
    with pytest.raises(UnsafeURLError):
        safe.get_html("https://public.example/")


def test_response_size_and_content_type_are_enforced() -> None:
    resolver = resolver_for("93.184.216.34")
    large = SafeHttpClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"Content-Type": "text/html"}, content=b"x" * 20
                )
            )
        ),
        max_bytes=10,
        resolver=resolver,
    )
    with pytest.raises(WebsiteCheckError, match="size"):
        large.get_html("https://example.com")
    non_html = SafeHttpClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"Content-Type": "application/pdf"}, content=b"pdf"
                )
            )
        ),
        max_bytes=100,
        resolver=resolver,
    )
    with pytest.raises(WebsiteCheckError, match="not HTML"):
        non_html.get_html("https://example.com")


def test_requests_connect_to_the_validated_address() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<h1>OK</h1>")

    safe = SafeHttpClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        max_bytes=1000,
        resolver=resolver_for("93.184.216.34"),
    )
    response = safe.get_html("https://example.com/path")
    assert response.url == "https://example.com/path"


def test_safe_html_response_and_robots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/plain"},
                text="User-agent: *\nDisallow: /private",
            )
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<h1>OK</h1>")

    safe = SafeHttpClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        max_bytes=1000,
        resolver=resolver_for("93.184.216.34"),
    )
    response = safe.get_html("https://example.com")
    assert response.status_code == 200
    assert response.content == b"<h1>OK</h1>"
    assert safe.robots_allowed("https://example.com/private", "OpenLeadKit") is False
    assert safe.robots_allowed("https://example.com/public", "OpenLeadKit") is True


def test_oversized_robots_response_is_rejected() -> None:
    safe = SafeHttpClient(
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 1001))
        ),
        max_bytes=1000,
        resolver=resolver_for("93.184.216.34"),
    )
    assert safe.robots_allowed("https://example.com/", "OpenLeadKit") is False


def test_website_field_extraction() -> None:
    html = b"""
    <html><head><title>Sunrise Clinic</title><meta name="viewport" content="width=device-width">
    </head><body>
    <a href="mailto:hello@sunrise.example">Email</a>
    <a href="tel:+442071234567">Phone</a>
    <a href="/contact">Contact</a><a href="/about-us">About</a>
    <a href="https://wa.me/442071234567">WhatsApp</a>
    <a href="https://instagram.com/sunriseclinic">Instagram</a>
    </body></html>
    """
    fields = extract_website_fields(html, "https://sunrise.example/")
    assert fields.title == "Sunrise Clinic"
    assert fields.mobile_viewport_found
    assert fields.public_email == "hello@sunrise.example"
    assert fields.public_phone == "+442071234567"
    assert fields.contact_page_url == "https://sunrise.example/contact"
    assert fields.about_page_url == "https://sunrise.example/about-us"
    assert fields.whatsapp_url == "https://wa.me/442071234567"

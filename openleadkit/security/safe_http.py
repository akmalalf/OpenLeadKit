"""SSRF-resistant HTTP primitives for manually initiated website checks."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from openleadkit.exceptions import UnsafeURLError, WebsiteCheckError
from openleadkit.services.normalization import normalize_url

Resolver = Callable[..., list[Any]]


def is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return bool(ip.is_global and not ip.is_multicast and not ip.is_reserved)


def resolve_public_addresses(
    hostname: str,
    port: int,
    resolver: Resolver = socket.getaddrinfo,
) -> frozenset[str]:
    try:
        results = resolver(hostname, port)
    except OSError as exc:
        raise UnsafeURLError("The hostname could not be resolved") from exc
    addresses = frozenset(str(result[4][0]) for result in results)
    if not addresses or any(not is_public_ip(address) for address in addresses):
        raise UnsafeURLError(
            "Local, private, link-local, multicast, or reserved addresses are blocked"
        )
    return addresses


def validate_public_url(url: str, resolver: Resolver = socket.getaddrinfo) -> str:
    return resolve_public_target(url, resolver).url


@dataclass(frozen=True)
class PublicTarget:
    """A validated logical URL paired with a DNS-pinned transport URL."""

    url: str
    request_url: str
    host_header: str
    sni_hostname: str | None


def resolve_public_target(url: str, resolver: Resolver = socket.getaddrinfo) -> PublicTarget:
    normalized = normalize_url(url)
    if not normalized:
        raise UnsafeURLError("The website URL is invalid or does not use HTTP/HTTPS")
    parts = urlsplit(normalized)
    hostname = parts.hostname
    if not hostname or hostname.casefold() in {"localhost", "localhost.localdomain"}:
        raise UnsafeURLError("Local hosts are blocked")
    addresses = resolve_public_addresses(
        hostname, parts.port or (443 if parts.scheme == "https" else 80), resolver
    )
    address = sorted(addresses)[0]
    address_literal = f"[{address}]" if ipaddress.ip_address(address).version == 6 else address
    request_netloc = f"{address_literal}:{parts.port}" if parts.port else address_literal
    request_url = urlunsplit((parts.scheme, request_netloc, parts.path or "/", parts.query, ""))
    return PublicTarget(
        url=normalized,
        request_url=request_url,
        host_header=parts.netloc,
        sni_hostname=hostname if parts.scheme == "https" else None,
    )


@dataclass(frozen=True)
class SafeResponse:
    url: str
    status_code: int
    content_type: str
    content: bytes
    headers: httpx.Headers


class SafeHttpClient:
    """Small client that revalidates every redirect and caps response bytes."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        max_bytes: int,
        resolver: Resolver = socket.getaddrinfo,
        max_redirects: int = 5,
    ) -> None:
        self.client = client
        self.max_bytes = max_bytes
        self.resolver = resolver
        self.max_redirects = max_redirects

    def get_html(self, url: str) -> SafeResponse:
        current = url
        for _ in range(self.max_redirects + 1):
            target = resolve_public_target(current, self.resolver)
            extensions = (
                {"sni_hostname": target.sni_hostname} if target.sni_hostname is not None else {}
            )
            with self.client.stream(
                "GET",
                target.request_url,
                headers={"Host": target.host_header, "Accept-Encoding": "identity"},
                extensions=extensions,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise WebsiteCheckError("The redirect does not have a destination")
                    current = urljoin(target.url, location)
                    continue
                content_type = response.headers.get("content-type", "").split(";")[0].casefold()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise WebsiteCheckError("The website content is not HTML")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise WebsiteCheckError("The website response exceeds the size limit")
                    chunks.append(chunk)
                return SafeResponse(
                    url=target.url,
                    status_code=response.status_code,
                    content_type=content_type,
                    content=b"".join(chunks),
                    headers=response.headers,
                )
        raise WebsiteCheckError("Too many redirects")

    def robots_allowed(self, url: str, user_agent: str) -> bool:
        validated = validate_public_url(url, self.resolver)
        parts = urlsplit(validated)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        target = resolve_public_target(robots_url, self.resolver)
        extensions = (
            {"sni_hostname": target.sni_hostname} if target.sni_hostname is not None else {}
        )
        try:
            with self.client.stream(
                "GET",
                target.request_url,
                headers={"Host": target.host_header, "Accept-Encoding": "identity"},
                extensions=extensions,
                follow_redirects=False,
            ) as response:
                if response.status_code in {401, 403}:
                    return False
                if response.status_code >= 400:
                    return True
                chunks: list[bytes] = []
                total = 0
                limit = min(self.max_bytes, 500_000)
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        return False
                    chunks.append(chunk)
        except httpx.HTTPError:
            return True
        body = b"".join(chunks)
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        return parser.can_fetch(user_agent, validated)

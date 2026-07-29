"""Manual, factual website inspection with strict scope."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from openleadkit.config import Settings
from openleadkit.exceptions import WebsiteCheckError
from openleadkit.security.safe_http import SafeHttpClient, SafeResponse
from openleadkit.services.normalization import normalize_phone

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


@dataclass(frozen=True)
class ExtractedWebsiteFields:
    title: str | None
    mobile_viewport_found: bool
    public_email: str | None
    public_phone: str | None
    whatsapp_url: str | None
    instagram_url: str | None
    contact_page_url: str | None
    about_page_url: str | None


def extract_website_fields(html: bytes, base_url: str) -> ExtractedWebsiteFields:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True)[:500] if soup.title else None
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}) is not None
    visible_text = soup.get_text(" ", strip=True)
    email_match = EMAIL_RE.search(visible_text)
    phone_match = PHONE_RE.search(visible_text)
    whatsapp: str | None = None
    instagram: str | None = None
    contact: str | None = None
    about: str | None = None
    origin = urlsplit(base_url).netloc
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor["href"]).strip()
        absolute = urljoin(base_url, href)
        lowered = absolute.casefold()
        label = anchor.get_text(" ", strip=True).casefold()
        if not whatsapp and ("wa.me/" in lowered or "whatsapp.com/" in lowered):
            whatsapp = absolute
        if not instagram and "instagram.com/" in lowered:
            instagram = absolute
        if urlsplit(absolute).netloc == origin:
            if not contact and "contact" in label + lowered:
                contact = absolute
            if not about and any(word in label or word in lowered for word in ("about", "profile")):
                about = absolute
    mail_link = soup.find("a", href=re.compile(r"^mailto:", re.I))
    tel_link = soup.find("a", href=re.compile(r"^tel:", re.I))
    email = (
        str(mail_link["href"]).split(":", 1)[1].split("?", 1)[0]
        if isinstance(mail_link, Tag)
        else (email_match.group(0) if email_match else None)
    )
    phone_raw = (
        str(tel_link["href"]).split(":", 1)[1]
        if isinstance(tel_link, Tag)
        else (phone_match.group(0) if phone_match else None)
    )
    return ExtractedWebsiteFields(
        title=title,
        mobile_viewport_found=viewport,
        public_email=email,
        public_phone=normalize_phone(phone_raw),
        whatsapp_url=whatsapp,
        instagram_url=instagram,
        contact_page_url=contact,
        about_page_url=about,
    )


@dataclass(frozen=True)
class WebsiteInspection:
    requested_url: str
    final_url: str
    http_status: int
    content_type: str
    response_bytes: int
    https_enabled: bool
    robots_allowed: bool
    fields: ExtractedWebsiteFields


class WebsiteChecker:
    def __init__(
        self,
        settings: Settings,
        safe_client: SafeHttpClient | None = None,
    ) -> None:
        self.settings = settings
        if safe_client is None:
            client = httpx.Client(
                headers={"User-Agent": f"{settings.http_user_agent} ({settings.app_project_url})"},
                timeout=httpx.Timeout(
                    connect=settings.http_connect_timeout_seconds,
                    read=settings.http_read_timeout_seconds,
                    write=settings.http_connect_timeout_seconds,
                    pool=settings.http_connect_timeout_seconds,
                ),
            )
            safe_client = SafeHttpClient(
                client, max_bytes=settings.http_max_response_bytes, max_redirects=5
            )
        self.safe_client = safe_client

    def inspect(self, website_url: str) -> WebsiteInspection:
        if not self.safe_client.robots_allowed(website_url, self.settings.http_user_agent):
            raise WebsiteCheckError("robots.txt does not allow this URL to be inspected")
        homepage = self.safe_client.get_html(website_url)
        fields = extract_website_fields(homepage.content, homepage.url)
        for secondary_url in dict.fromkeys(
            url for url in (fields.contact_page_url, fields.about_page_url) if url
        ):
            if not self.safe_client.robots_allowed(secondary_url, self.settings.http_user_agent):
                continue
            if self.settings.http_per_domain_delay_seconds:
                time.sleep(self.settings.http_per_domain_delay_seconds)
            secondary = self.safe_client.get_html(secondary_url)
            secondary_fields = extract_website_fields(secondary.content, secondary.url)
            fields = ExtractedWebsiteFields(
                title=fields.title,
                mobile_viewport_found=(
                    fields.mobile_viewport_found or secondary_fields.mobile_viewport_found
                ),
                public_email=fields.public_email or secondary_fields.public_email,
                public_phone=fields.public_phone or secondary_fields.public_phone,
                whatsapp_url=fields.whatsapp_url or secondary_fields.whatsapp_url,
                instagram_url=fields.instagram_url or secondary_fields.instagram_url,
                contact_page_url=fields.contact_page_url,
                about_page_url=fields.about_page_url,
            )
        return self._result(website_url, homepage, fields)

    @staticmethod
    def _result(
        requested_url: str, response: SafeResponse, fields: ExtractedWebsiteFields
    ) -> WebsiteInspection:
        return WebsiteInspection(
            requested_url=requested_url,
            final_url=response.url,
            http_status=response.status_code,
            content_type=response.content_type,
            response_bytes=len(response.content),
            https_enabled=urlsplit(response.url).scheme == "https",
            robots_allowed=True,
            fields=fields,
        )

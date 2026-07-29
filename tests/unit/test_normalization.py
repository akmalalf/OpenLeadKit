from openleadkit.schemas import Category
from openleadkit.services.normalization import (
    assemble_address,
    extract_domain,
    extract_osm_element,
    normalize_business_name,
    normalize_instagram,
    normalize_phone,
    normalize_url,
    normalize_whitespace,
)


def test_whitespace_and_business_name_normalization() -> None:
    assert normalize_whitespace("  Healthy\n  Clinic ") == "Healthy Clinic"
    assert normalize_business_name("Acme Healthy Clinic, Ltd!") == "acme healthy clinic"


def test_global_phone_normalization() -> None:
    assert normalize_phone("020 7946 0958") == "02079460958"
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert normalize_phone("00 33 1 42 68 53 00") == "+33142685300"


def test_phone_is_conservative_for_multiple_and_unknown_country() -> None:
    assert normalize_phone("020 7946 0958 or +44 20 7000 0000") == "02079460958"
    assert normalize_phone("not a phone") is None


def test_url_and_domain_normalization() -> None:
    assert (
        normalize_url("HTTPS://WWW.Exämple.com:443/a//b?utm_source=x&id=7#top")
        == "https://www.xn--exmple-cua.com/a/b?id=7"
    )
    assert extract_domain("example.com/path") == "example.com"
    assert normalize_url("javascript:alert(1)") is None
    assert normalize_url("data:text/html,hi") is None
    assert normalize_url("http://user:secret@example.com") is None


def test_instagram_and_address() -> None:
    assert normalize_instagram("@healthy_clinic") == "healthy_clinic"
    assert normalize_instagram("https://instagram.com/healthy.clinic/?ref=x") == "healthy.clinic"
    assert (
        assemble_address(
            {
                "addr:street": "High Street",
                "addr:housenumber": "17",
                "addr:district": "Camden",
                "addr:city": "London",
            }
        )
        == "High Street 17, Camden, London"
    )
    assert assemble_address({"addr:full": " 1 Market Street "}) == "1 Market Street"


def test_osm_element_extraction() -> None:
    category = Category(key="cafe", label="Cafe", tags=[{"amenity": "cafe"}])
    record = extract_osm_element(
        {
            "type": "way",
            "id": 42,
            "center": {"lat": -6.2, "lon": 106.8},
            "tags": {
                "name": "Morning Coffee",
                "addr:city": "London",
                "addr:country": "GB",
                "phone": "020 7946 0958",
                "website": "morningcoffee.example?utm_source=osm",
            },
        },
        category,
    )
    assert record is not None
    assert record.osm_type == "way"
    assert record.normalized_phone == "02079460958"
    assert record.normalized_domain == "morningcoffee.example"
    assert record.source_url == "https://www.openstreetmap.org/way/42"


def test_osm_element_without_name_or_coordinates_is_skipped() -> None:
    category = Category(key="cafe", label="Cafe", tags=[{"amenity": "cafe"}])
    assert extract_osm_element({"type": "node", "id": 1, "lat": 1, "lon": 2}, category) is None
    assert (
        extract_osm_element(
            {"type": "way", "id": 1, "tags": {"name": "Missing Coordinates"}}, category
        )
        is None
    )

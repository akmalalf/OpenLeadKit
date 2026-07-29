"""Domain-specific exceptions."""


class OpenLeadKitError(Exception):
    """Base application error."""


class ConfigurationError(OpenLeadKitError):
    """Invalid or missing configuration."""


class DatabaseError(OpenLeadKitError):
    """Database connection or migration problem."""


class CategoryConfigurationError(ConfigurationError):
    """Invalid category mapping."""


class AreaLookupError(OpenLeadKitError):
    """Nominatim lookup failed."""


class OverpassError(OpenLeadKitError):
    """Overpass request failed."""


class RateLimitError(OpenLeadKitError):
    """Remote service rate limit."""


class WorkbookCompatibilityError(OpenLeadKitError):
    """Workbook layout is incompatible."""


class ExportError(OpenLeadKitError):
    """Workbook export failed."""


class UnsafeURLError(OpenLeadKitError):
    """URL cannot be accessed safely."""


class WebsiteCheckError(OpenLeadKitError):
    """Website inspection failed."""

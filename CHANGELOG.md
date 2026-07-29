# Changelog

All notable changes are documented here. This format follows Keep a Changelog and the project
uses Semantic Versioning.

## [Unreleased]

### Added

- Initial application, documentation, tests, and contributor automation.

### Fixed

- Commit review and duplicate mutations before Streamlit reruns.
- Pin website connections to validated public IP addresses and stream size-limited robots files.
- Preserve exact duplicate candidates without location fields.
- Reject duplicate Excel rows within the same export batch.
- Keep configuration errors credential-safe and make the Settings page accurately read-only.

## [0.1.0] - 2026-07-29

### Added

- PostgreSQL schema and Alembic migration.
- OpenStreetMap/Overpass discovery with optional Nominatim area lookup.
- Global area lookup with optional country-code filters and country-neutral phone normalization.
- Normalization, deduplication, review, qualification, website checks, and audit history.
- Verified Excel CRM export and English multipage Streamlit interface.

[Unreleased]: https://github.com/akmalalf/OpenLeadKit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/akmalalf/OpenLeadKit/releases/tag/v0.1.0

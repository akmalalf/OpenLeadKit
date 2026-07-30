# Changelog

All notable changes are documented here. This format follows Keep a Changelog and the project
uses Semantic Versioning.

## [Unreleased]

## [0.2.0] - 2026-07-31

### Added

- Generate standalone Excel exports without requiring a custom input workbook.
- Add paginated export history with workbook downloads and exported-row inspection.
- Allow combining the current Approved queue with multiple historical export batches.

### Changed

- Paginate CRM export batch selection and combined export previews.
- Remove local workbook paths from export history and expose available files only through
  download actions.
- Save manual lead details, qualification, notes, and the review decision in one action.
- Preserve unsaved Lead Review drafts, queue sort, and filters across page navigation for
  the browser session, then clear a lead's draft after a successful review decision.
- Open Lead Review website drafts in a new browser tab without saving them or requesting
  them from the application server.
- Recheck duplicate candidates after manual edits change matching business fields.

### Fixed

- Synchronize Lead Review fields without form-submit buffering so unsaved notes and edits
  reach session state before page navigation.
- Apply only the newest map rectangle and normalize Leaflet world-copy longitudes before
  validating the search boundary.
- Commit review and duplicate mutations before Streamlit reruns.
- Pin website connections to validated public IP addresses and stream size-limited robots files.
- Preserve exact duplicate candidates without location fields.
- Reject duplicate Excel rows within the same export batch.
- Keep configuration errors credential-safe and make the Settings page accurately read-only.

## [0.1.0] - 2026-07-29

### Added

- Initial application, documentation, tests, and contributor automation.
- PostgreSQL schema and Alembic migration.
- OpenStreetMap/Overpass discovery with optional Nominatim area lookup.
- Global area lookup with optional country-code filters and country-neutral phone normalization.
- Normalization, deduplication, review, qualification, website checks, and audit history.
- Verified Excel CRM export and English multipage Streamlit interface.

[Unreleased]: https://github.com/akmalalf/OpenLeadKit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/akmalalf/OpenLeadKit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/akmalalf/OpenLeadKit/releases/tag/v0.1.0

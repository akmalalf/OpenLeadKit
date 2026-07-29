# Contributing to OpenLeadKit

Thank you for helping improve OpenLeadKit.

## Development setup

Fork and clone the repository, create a Python 3.12 virtual environment, copy `.env.example`,
install `pip install -e ".[dev]"`, create a separate PostgreSQL test database, and run
`alembic upgrade head`. Never point tests at a non-test database.

## Branches and commits

Use short branches such as `feat/category-import`, `fix/export-styles`, or
`docs/postgres-setup`. Follow Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`,
`refactor:`, `chore:`, and `security:`.

## Required checks

Before opening a pull request:

```bash
make lint
make typecheck
make test-unit
make coverage
make test-integration
```

New behavior requires meaningful tests. HTTP tests must use mocks and database tests must use
`TEST_DATABASE_URL`.

## Pull requests

Keep a PR focused. Explain the user problem, implementation, security/data-loss implications,
migration impact, and commands run. Update `README.md` when the user workflow changes. Do not
include `.env`, workbooks, exports, dumps, lead data, or credentials.

## Add a category

Add a unique key, English label, and one or more supported OSM tag combinations to
`config/categories.json`. Do not put mappings into UI code. Run category and query-builder tests.

## Add a data-source adapter

Create a source-specific client and parser in `openleadkit/services/`. Reuse normalized
`BusinessRecord`, preserve raw responses, expose clear attribution, implement bounded
user-triggered requests, and add mocked tests. Do not weaken security or mix source-specific
logic into the Streamlit pages.

## Report bugs

Use the issue template. Include version, OS, Python/PostgreSQL versions, sanitized configuration,
reproduction steps, expected/actual result, and safe logs. Remove business data and secrets.
For vulnerabilities, use the private process in `SECURITY.md`.

All participants must follow `CODE_OF_CONDUCT.md`.

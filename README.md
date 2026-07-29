# OpenLeadKit

> An open-source toolkit for discovering, reviewing, and qualifying local-business leads.

OpenLeadKit retrieves public business data from OpenStreetMap through Overpass, stores it in
PostgreSQL, helps reviewers assess duplicates and lead quality, and exports approved leads to an
existing Excel CRM workbook. The application runs locally and does not send bulk messages.

## Features

- 26 business categories that can be extended through `config/categories.json`.
- Global one-off Nominatim area lookup with optional country filters, or manual bounding-box entry.
- OpenStreetMap node, way, and relation searches.
- Name, phone, URL, domain, Instagram, and address normalization.
- PostgreSQL as the system of record, using `citext`, `pg_trgm`, UUID, JSONB, and audit records.
- Duplicate candidates based on OSM identity, domain, phone, and similar names in the same area.
- Manual review and qualification, safe website inspection, and a transparent suggestion score.
- Copy-only export to the `Raw Import` worksheet with duplicate detection and post-save checks.
- Search, review, website-check, duplicate-decision, merge, and export history.

## Non-goals

OpenLeadKit does not scrape Google Maps pages, require Google Places credentials, discover
websites through search engines, bypass CAPTCHA or authentication, rotate proxies, or automate
outreach.

## Architecture

Streamlit provides the user interface. The service layer builds queries and communicates with
public APIs through HTTPX. SQLAlchemy repositories own transactions and audit records.
PostgreSQL is the system of record, Excel is only an export destination, and Alembic manages the
database schema.

## Requirements

- Linux or WSL
- Python 3.12; the package metadata also permits Python 3.11
- PostgreSQL 14 or later
- Permission to create the `citext` and `pg_trgm` extensions

## Set up local PostgreSQL

Open an administrator session:

```bash
sudo -u postgres psql
```

Run the following SQL and replace the example password:

```sql
CREATE ROLE openleadkit_app LOGIN PASSWORD 'strong-local-password';
CREATE DATABASE openleadkit OWNER openleadkit_app;
CREATE DATABASE openleadkit_test OWNER openleadkit_app;
\connect openleadkit
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
\connect openleadkit_test
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Exit with `\q`. To use the optional Docker service:

```bash
POSTGRES_PASSWORD=strong-local-password docker compose up -d postgres
```

Docker publishes PostgreSQL on host port `5433` by default. Update `DATABASE_URL` to use that
port.

## Configure `.env`

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env`, especially `DATABASE_URL`, `TEST_DATABASE_URL`, and `APP_PROJECT_URL`. Never
commit `.env`. API endpoints, timeouts, response limits, timezone, duplicate threshold, and
workbook paths are configurable there as well.

The in-application Settings page is read-only so it cannot create a second, conflicting
configuration source. Edit `.env` and restart OpenLeadKit to apply changes.

OpenLeadKit defaults to `UTC`. Set `APP_TIMEZONE` to another IANA timezone only when a deployment
needs localized timestamps.

## Install on Linux or WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Run Alembic migrations

Migrations never run implicitly during application import or Streamlit startup.

```bash
alembic upgrade head
alembic current
python scripts/check_database.py
```

Roll back one revision:

```bash
alembic downgrade -1
```

## Run the application

```bash
streamlit run app.py
```

Open the local address printed by Streamlit. If the database is not ready, the application
shows the required setup command without creating the schema silently.

## Search for businesses

Open the business-search page, select a category, and define a bounded area. You can resolve an
area name, draw one rectangle on the OpenStreetMap map, or enter South, West, North, and East
coordinates manually. Area lookup is global by default; optionally enter one or more ISO 3166-1
alpha-2 country codes, such as `gb,ie`, to narrow results. Drawing or editing the map never starts
a request. The map location control can center the view on the browser's current location after
the user grants permission; production deployments require HTTPS for browser geolocation. Review
the generated query, result limit, and geographic area before pressing **Start search**. Results
include OpenStreetMap attribution and are persisted only after the transaction succeeds.

Phone normalization is country-neutral. Explicit international prefixes such as `+44` or `0033`
are preserved in normalized form, while local numbers remain local because OpenLeadKit does not
guess a country code.

## Review leads

The lead-review page presents one record at a time. The **Sort by** control orders the queue in
PostgreSQL by review need, discovery time, business name, city, or the calculated transparent
suggestion score. The separate **Qualification filter** limits the queue to one qualification
value. Changing either control returns the reviewer to the first lead. Reviewers can approve or
reject the record, assign High, Medium, Low, Not Qualified, or Unknown status, add notes, and
inspect the stored official website. Each change creates a `review_events` record. Suggestion
scores never replace manual decisions.

The Dashboard recent-activity section lists up to five latest completed searches, followed by
the most recent verified CRM export.

## Resolve duplicates

The duplicate page displays both records and the matching reason. Reviewers can keep both,
ignore the candidate, or merge the records. A merge requires explicit confirmation, fills only
empty survivor fields, moves compatible relations, and stores an audit snapshot.

Merge recovery is manual. Locate the snapshot in `business_merges`, recreate the
`merged_snapshot` record with its `merged_business_id`, and restore associations from the audit
record or backup. Test the procedure against the test database and create a backup before
operating on important data.

## Inspect websites

Website inspection starts only after an explicit user action and only for a stored official
URL. The HTTP layer blocks localhost, private networks, link-local, multicast, reserved ranges,
unsafe redirects, oversized responses, and non-HTML content. Connections are pinned to the
public IP address that passed validation while preserving the original HTTP Host and TLS server
name. It enforces `robots.txt`, timeouts, and redirect limits. It does not download images, PDF
files, media, archives, office documents, or authenticated content.

## Export to the Excel CRM

Place the source workbook at:

```text
input/Website_Lead_Funnel_CRM.xlsx
```

Inspect it without saving:

```bash
python scripts/inspect_workbook.py
```

The export page includes only approved leads. It never overwrites the source workbook. Instead,
it creates a timestamped copy in `exports/`, changes only the `Raw Import` worksheet, reopens the
saved file, and verifies the batch before marking database records as Exported. Google rating
and review-count fields remain empty because OpenLeadKit never invents those values.

## Back up the database

```bash
pg_dump --format=custom --no-owner --file=openleadkit_$(date +%F).dump openleadkit
```

Store the dump securely outside the repository.

## Restore the database

Restore into an empty database first:

```bash
createdb -O openleadkit_app openleadkit_restore
pg_restore --no-owner --dbname=openleadkit_restore openleadkit_YYYY-MM-DD.dump
```

Verify the restored database before replacing any active database.

## Testing

```bash
make lint
make typecheck
make test-unit
make coverage
```

Integration tests may use only a database whose name contains `test`, differs from
`DATABASE_URL`, and is configured through `TEST_DATABASE_URL`:

```bash
make test-integration
```

All external HTTP requests are mocked in tests.

## Troubleshooting

- **`.env` is missing:** run `cp .env.example .env`.
- **PostgreSQL is unavailable:** run `pg_isready` and
  `python scripts/check_database.py`.
- **Migrations are behind:** run `alembic upgrade head`.
- **Extension creation is denied:** ask a PostgreSQL administrator to create `citext` and
  `pg_trgm`.
- **The workbook is missing:** other workflows remain available; place the workbook at the
  configured input path.
- **Overpass returns 429 or 5xx:** wait, reduce the search area or limit, and retry manually.
- **Nominatim results are ambiguous:** select a result explicitly; the application does not
  select the first result automatically.

## OpenStreetMap attribution

Data © OpenStreetMap contributors, available under the Open Database License (ODbL).
OpenLeadKit is not affiliated with or endorsed by the OpenStreetMap Foundation.

## API usage limits

Use only geographically bounded, user-triggered searches. Do not run a crawler, send parallel
requests to public endpoints, or perform bulk geocoding. Keep `APP_PROJECT_URL` pointed to the
project's public GitHub repository so the HTTP User-Agent identifies the application, and follow
the usage policy of each Overpass or Nominatim instance you select.

## Security

Secrets belong only in the environment. Website URLs pass SSRF and DNS validation on every
redirect. TLS verification remains enabled, and output paths are restricted to the project
directory. Do not expose the local application to the internet without appropriate
authentication and a secure reverse proxy. Report vulnerabilities according to
[SECURITY.md](SECURITY.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Issues and
pull requests that add categories, source adapters, tests, or documentation improvements are
welcome.

## License

Apache License 2.0. See [LICENSE](LICENSE).

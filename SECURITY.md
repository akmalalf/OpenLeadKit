# Security Policy

## Supported versions

Until a later release is announced, security fixes target the latest `0.1.x` release and the
`main` branch.

## Private reporting

Do not publish an unpatched vulnerability in a public issue, discussion, pull request, or social
post. Use GitHub's
[private vulnerability-reporting form](https://github.com/akmalalf/OpenLeadKit/security/advisories/new).
If private vulnerability reporting is not available, wait for the repository owner to enable it
rather than disclosing the issue publicly.

Include the affected version/commit, attack preconditions, reproducible steps or proof of concept,
impact, proposed remediation if known, and whether any real data was accessed. Do not include
credentials or unnecessary personal/business data. Maintainers should acknowledge a report
within seven days and coordinate disclosure after a fix is available.

## Sensitive scope

Security-sensitive areas include SSRF/DNS/redirect validation, robots and HTTP limits, PostgreSQL
queries and migrations, merge transactions, audit integrity, path traversal, workbook parsing
and export verification, Streamlit deployment, dependency integrity, logs, and environment
configuration.

Never commit `.env`, passwords, tokens, CRM workbooks, generated exports, database dumps, or
logs containing user data. Rotate a secret immediately if it is exposed. TLS verification must
remain enabled; anti-bot, CAPTCHA, authentication, and rate-limit bypasses are out of scope.

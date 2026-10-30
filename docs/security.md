# Security

The data is mostly public and the API is read-only, but it reads content from other catalogues and
publishes it under MOSAIC's name. These are the threats and what covers them.

| Threat | Measure | Where |
|---|---|---|
| A source points the harvester at internal or unexpected hosts (SSRF) | https only; host allow-list (`allowed_hosts`), also checked after every redirect; at most 5 redirects | `adapters/fetch.py` |
| Huge or slow responses | Size limit (`max_download_mb`, 2 MB per YAML record), 30 s timeout | `fetch.py`, `git_yaml.py` |
| Hostile files | `yaml.safe_load` only; tarballs read in memory, never extracted to disk; local paths cannot escape their folder | `git_yaml.py`, `fetch.py` |
| Malformed records reach the website | Every record is validated into the typed model; invalid ones become issues and are not published | `translators/common.py` |
| Internal fields leak | Responses are explicit DTOs: a field is published only if it is listed. Internal paths from schema 1 were not migrated | `application/dto.py` |
| XSS through texts from other catalogues | The API returns JSON, never HTML built from records. The website must render record text as text, never as HTML | website |
| Personal data | Contact e-mails are public by project decision; `http.expose_emails: false` removes them. They are never logged | `dto.py`, `config.py` |
| Write or abuse of the API | GET routes only (a test checks this); bounded parameters (`q` ≤ 200 characters, `page_size` ≤ 100, validated bbox and years); errors as RFC 9457 problem+json | `adapters/inbound/http.py` |
| Cross-origin misuse | CORS allow-list (`http.cors_origins`), GET only | `http.py` |
| Clickjacking, MIME sniffing | `X-Frame-Options: DENY`, `CSP frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer` | `http.py` |
| Supply chain (GitHub Actions) | Least-privilege `permissions`; pin actions to SHAs before publishing; Dependabot + `pip-audit` (to enable when the repo exists) | `.github/workflows` |

**Pending when a live server exists:**

- rate limiting, at the reverse proxy or with a middleware;
- HTTPS termination;
- logs without query strings that could hold personal data;
- an OWASP API Top 10 review.

# Security status

## Posture

smoltask is a single-user tool that runs on the machine of the person using it.
It has no authentication, no multi-user model and no outbound network access.
The threat model is **"ordinary input reaches the database"**, not "an attacker
has a foothold on the network" — if someone can reach the port, they can already
read and write every task, by design.

With one addition, learned the hard way: **the user's own browser can reach the
port, and it also visits the rest of the internet.** Binding to localhost keeps
other machines out; it does not keep out a web page that the browser on this
machine is showing. Two attacks need no login to ride on. A form or a body-less
`fetch` from another site is sent without a CORS preflight, so its side effect
lands even though its answer cannot be read (cross-site request forgery). And a
page can re-point its own hostname at 127.0.0.1 (DNS rebinding), after which the
browser treats the app as that page's own origin and lets it read everything.
`guard.py` closes both; see below.

## What is enforced

| Control | Where | Test |
|---|---|---|
| Requests naming a host not on the allowlist are refused with 400, on every route — the DNS-rebinding defence. `SMOLTASK_ALLOWED_HOSTS`, default `localhost,127.0.0.1,[::1]` | `guard.py` | `test_an_unknown_host_is_refused_everywhere`, `test_the_host_allowlist_comes_from_the_environment` |
| Writes (anything but GET/HEAD/OPTIONS) that a browser marks as cross-site are refused with 403: `Sec-Fetch-Site` other than `same-origin`/`none`, or else an `Origin` that is not this host and port. Requests with neither header — curl, scripts — are allowed | `guard.py` | `test_a_cross_site_write_is_refused_and_changes_nothing`, `test_the_page_own_requests_still_work`, `test_scripts_without_browser_headers_still_work` |
| `Content-Security-Policy` (`default-src 'self'`, `frame-ancestors 'none'`, no inline script or style attributes), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer` on every response, refusals included | `guard.py` | `test_security_headers_are_on_every_response`, `test_styles_are_set_through_the_cssom_not_as_attributes` |
| No `/docs`, `/redoc` or `/openapi.json` | `app.py` | `test_the_api_docs_are_not_served` |
| Parameterised SQL everywhere; no string-built queries | `db.py` | `test_title_is_data_not_sql`, `test_search_is_data_not_sql` |
| Archive `sort`/`dir`/`outcome` matched against an allowlist, never interpolated | `db.py:list_archive` | `test_archive_sort_is_allowlisted` |
| Titles: control characters, null bytes, bidi overrides and isolates stripped — joiners and unassigned code points kept, so emoji survive — length bounded 1–80 | `app.py:clean_line`, `clean_title` | `test_title_control_characters_are_stripped`, `test_joined_emoji_survive_but_bidi_controls_do_not`, `test_oversized_titles_are_rejected` |
| Dates validated as real calendar dates before reaching SQL, on create as on patch | `app.py:validate_due` | `test_due_dates_are_validated`, `test_a_date_on_create_is_validated_like_any_other` |
| Settings labels: shape enforced by the model, control characters stripped, lengths bounded, names required and distinct; stored as a bound JSON parameter and rendered as text | `app.py:clean_labels`, `db.py:set_labels` | `test_labels_are_data_not_markup_or_sql`, `test_label_control_characters_are_stripped`, `tests/test_settings.py` |
| A damaged settings row falls back to the defaults rather than failing the page | `db.py:get_labels` | `test_a_damaged_row_falls_back_to_the_defaults` |
| Quadrants constrained to 1–4 at the API — as strict integers, so `true`, `"2"` and `1.0` are refused rather than coerced — *and* by a `CHECK` in the schema | `app.py`, `db.py` | `test_quadrants_are_bounded`, `test_a_quadrant_is_an_integer_not_something_that_converts_to_one` |
| Static mount cannot escape its directory | `app.py` | `test_static_mount_does_not_escape` |
| No database path or filesystem detail in any response | `app.py` | `test_no_route_exposes_the_database_path` |
| Ids outside SQLite's 64-bit range are a miss, not a driver error | `db.py:is_possible_id` | `test_an_id_too_large_for_sqlite_is_a_miss_not_a_crash` |
| No reachable input returns 5xx; schema invariants survive any operation order | repo-wide | `tests/test_robustness.py` |
| Concurrent requests do not 500: a request's connection may cross threadpool workers, so it is opened with `check_same_thread=False` | `db.py:connect` | `test_concurrent_captures_all_succeed_through_a_real_server` |
| Compose publishes on `127.0.0.1` unless `SMOLTASK_BIND` says otherwise (Docker's published ports bypass host firewalls); read-only root filesystem, all capabilities dropped, `no-new-privileges`; base image pinned by digest | `docker-compose.yml`, `Dockerfile` | `tests/test_config.py` |
| CI actions pinned to commits; automerge checks the PR's author and runs only on the private repo; tests run on Python 3.10 and on the image's 3.14; the image is built and health-checked before a Dependabot merge | `.github/workflows/` | `tests/test_config.py` |
| No hardcoded secrets in the tree | repo-wide | `test_no_hardcoded_secrets` |
| Database file is not tracked by git | `.gitignore` | `test_database_file_is_not_tracked` |

## Accepted risks

- **No authentication.** Documented in [SECURITY.md](SECURITY.md). Anyone who
  can reach the port has full access. Mitigation is deployment, not code: bind
  to localhost.
- **No rate limiting.** A single-user local app has no one to limit.
- **Requests without `Origin` or `Sec-Fetch-Site` are trusted.** That is every
  non-browser client, and scripted access is intended. A process already
  running on the machine could do anything to the database file directly; a
  web page cannot send a write without a browser attaching one of the two.
- **No request body cap beyond the fields' own.** Every field is bounded by
  pydantic before it is cleaned, so an oversized body is refused, but only once
  it has been read. There is no one on a loopback port to send one.
- **No audit trail.** Nothing is ever deleted, so the archive is the record —
  but there is no log of edits.
- **SQLite, no migrations to speak of.** Schema changes are additive, guarded by
  `PRAGMA table_info` checks.

## Not yet applicable

The Jira promote feature is designed but not built. When it lands it introduces
the first real secret in this project (a Jira personal access token) and the
first outbound request. Both need their own entries here at that point: token
in `.env` only, and the Jira base URL validated against SSRF before it is
fetched.

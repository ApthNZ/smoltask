# Security status

## Posture

smoltask is a single-user tool that runs on the machine of the person using it.
It has no authentication, no multi-user model and no outbound network access.
The threat model is **"ordinary input reaches the database"**, not "an attacker
has a foothold on the network" — if someone can reach the port, they can already
read and write every task, by design.

## What is enforced

| Control | Where | Test |
|---|---|---|
| Parameterised SQL everywhere; no string-built queries | `db.py` | `test_title_is_data_not_sql`, `test_search_is_data_not_sql` |
| Archive `sort`/`dir`/`outcome` matched against an allowlist, never interpolated | `db.py:list_archive` | `test_archive_sort_is_allowlisted` |
| Titles: control characters and null bytes stripped, length bounded 1–80 | `app.py:clean_title` | `test_title_control_characters_are_stripped`, `test_oversized_titles_are_rejected` |
| Dates validated as real calendar dates before reaching SQL | `app.py:validate_due` | `test_due_dates_are_validated` |
| Quadrants constrained to 1–4 at the API *and* by a `CHECK` in the schema | `app.py`, `db.py` | `test_quadrants_are_bounded` |
| Static mount cannot escape its directory | `app.py` | `test_static_mount_does_not_escape` |
| No database path or filesystem detail in any response | `app.py` | `test_no_route_exposes_the_database_path` |
| Ids outside SQLite's 64-bit range are a miss, not a driver error | `db.py:is_possible_id` | `test_an_id_too_large_for_sqlite_is_a_miss_not_a_crash` |
| No reachable input returns 5xx; schema invariants survive any operation order | repo-wide | `tests/test_robustness.py` |
| No hardcoded secrets in the tree | repo-wide | `test_no_hardcoded_secrets` |
| Database file is not tracked by git | `.gitignore` | `test_database_file_is_not_tracked` |

## Accepted risks

- **No authentication.** Documented in [SECURITY.md](SECURITY.md). Anyone who
  can reach the port has full access. Mitigation is deployment, not code: bind
  to localhost.
- **No rate limiting.** A single-user local app has no one to limit.
- **No CSRF protection.** There are no credentials to ride on and no cross-site
  state to protect; the API is unauthenticated either way.
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

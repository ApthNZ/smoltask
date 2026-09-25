# Security

## Read this first

smoltask has **no authentication**. There is no login, no session, no user
model. Anyone who can open the page can read, add and complete every task. That
is a deliberate choice for a single-user notebook, and it makes the app
unsuitable for anything else.

**Do not expose it to the internet.** Run it on localhost — which is how it is
meant to be run — or on a private network you control, or behind a reverse
proxy that handles authentication for it.

Tasks are the things you have written down about your day. Treat the database
file as you would treat the notebook it replaces.

The code was written by an AI and has not been audited by a human. See the
warning at the top of the [README](README.md).

## Reporting something

If you find a vulnerability, please open an issue. Given the above, "there is
no authentication" is not a vulnerability — it is documented behaviour. Things
that *would* be worth reporting: injection through a validated field, a path
that escapes the static directory, a crash reachable from ordinary input, or
anything that lets a request read files it shouldn't.

This is a hobby project with no security team and no response-time commitment.

## What the code does enforce

Details, including the accepted risks, are in
[SECURITY_STATUS.md](SECURITY_STATUS.md). In summary: every SQL query is
parameterised, the archive's sort and filter arguments are matched against an
allowlist rather than interpolated, titles are stripped of control characters
and bounded at 80 characters, dates and quadrants are validated before they
reach SQL, and static files are served by a mount that confines paths. The app
also refuses requests that name a host it was not told about (DNS rebinding)
and writes that a browser marks as coming from another site (CSRF), and sends a
strict Content-Security-Policy that forbids framing.
`tests/test_security.py` covers each of those.

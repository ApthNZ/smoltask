"""Security tests.

smoltask has no authentication by design — it is a single-user notebook, and
the threat model is "ordinary input reaches the database", not "an attacker has
network access". These tests therefore cover what the app can still get wrong on
its own: injection through the fields it does accept, an allowlisted sort that
stops being allowlisted, traversal out of the static directory, and secrets
committed to the tree.

See SECURITY_STATUS.md for the posture these tests defend.
"""

import re

import pytest

import db
from conftest import ROOT, add

SOURCE_FILES = [
    p
    for p in list(ROOT.glob("*.py")) + list(ROOT.glob("static/*.js")) + list(ROOT.glob("tests/*.py"))
    if p.name != "test_security.py"  # this file quotes the patterns it hunts for
]


# --- secrets -----------------------------------------------------------------


def test_no_hardcoded_secrets():
    patterns = [
        r'api[_-]?key\s*=\s*["\'][^"\']+["\']',
        r'password\s*=\s*["\'][^"\']+["\']',
        r'secret\s*=\s*["\'][^"\']+["\']',
        r'token\s*=\s*["\'][^"\']+["\']',
        r"webhook.*discord\.com",
        r"postgresql://.*:.*@",
        r"gh[pousr]_[A-Za-z0-9]{16,}",
    ]
    for path in SOURCE_FILES:
        text = path.read_text()
        for pattern in patterns:
            assert not re.search(pattern, text, re.IGNORECASE), f"{path.name} matches {pattern}"


def test_database_file_is_not_tracked():
    ignored = (ROOT / ".gitignore").read_text()
    for pattern in ("*.db", "data/", ".env"):
        assert pattern in ignored, f".gitignore is missing {pattern}"


def tracked_files():
    """What git would publish. Deliberately not a directory glob: CLAUDE_LOCAL.md
    is gitignored precisely so it *can* hold the deployment detail this test
    forbids everywhere else."""
    import subprocess

    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    return [ROOT / name for name in result.stdout.split() if (ROOT / name).is_file()]


def test_no_deployment_detail_in_tracked_files():
    """Every commit here is destined to be public, so no tracked file may name a
    host, an address or an account. The pre-push hook is the real gate; this one
    fails at the commit instead of at the push."""
    # Loopback and "any address" are documentation, not disclosure: they say
    # where to bind, and they are the same on every machine in the world.
    generic = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}
    ipv4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    for path in tracked_files():
        if path.name == "test_security.py" or path.suffix in (".png", ".svg"):
            continue
        for line in path.read_text(errors="ignore").splitlines():
            found = [a for a in ipv4.findall(line) if a not in generic]
            assert not found, f"{path.name}: {found} in {line.strip()[:60]}"


def test_local_notes_are_not_tracked():
    """The file that holds the homelab detail must never be committed."""
    assert not any(p.name == "CLAUDE_LOCAL.md" for p in tracked_files())
    assert "CLAUDE_LOCAL.md" in (ROOT / ".gitignore").read_text()


# --- injection ---------------------------------------------------------------


def test_title_is_data_not_sql(client):
    hostile = "'; DROP TABLE task; --"
    add(client, hostile)
    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks[0]["title"] == hostile
    # The table is still there, which is the actual assertion.
    assert client.get("/health").json()["status"] == "ok"


def test_search_is_data_not_sql(client):
    add(client, "Email bob")
    response = client.get("/api/archive", params={"q": "' OR 1=1 --"})
    assert response.status_code == 200
    assert response.json()["tasks"] == []


def test_search_wildcards_are_literal(client):
    """A `%` typed into the filter box is a percent sign, not "match anything"."""
    task = add(client, "Email bob")
    client.post(f"/api/tasks/{task['id']}/complete")
    assert client.get("/api/archive", params={"q": "%"}).json()["tasks"] == []
    assert len(client.get("/api/archive", params={"q": "bob"}).json()["tasks"]) == 1


def test_archive_sort_is_allowlisted(client):
    for bad_sort in ("title; DROP TABLE task", "rowid", "", "created_at"):
        assert client.get("/api/archive", params={"sort": bad_sort}).status_code == 400
    for bad_dir in ("asc; --", "up"):
        assert client.get("/api/archive", params={"dir": bad_dir}).status_code == 400
    assert client.get("/api/archive", params={"outcome": "cancelled"}).status_code == 400


def test_patch_cannot_reach_unlisted_columns(client, conn):
    task = add(client, "Email bob")
    response = client.patch(
        f"/api/tasks/{task['id']}",
        json={"finished_at": "2020-01-01", "outcome": "done", "jira_key": "X-1"},
    )
    # Nothing in the body is a patchable field, so there is nothing to change.
    assert response.status_code == 400
    assert client.get("/api/tasks").json()["tasks"][0]["finished_at"] is None


# --- input validation --------------------------------------------------------


def test_title_control_characters_are_stripped(client):
    task = add(client, "Email\x00 bob\r\nabout\tthe ‮ numbers")
    assert "\x00" not in task["title"]
    assert "\n" not in task["title"] and "\r" not in task["title"]
    assert "‮" not in task["title"]
    assert task["title"] == "Email bob about the numbers"


def test_oversized_titles_are_rejected(client):
    assert client.post("/api/tasks", json={"title": "x" * 81}).status_code == 400
    assert client.post("/api/tasks", json={"title": "x" * 80}).status_code == 201
    assert client.post("/api/tasks", json={"title": "   "}).status_code == 400
    assert client.post("/api/tasks", json={"title": "x" * 100000}).status_code == 422


def test_the_schema_enforces_the_limit_too(conn):
    """The API is not the only thing standing between 80 characters and the
    database — a CHECK constraint says the same thing."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO task (title, created_at) VALUES (?, ?)", ("x" * 81, db.now())
        )


def test_due_dates_are_validated(client):
    task = add(client, "Email bob")
    for bad_date in ("2026-02-30", "not-a-date", "26-09-18", "2026-13-01", "'; --"):
        assert client.patch(f"/api/tasks/{task['id']}", json={"due": bad_date}).status_code == 400
    assert client.patch(f"/api/tasks/{task['id']}", json={"due": "2026-09-18"}).status_code == 200


def test_a_date_on_create_is_validated_like_any_other(client):
    for due in ("2026-02-30", "friday", "2026-9-1", "2026-09-25; DROP TABLE task"):
        response = client.post("/api/tasks", json={"title": "Call Bob", "due": due})
        assert response.status_code == 400, due
    assert client.get("/api/tasks").json()["tasks"] == [], "a rejected create wrote a row"


def test_labels_are_data_not_markup_or_sql(client, conn):
    """They reach the page through textContent, never innerHTML, so they are
    stored exactly as typed — escaping here would show the escapes."""
    import copy

    value = copy.deepcopy(db.DEFAULT_LABELS)
    value["quadrants"][0]["name"] = "<b>x</b>'); --"
    value["quadrants"][1]["definition"] = "<img src=x onerror=alert(1)>"
    saved = client.put("/api/settings", json={"labels": value}).json()["labels"]
    assert saved["quadrants"][0]["name"] == "<b>x</b>'); --"
    assert conn.execute("SELECT COUNT(*) FROM task").fetchone()[0] == 0
    assert "innerHTML" not in (ROOT / "static" / "app.js").read_text()


def test_label_control_characters_are_stripped(client):
    import copy

    value = copy.deepcopy(db.DEFAULT_LABELS)
    value["quadrants"][0]["name"] = "To\x00da\x1by"
    value["matrix"]["rows"][0] = "imp\u202eortant"
    saved = client.put("/api/settings", json={"labels": value}).json()["labels"]
    assert saved["quadrants"][0]["name"] == "Today"
    assert saved["matrix"]["rows"][0] == "important"


def test_oversized_label_bodies_are_refused_before_cleaning(client):
    import copy

    value = copy.deepcopy(db.DEFAULT_LABELS)
    value["quadrants"][0]["name"] = "x" * 5000
    assert client.put("/api/settings", json={"labels": value}).status_code == 422


def test_quadrants_are_bounded(client):
    task = add(client, "Email bob")
    for bad_quadrant in (0, 5, -1, 99):
        assert client.patch(f"/api/tasks/{task['id']}", json={"quadrant": bad_quadrant}).status_code == 400
    assert client.patch(f"/api/tasks/{task['id']}", json={"quadrant": None}).status_code == 200


def test_quadrant_check_exists_in_the_schema(conn):
    import sqlite3

    task_id = conn.execute(
        "INSERT INTO task (title, created_at) VALUES ('x', ?)", (db.now(),)
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE task SET quadrant = 7 WHERE id = ?", (task_id,))


def test_a_finished_task_always_has_an_outcome(conn):
    """The schema will not let a task be half off the page."""
    import sqlite3

    task_id = conn.execute(
        "INSERT INTO task (title, created_at) VALUES ('x', ?)", (db.now(),)
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE task SET finished_at = ? WHERE id = ?", (db.now(), task_id))


# --- surface -----------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/static/../app.py",
        "/static/../../etc/passwd",
        "/static/%2e%2e/app.py",
        "/static/....//app.py",
    ],
)
def test_static_mount_does_not_escape(client, path):
    response = client.get(path)
    assert response.status_code in (400, 404)
    assert "SMOLTASK_DB" not in response.text


def test_static_serves_only_what_it_should(client):
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/../db.py").status_code in (400, 404)


def test_no_route_exposes_the_database_path(client):
    add(client, "Email bob")
    for path in ("/health", "/api/tasks", "/api/archive"):
        body = client.get(path).text
        assert db.DB_PATH not in body
        assert "/tmp" not in body and "sqlite" not in body.lower()


def test_health_leaks_nothing(client):
    assert set(client.get("/health").json()) == {"status", "open"}


# --- who may talk to it: Host, Origin, Sec-Fetch-Site (guard.py) --------------

# What a form on another site, or a `fetch(..., {mode: "no-cors"})` from one,
# looks like when it arrives. No preflight is sent for either, so these reach
# the app unless the app itself refuses them.
CROSS_SITE_FORM = {"Origin": "https://evil.example",
                   "Content-Type": "application/x-www-form-urlencoded"}
CROSS_SITE_FETCH = {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"}


@pytest.mark.parametrize("headers", [CROSS_SITE_FORM, CROSS_SITE_FETCH,
                                     {"Sec-Fetch-Site": "same-site"},
                                     {"Origin": "null"},
                                     {"Origin": "http://testserver:9999"}])
@pytest.mark.parametrize("action", ["complete", "restore", "triaged"])
def test_a_cross_site_write_is_refused_and_changes_nothing(client, headers, action):
    """The body-less POSTs were the live hole: a simple request, no preflight,
    and a side effect that lands even though the answer cannot be read."""
    task = add(client, "Email bob")
    if action == "restore":
        client.post(f"/api/tasks/{task['id']}/complete")
    before = client.get("/api/tasks").json()
    response = client.post(f"/api/tasks/{task['id']}/{action}", headers=headers)
    assert response.status_code == 403
    assert client.get("/api/tasks").json() == before


def test_every_write_route_is_covered_not_just_the_body_less_ones(client):
    task = add(client, "Email bob")
    for method, path, body in [
        ("POST", "/api/tasks", {"title": "x"}),
        ("PATCH", f"/api/tasks/{task['id']}", {"quadrant": 1}),
        ("PUT", "/api/settings", {"labels": db.DEFAULT_LABELS}),
    ]:
        response = client.request(method, path, json=body, headers=CROSS_SITE_FETCH)
        assert response.status_code == 403, path


def test_the_page_own_requests_still_work(client):
    """What a browser attaches to a fetch from the app's own page."""
    same_origin = {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
    task = client.post("/api/tasks", json={"title": "Email bob"}, headers=same_origin)
    assert task.status_code == 201
    done = client.post(f"/api/tasks/{task.json()['id']}/complete", headers=same_origin)
    assert done.status_code == 200 and done.json()["outcome"] == "done"
    # A browser too old to send Sec-Fetch-Site still sends a matching Origin.
    assert client.post("/api/tasks", json={"title": "x"},
                       headers={"Origin": "http://testserver"}).status_code == 201


def test_scripts_without_browser_headers_still_work(client):
    """curl and scripts send neither header, and scripted access is intended."""
    task = client.post("/api/tasks", json={"title": "Email bob"})
    assert task.status_code == 201
    assert client.post(f"/api/tasks/{task.json()['id']}/complete").status_code == 200


def test_reads_are_not_subject_to_the_origin_check(client):
    """A cross-site GET cannot read the answer without CORS, and a navigation
    from a bookmark is a GET. Only writes are refused."""
    assert client.get("/api/tasks", headers=CROSS_SITE_FETCH).status_code == 200


@pytest.mark.parametrize("path", ["/", "/health", "/api/tasks", "/static/app.js"])
def test_an_unknown_host_is_refused_everywhere(client, path):
    """DNS rebinding: a page on attacker.example re-points its name at this
    machine, and the browser then treats the app as the attacker's own origin.
    The Host header is the one thing that still says which name was used."""
    response = client.get(path, headers={"Host": "attacker.example"})
    assert response.status_code == 400
    assert "Email" not in response.text


def test_the_host_allowlist_comes_from_the_environment(monkeypatch):
    import guard

    monkeypatch.delenv("SMOLTASK_ALLOWED_HOSTS", raising=False)
    assert guard.allowed_hosts("SMOLTASK_ALLOWED_HOSTS") == {"localhost", "127.0.0.1", "[::1]"}
    monkeypatch.setenv("SMOLTASK_ALLOWED_HOSTS", " Notebook.example:8108 , [FD00::1]:8108,,")
    assert guard.allowed_hosts("SMOLTASK_ALLOWED_HOSTS") == {"notebook.example", "[fd00::1]"}


def test_hosts_are_compared_without_their_port():
    import guard

    assert guard.host_only("LOCALHOST:8108") == "localhost"
    assert guard.host_only("[::1]:8108") == "[::1]", "not split on the first colon"
    assert guard.host_only("[::1]") == "[::1]"


def test_ipv6_loopback_is_allowed_by_default(client):
    assert client.get("/health", headers={"Host": "[::1]:8108"}).status_code == 200


# --- what a loaded page may do ------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/api/tasks", "/health",
                                  "/api/tasks/999999/complete"])
def test_security_headers_are_on_every_response(client, path):
    method = client.post if path.endswith("/complete") else client.get
    headers = method(path).headers
    csp = headers["content-security-policy"]
    for directive in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'",
                      "base-uri 'none'", "form-action 'self'"):
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"


def test_refusals_carry_the_headers_too(client):
    assert "content-security-policy" in client.get(
        "/", headers={"Host": "attacker.example"}).headers
    assert "content-security-policy" in client.post(
        "/api/tasks", json={"title": "x"}, headers=CROSS_SITE_FETCH).headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_docs_are_not_served(client, path):
    assert client.get(path).status_code == 404


# --- text that reads differently from how it is stored ------------------------


def test_joined_emoji_survive_but_bidi_controls_do_not(client):
    """Category C was stripped wholesale, which took the zero-width joiner out
    of a family emoji and left three people where one family had been."""
    family = "\U0001F468‍\U0001F469‍\U0001F467"
    heart = "❤️"
    task = add(client, f"Photos {family} {heart}")
    assert task["title"] == f"Photos {family} {heart}"
    for control in ("‪", "‫", "‬", "‭", "‮",
                    "⁦", "⁧", "⁨", "⁩"):
        assert add(client, f"a{control}b")["title"] == "ab", repr(control)


def test_code_points_this_python_does_not_know_are_kept():
    """Unassigned in *this* interpreter's tables is not the same as meaningless:
    a newer emoji is unassigned to an older Python, and used to vanish."""
    import unicodedata

    import app

    unassigned = next(chr(c) for c in range(0x1FA00, 0x1FB00)
                      if unicodedata.category(chr(c)) == "Cn")
    assert app.clean_line(f"x{unassigned}y") == f"x{unassigned}y"
    assert app.clean_line("xy") == "xy", "private use is still stripped"

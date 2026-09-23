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

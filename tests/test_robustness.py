"""Nothing reachable from ordinary input may 500, and the schema's invariants
must survive any sequence of operations.

The out-of-range id case here was a real 500: SQLite stores integers in 64 bits,
and handing the driver a larger one raises OverflowError rather than simply not
matching, so "no such task" came back as a crash.
"""

import itertools
import random
import string

import pytest

import db
from conftest import add

HOSTILE_TITLES = [
    "", " ", "\x00", "\n\n\n", "x" * 80, "x" * 81, "'; DROP TABLE task; --",
    "<script>alert(1)</script>", "%", "_", "\\", "../../etc/passwd", "🙂" * 40,
    "‮evil", "null", "0", "a\tb\rc\nd", "{}", "[]",
]
HOSTILE_DUES = [
    None, "", "2026-02-30", "0000-00-00", "9999-12-31", "-1", "2026-9-8",
    "20260918", "2026-09-18T00:00:00", "'; --", "%", "x" * 300, "2026-13-01",
]
HOSTILE_QUADRANTS = [None, 0, 5, -1, 2**31, True, 1.5, "1", "x", [], {}]
OUT_OF_RANGE_IDS = [2**63, 2**64, 10**30, -(2**63) - 1]


def test_an_id_too_large_for_sqlite_is_a_miss_not_a_crash(client):
    for task_id in OUT_OF_RANGE_IDS:
        for path in ("complete", "restore", "triaged"):
            response = client.post(f"/api/tasks/{task_id}/{path}")
            assert response.status_code == 404, f"{path} {task_id}: {response.status_code}"
        assert client.patch(f"/api/tasks/{task_id}", json={"quadrant": 1}).status_code == 404


def test_is_possible_id_rejects_what_cannot_name_a_row():
    assert db.is_possible_id(1)
    assert not db.is_possible_id(2**63)
    assert not db.is_possible_id(True), "a bool is not an id"
    assert not db.is_possible_id("1")
    assert not db.is_possible_id(1.0)


@pytest.mark.parametrize("title", HOSTILE_TITLES)
def test_no_title_crashes_the_creator(client, title):
    assert client.post("/api/tasks", json={"title": title}).status_code < 500


@pytest.mark.parametrize("payload", [{}, {"title": None}, {"title": 1}, {"title": []},
                                     {"title": {"a": 1}}, {"nope": "x"}, [], "string", 42])
def test_no_body_shape_crashes_the_creator(client, payload):
    assert client.post("/api/tasks", json=payload).status_code < 500


@pytest.mark.parametrize("due", HOSTILE_DUES)
def test_no_date_crashes_the_patcher(client, due):
    task = add(client, "subject")
    assert client.patch(f"/api/tasks/{task['id']}", json={"due": due}).status_code < 500


@pytest.mark.parametrize("quadrant", HOSTILE_QUADRANTS)
def test_no_quadrant_crashes_the_patcher(client, quadrant):
    task = add(client, "subject")
    assert client.patch(f"/api/tasks/{task['id']}", json={"quadrant": quadrant}).status_code < 500


def test_no_archive_query_crashes_it(client):
    sorts = ["created", "finished", "", "rowid", "id; DROP TABLE task"]
    dirs = ["asc", "desc", "", "ASC", "asc;--"]
    outcomes = ["", "done", "promoted", "cancelled", "'; --"]
    for sort, direction, outcome in itertools.product(sorts, dirs, outcomes):
        response = client.get("/api/archive",
                              params={"sort": sort, "dir": direction, "outcome": outcome})
        assert response.status_code < 500, f"{sort}/{direction}/{outcome}"
    for query in HOSTILE_TITLES + ["%" * 100, "\\" * 50]:
        assert client.get("/api/archive", params={"q": query}).status_code < 500


def test_the_invariants_survive_a_soak(client, conn):
    """Six hundred operations in a seeded random order. The schema's CHECKs are
    the real assertion — if any sequence can produce a half-finished row, this
    is where it shows up."""
    random.seed(7)
    ids = [add(client, "".join(random.choices(string.ascii_letters, k=20)))["id"]
           for _ in range(30)]
    for _ in range(600):
        task_id = random.choice(ids)
        response = random.choice([
            lambda: client.post(f"/api/tasks/{task_id}/complete"),
            lambda: client.post(f"/api/tasks/{task_id}/restore"),
            lambda: client.post(f"/api/tasks/{task_id}/triaged"),
            lambda: client.patch(f"/api/tasks/{task_id}",
                                 json={"quadrant": random.choice([None, 1, 2, 3, 4])}),
            lambda: client.patch(f"/api/tasks/{task_id}",
                                 json={"due": random.choice([None, "2026-09-18", "2027-01-01"])}),
            lambda: client.get("/api/tasks"),
            lambda: client.get("/api/archive"),
        ])()
        assert response.status_code < 500

    checks = {
        "half-finished rows":
            "SELECT COUNT(*) FROM task WHERE (finished_at IS NULL) != (outcome IS NULL)",
        "orphan jira keys":
            "SELECT COUNT(*) FROM task WHERE jira_key IS NOT NULL AND outcome != 'promoted'",
        "oversize titles": "SELECT COUNT(*) FROM task WHERE length(title) > 80",
        "bad quadrants":
            "SELECT COUNT(*) FROM task WHERE quadrant IS NOT NULL AND quadrant NOT IN (1,2,3,4)",
    }
    for name, sql in checks.items():
        assert conn.execute(sql).fetchone()[0] == 0, name

    # And the page still renders something coherent.
    body = client.get("/api/tasks").json()
    assert all(t["finished_at"] is None for t in body["tasks"])
    assert all(t["reason"] in ("unsorted", "disowned", "due", "stale")
               for t in body["triage"]["queue"])

"""Settings: what the priorities are called, and the axes of the triage grid.

Cosmetic by construction. The behaviour hangs off the quadrant number, so these
tests also check that renaming a quadrant changes nothing it does.
"""

import copy

import pytest

import db
from conftest import add


def labels(**overrides):
    value = copy.deepcopy(db.DEFAULT_LABELS)
    for n, name in overrides.get("names", {}).items():
        value["quadrants"][n - 1]["name"] = name
    for n, text in overrides.get("definitions", {}).items():
        value["quadrants"][n - 1]["definition"] = text
    if "columns" in overrides:
        value["matrix"]["columns"] = overrides["columns"]
    if "rows" in overrides:
        value["matrix"]["rows"] = overrides["rows"]
    return value


def put(client, value):
    return client.put("/api/settings", json={"labels": value})


def test_a_fresh_notebook_has_the_defaults(client):
    body = client.get("/api/settings").json()
    assert body["labels"] == db.DEFAULT_LABELS
    assert body["defaults"] == db.DEFAULT_LABELS
    assert client.get("/api/tasks").json()["labels"] == db.DEFAULT_LABELS


def test_renaming_a_priority_sticks(client):
    response = put(client, labels(names={1: "Today", 4: "Someday"},
                                  definitions={1: "before I go home"}))
    assert response.status_code == 200
    saved = response.json()["labels"]
    assert [q["name"] for q in saved["quadrants"]] == ["Today", "Next", "Last", "Someday"]
    assert saved["quadrants"][0]["definition"] == "before I go home"
    # The page picks it up on its next load, and so does the settings screen.
    assert client.get("/api/tasks").json()["labels"] == saved
    assert client.get("/api/settings").json()["labels"] == saved


def test_the_defaults_do_not_move_when_the_labels_do(client):
    """Restore defaults fills the form from `defaults`. A save must not have
    rewritten what the defaults are."""
    put(client, labels(names={2: "Soon"}))
    assert client.get("/api/settings").json()["defaults"] == db.DEFAULT_LABELS
    assert db.DEFAULT_LABELS["quadrants"][1]["name"] == "Next"


def test_restoring_defaults_is_just_saving_them(client):
    put(client, labels(names={2: "Soon"}))
    assert put(client, db.DEFAULT_LABELS).json()["labels"] == db.DEFAULT_LABELS


def test_definitions_and_axes_may_be_empty(client):
    value = labels(definitions={4: ""}, columns=["", ""], rows=["", ""])
    saved = put(client, value).json()["labels"]
    assert saved["quadrants"][3]["definition"] == ""
    assert saved["matrix"] == {"columns": ["", ""], "rows": ["", ""]}


def test_a_name_is_required(client):
    response = put(client, labels(names={3: "   "}))
    assert response.status_code == 400
    assert "Priority 3 needs a name" in response.json()["detail"]


def test_two_priorities_cannot_share_a_name(client):
    """`1` and `3` would file into sections that look identical."""
    response = put(client, labels(names={1: "Soon", 3: "soon"}))
    assert response.status_code == 400
    assert "share a name" in response.json()["detail"]


def test_whitespace_is_tidied_as_a_title_is(client):
    saved = put(client, labels(names={1: "  To\tday  "},
                               definitions={1: "  a  line\nof text "})).json()["labels"]
    assert saved["quadrants"][0] == {"name": "To day", "definition": "a line of text"}


@pytest.mark.parametrize("overrides, field", [
    ({"names": {1: "x" * (db.MAX_NAME + 1)}}, "name"),
    ({"definitions": {2: "x" * (db.MAX_DEFINITION + 1)}}, "definition"),
    ({"columns": ["x" * (db.MAX_AXIS + 1), "b"]}, "axis"),
])
def test_labels_are_bounded(client, overrides, field):
    response = put(client, labels(**overrides))
    assert response.status_code == 400, field
    assert "at most" in response.json()["detail"]


def test_labels_at_the_limit_are_accepted(client):
    value = labels(names={1: "x" * db.MAX_NAME},
                   definitions={1: "y" * db.MAX_DEFINITION},
                   columns=["z" * db.MAX_AXIS, "w"])
    assert put(client, value).status_code == 200


@pytest.mark.parametrize("mutate", [
    lambda v: v["quadrants"].pop(),
    lambda v: v["quadrants"].append({"name": "Fifth", "definition": ""}),
    lambda v: v["matrix"]["columns"].pop(),
    lambda v: v["matrix"]["rows"].append("third"),
    lambda v: v.pop("matrix"),
    lambda v: v["quadrants"][0].pop("name"),
    lambda v: v["quadrants"][0].__setitem__("name", 7),
])
def test_the_shape_is_enforced(client, mutate):
    value = labels()
    mutate(value)
    assert put(client, value).status_code == 422
    assert client.get("/api/settings").json()["labels"] == db.DEFAULT_LABELS


def test_a_failed_save_changes_nothing(client):
    put(client, labels(names={1: "Today"}))
    put(client, labels(names={1: "Same", 2: "same"}))
    assert client.get("/api/settings").json()["labels"]["quadrants"][0]["name"] == "Today"


def test_a_damaged_row_falls_back_to_the_defaults(client, conn):
    """A label can be lost; the page cannot be. Nothing but the API writes this
    row, but a hand-edited database should cost a label, not a 500."""
    for junk in ("not json", "[]", '{"quadrants": []}', "null",
                 '{"quadrants": [{"name": ""}], "matrix": {}}'):
        conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('labels', ?)", (junk,))
        conn.commit()
        assert client.get("/api/settings").json()["labels"] == db.DEFAULT_LABELS, junk
        assert client.get("/api/tasks").status_code == 200


def test_renaming_changes_nothing_a_quadrant_does(client):
    """1 still goes stale, 4 is still the one a date contradicts, and the page
    still sorts by number — whatever they are called."""
    put(client, labels(names={1: "Zebra", 2: "Apple", 3: "Mango", 4: "Banana"}))
    task = add(client, "Promised a date", quadrant=4, due="2026-09-30")
    queue = client.get("/api/tasks").json()["triage"]["queue"]
    assert [(t["id"], t["reason"]) for t in queue] == [(task["id"], "disowned")]
    for quadrant in (3, 1, 2):
        add(client, f"In {quadrant}", quadrant=quadrant)
    order = [t["quadrant"] for t in client.get("/api/tasks").json()["tasks"]]
    assert order == [1, 2, 3, 4]


def test_settings_survive_a_restart(client, dbfile):
    put(client, labels(names={1: "Today"}))
    fresh = db.connect(dbfile)
    try:
        db.init_db(fresh)  # what startup does; it must not reset anything
        assert db.get_labels(fresh)["quadrants"][0]["name"] == "Today"
    finally:
        fresh.close()

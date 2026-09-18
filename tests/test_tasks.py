"""Task behaviour: the order of the page, the triage queue, and the archive.

These are the rules from DESIGN.md rather than the HTTP surface — the things
that would still be wrong if every endpoint returned 200.
"""

from datetime import date, timedelta

import db
from conftest import add


def titles(client):
    return [t["title"] for t in client.get("/api/tasks").json()["tasks"]]


# --- the order of the page ---------------------------------------------------


def test_quadrants_rank_the_page(client):
    add(client, "never", quadrant=4)
    add(client, "now", quadrant=1)
    add(client, "last", quadrant=3)
    add(client, "next", quadrant=2)
    assert titles(client) == ["now", "next", "last", "never"]


def test_unsorted_sorts_to_the_bottom(client):
    """An untriaged task has not earned a position. An inbox on top would rank
    the most recently captured thing as the most important thing."""
    add(client, "untriaged")
    add(client, "never mind", quadrant=4)
    assert titles(client) == ["never mind", "untriaged"]


def test_within_a_quadrant_dates_come_first_then_age(client):
    add(client, "undated", quadrant=1)
    add(client, "later", quadrant=1, due="2026-12-01")
    add(client, "sooner", quadrant=1, due="2026-09-20")
    assert titles(client) == ["sooner", "later", "undated"]


def test_undated_tasks_hold_their_creation_order(client):
    for name in ("first", "second", "third"):
        add(client, name, quadrant=2)
    assert titles(client) == ["first", "second", "third"]


def test_a_quadrant_outranks_a_due_date(client):
    """A `Last` task due tomorrow still sorts below every `Now` task. That is
    the design, and it is why triage surfaces due dates separately."""
    add(client, "urgent to someone else", quadrant=3, due="2026-09-18")
    add(client, "actually important", quadrant=1)
    assert titles(client) == ["actually important", "urgent to someone else"]


# --- triage ------------------------------------------------------------------


def queue(client):
    body = client.get("/api/tasks").json()
    return [(t["title"], t["reason"]) for t in body["triage"]["queue"]]


def test_unsorted_tasks_are_queued_for_triage(client):
    add(client, "untriaged")
    assert queue(client) == [("untriaged", "unsorted")]


def insert(conn, title, **fields):
    """Insert without going through PATCH, which would mark the task triaged
    today and hide it from the very queue the test is about."""
    columns = ", ".join(["title", "created_at", *fields])
    marks = ", ".join(["?"] * (2 + len(fields)))
    conn.execute(
        f"INSERT INTO task ({columns}) VALUES ({marks})",
        (title, db.now(), *fields.values()),
    )
    conn.commit()


def test_a_task_due_soon_is_queued_whatever_its_quadrant(conn):
    """Sorting by quadrant first would bury a commitment made to someone else.
    Triage surfaces it regardless of where it sits on the page."""
    tomorrow = (date.fromisoformat(db.today()) + timedelta(days=1)).isoformat()
    insert(conn, "promised for tomorrow", quadrant=3, due=tomorrow)
    assert [(t["title"], t["reason"]) for t in db.triage_queue(conn)["queue"]] == [
        ("promised for tomorrow", "due")
    ]


def test_a_dated_never_task_is_queued(conn):
    """A date on a task ranked Never is a date promised to someone and disowned
    in the same breath. Triage is where contradictions surface."""
    far = (date.fromisoformat(db.today()) + timedelta(days=90)).isoformat()
    insert(conn, "get back to legal", quadrant=db.NEVER, due=far)
    assert [(t["title"], t["reason"]) for t in db.triage_queue(conn)["queue"]] == [
        ("get back to legal", "disowned")
    ]


def test_an_undated_never_task_is_left_alone(conn):
    """Never without a date is an honest answer, not a contradiction."""
    insert(conn, "reconcile the old invoices", quadrant=db.NEVER)
    assert db.triage_queue(conn)["queue"] == []


def test_disowned_outranks_due_soon(conn):
    """Both apply to a dated Never task due tomorrow. It appears once, and the
    reason shown is the one the user did not already know."""
    tomorrow = (date.fromisoformat(db.today()) + timedelta(days=1)).isoformat()
    insert(conn, "promised, and disowned", quadrant=db.NEVER, due=tomorrow)
    queue = db.triage_queue(conn)["queue"]
    assert len(queue) == 1
    assert queue[0]["reason"] == "disowned"


def test_unsorted_still_outranks_everything(conn):
    """An untriaged task has no quadrant, so it cannot also be disowned — but
    the ordering is worth pinning down."""
    tomorrow = (date.fromisoformat(db.today()) + timedelta(days=1)).isoformat()
    insert(conn, "dated never", quadrant=db.NEVER, due=tomorrow)
    insert(conn, "not sorted at all")
    assert [t["reason"] for t in db.triage_queue(conn)["queue"]] == ["unsorted", "disowned"]


def test_creating_the_contradiction_does_not_silence_it(client):
    """Ranking a dated task Never is the moment the problem appears, not the
    moment it is resolved. Marking it looked-at would hide it until tomorrow."""
    task = add(client, "get back to legal", due="2026-12-01")
    assert queue(client) == [], "setting a date counts as having looked"
    client.patch(f"/api/tasks/{task['id']}", json={"quadrant": 4})
    assert queue(client) == [("get back to legal", "disowned")]


def test_but_skipping_it_in_triage_still_silences_it_for_the_day(client):
    """Asking once is a check. Asking every time is nagging, which this app
    does not do."""
    task = add(client, "get back to legal", due="2026-12-01")
    client.patch(f"/api/tasks/{task['id']}", json={"quadrant": 4})
    assert queue(client)
    client.post(f"/api/tasks/{task['id']}/triaged")
    assert queue(client) == []
    # Still on the page, still red, still asked about tomorrow.
    assert client.get("/api/tasks").json()["triage"]["all"][0]["reason"] == "disowned"


def test_resolving_the_contradiction_does_mark_it_looked_at(client):
    """Clearing the date, or moving it out of Never, is a real answer."""
    task = add(client, "get back to legal", due="2026-12-01")
    client.patch(f"/api/tasks/{task['id']}", json={"quadrant": 4})
    client.patch(f"/api/tasks/{task['id']}", json={"due": None})
    assert queue(client) == []
    assert client.get("/api/tasks").json()["triage"]["all"] == []


def test_the_counts_name_every_reason(conn):
    insert(conn, "unsorted one")
    assert set(db.triage_queue(conn)["counts"]) == {"unsorted", "disowned", "due", "stale"}


def test_a_task_due_later_is_not_queued(conn):
    far = (date.fromisoformat(db.today()) + timedelta(days=30)).isoformat()
    insert(conn, "not yet", quadrant=2, due=far)
    assert db.triage_queue(conn)["queue"] == []


def test_setting_a_date_today_does_not_re_ask_today(client):
    """You just looked at it. The morning ritual is for tomorrow morning."""
    tomorrow = (date.fromisoformat(db.today()) + timedelta(days=1)).isoformat()
    add(client, "promised for tomorrow", quadrant=3, due=tomorrow)
    assert queue(client) == []


def test_ranking_a_dated_task_never_in_one_go_still_asks(client):
    """Even done in a single action, it is a contradiction being created."""
    tomorrow = (date.fromisoformat(db.today()) + timedelta(days=1)).isoformat()
    add(client, "promised, and disowned", quadrant=4, due=tomorrow)
    assert [r for _, r in queue(client)] == ["disowned"]


def test_a_task_triaged_today_is_not_asked_about_again(client):
    task = add(client, "untriaged")
    assert queue(client)
    client.post(f"/api/tasks/{task['id']}/triaged")
    assert queue(client) == []


def test_acting_on_a_task_counts_as_triaging_it(client):
    add(client, "untriaged")
    task_id = client.get("/api/tasks").json()["tasks"][0]["id"]
    client.patch(f"/api/tasks/{task_id}", json={"quadrant": 2})
    assert queue(client) == []


def test_a_task_stuck_in_now_goes_stale(conn):
    """Eisenhower drift: everything becomes urgent-and-important eventually.
    A week in `Now` without being looked at is the signal."""
    old = (date.fromisoformat(db.today()) - timedelta(days=db.STALE_DAYS + 1)).isoformat()
    conn.execute(
        "INSERT INTO task (title, quadrant, created_at, triaged_on) VALUES (?, 1, ?, ?)",
        ("avoiding this", f"{old}T09:00:00+00:00", old),
    )
    conn.commit()
    reasons = [t["reason"] for t in db.triage_queue(conn)["queue"]]
    assert reasons == ["stale"]


def test_a_fresh_now_task_is_not_stale(conn):
    conn.execute(
        "INSERT INTO task (title, quadrant, created_at, triaged_on) VALUES (?, 1, ?, ?)",
        ("just ranked", db.now(), db.today()),
    )
    conn.commit()
    assert db.triage_queue(conn)["queue"] == []


def test_a_task_appears_in_the_queue_once(conn):
    """Unsorted *and* due soon is still one task to look at."""
    conn.execute(
        "INSERT INTO task (title, due, created_at) VALUES (?, ?, ?)",
        ("both reasons", db.today(), db.now()),
    )
    conn.commit()
    assert len(db.triage_queue(conn)["queue"]) == 1


def test_triage_fires_on_the_first_load_of_a_day(client):
    add(client, "untriaged")
    assert client.get("/api/tasks").json()["triage"]["auto"] is True


def test_triage_does_not_fire_again_once_something_is_triaged(client):
    first = add(client, "untriaged")
    add(client, "also untriaged")
    client.post(f"/api/tasks/{first['id']}/triaged")
    body = client.get("/api/tasks").json()["triage"]
    assert body["auto"] is False
    assert len(body["queue"]) == 1, "the rest of the queue is still available on demand"


def test_triage_can_still_be_run_on_demand_after_a_clean_sweep(client):
    """The user asked for it to be re-runnable. Having triaged everything this
    morning must not make the ritual unavailable this afternoon."""
    task = add(client, "skipped this morning")
    client.post(f"/api/tasks/{task['id']}/triaged")
    body = client.get("/api/tasks").json()["triage"]
    assert body["queue"] == [], "nothing left for an automatic run"
    assert body["auto"] is False
    assert [t["title"] for t in body["all"]] == ["skipped this morning"]


def test_the_on_demand_list_still_only_offers_what_qualifies(client):
    """It lifts the already-triaged-today exclusion, not the rules themselves."""
    far = (date.fromisoformat(db.today()) + timedelta(days=30)).isoformat()
    add(client, "ranked and not due for ages", quadrant=2, due=far)
    assert client.get("/api/tasks").json()["triage"]["all"] == []


def test_an_empty_page_never_fires_triage(client):
    assert client.get("/api/tasks").json()["triage"]["auto"] is False


# --- archive -----------------------------------------------------------------


def test_the_archive_records_which_button_was_pressed(client, conn):
    ticked = add(client, "ticked")
    client.post(f"/api/tasks/{ticked['id']}/complete")
    promoted = add(client, "promoted")
    db.complete(conn, promoted["id"], outcome="promoted", jira_key="PROJ-412")

    rows = {t["title"]: t for t in client.get("/api/archive").json()["tasks"]}
    assert rows["ticked"]["outcome"] == "done"
    assert rows["ticked"]["jira_key"] is None
    assert rows["promoted"]["outcome"] == "promoted"
    assert rows["promoted"]["jira_key"] == "PROJ-412"


def test_the_archive_filters_by_outcome(client, conn):
    ticked = add(client, "ticked")
    client.post(f"/api/tasks/{ticked['id']}/complete")
    promoted = add(client, "promoted")
    db.complete(conn, promoted["id"], outcome="promoted", jira_key="PROJ-412")

    done = client.get("/api/archive", params={"outcome": "done"}).json()["tasks"]
    assert [t["title"] for t in done] == ["ticked"]


def test_the_archive_filters_by_title(client):
    for name in ("Email bob", "Call alice"):
        task = add(client, name)
        client.post(f"/api/tasks/{task['id']}/complete")
    found = client.get("/api/archive", params={"q": "bob"}).json()["tasks"]
    assert [t["title"] for t in found] == ["Email bob"]


def test_the_archive_sorts_both_ways(client):
    for name in ("first", "second"):
        task = add(client, name)
        client.post(f"/api/tasks/{task['id']}/complete")
    newest = client.get("/api/archive", params={"sort": "created", "dir": "desc"}).json()["tasks"]
    oldest = client.get("/api/archive", params={"sort": "created", "dir": "asc"}).json()["tasks"]
    assert [t["title"] for t in newest] == ["second", "first"]
    assert [t["title"] for t in oldest] == ["first", "second"]


def test_the_days_tick_count_is_reported(client):
    assert client.get("/api/tasks").json()["done_today"] == 0
    for name in ("one", "two"):
        task = add(client, name)
        client.post(f"/api/tasks/{task['id']}/complete")
    assert client.get("/api/tasks").json()["done_today"] == 2


def test_timestamps_are_local_so_day_boundaries_line_up(client):
    """Every "today" question is answered by comparing the first ten characters
    of a timestamp against the local date. A UTC timestamp puts those ten
    characters a day out for half of every day east of Greenwich, which read as
    "0 ticked today" just after midnight."""
    from datetime import datetime

    task = add(client, "ticked just now")
    client.post(f"/api/tasks/{task['id']}/complete")
    finished = client.get("/api/archive").json()["tasks"][0]["finished_at"]
    assert finished[:10] == datetime.now().date().isoformat()
    assert client.get("/api/tasks").json()["done_today"] == 1


def test_nothing_is_ever_deleted(client):
    """There is no delete button, by design. A task created by accident is
    completed like any other and lands in the archive."""
    task = add(client, "oops")
    client.post(f"/api/tasks/{task['id']}/complete")
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 405
    assert len(client.get("/api/archive").json()["tasks"]) == 1

"""SQLite storage. One file, no migrations, no ORM."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = os.environ.get("SMOLTASK_DB", os.path.join(os.path.dirname(__file__), "smoltask.db"))

# A task is "on the page" while finished_at IS NULL. The archive is the
# complement. There is no status column and no state machine: the only two ways
# off the page are ticking it and promoting it to a ticket, and `outcome`
# records which happened rather than asking anyone to choose.
SCHEMA = """
CREATE TABLE IF NOT EXISTS task (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
    quadrant    INTEGER CHECK (quadrant IN (1, 2, 3, 4)),
    due         TEXT,
    created_at  TEXT NOT NULL,
    finished_at TEXT,
    outcome     TEXT CHECK (outcome IN ('done', 'promoted')),
    jira_key    TEXT,
    triaged_on  TEXT,
    CHECK ((finished_at IS NULL) = (outcome IS NULL)),
    CHECK (jira_key IS NULL OR outcome = 'promoted')
);

CREATE INDEX IF NOT EXISTS task_open ON task(finished_at);
"""

MAX_TITLE = 80
STALE_DAYS = 7
NEVER = 4  # the quadrant that says this will not happen

# SQLite stores integers in 64 bits. A larger id cannot name a row, and handing
# one to the driver raises OverflowError rather than simply not matching — which
# turns "no such task" into a 500.
INT_MAX = 2**63 - 1
INT_MIN = -(2**63)

# Display order. Quadrants rank 1..4; unsorted sorts last because a task that
# has not been triaged has not earned a position, and an inbox on top would rank
# the most recently captured thing as the most important thing.
OPEN_ORDER = """
    ORDER BY CASE WHEN quadrant IS NULL THEN 5 ELSE quadrant END,
             due IS NULL, due, created_at, id
"""

# The archive's sort is chosen by the client, so it is matched against this map
# rather than interpolated. Anything not in here is not a sort.
ARCHIVE_SORTS = {"created": "created_at", "finished": "finished_at"}
ARCHIVE_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}
OUTCOMES = ("done", "promoted")


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_disowned(task: dict) -> bool:
    """A date promised to someone and disowned in the same breath: the task
    carries a due date and is ranked `Never`."""
    return task.get("quadrant") == NEVER and bool(task.get("due"))


def now() -> str:
    """Local time, with its offset.

    Deliberately not UTC. "Ticked today" and "due today" mean the day the person
    holding the notebook is living in, and every query that asks about a day
    does it by comparing the first ten characters of a timestamp. Storing UTC
    puts those ten characters a day out for half of every day in New Zealand,
    which showed up as the day's tick count reading zero just after midnight.

    The offset is kept so the value is still an unambiguous instant, and
    ordering is unaffected for a notebook that lives on one machine.
    """
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


# --- reads -------------------------------------------------------------------


def _row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "title": r["title"],
        "quadrant": r["quadrant"],
        "due": r["due"],
        "created_at": r["created_at"],
        "finished_at": r["finished_at"],
        "outcome": r["outcome"],
        "jira_key": r["jira_key"],
        "triaged_on": r["triaged_on"],
    }


def is_possible_id(task_id) -> bool:
    """Could this value name a row at all? Anything outside SQLite's integer
    range cannot, and asking the driver about it is an error rather than a
    miss."""
    return isinstance(task_id, int) and not isinstance(task_id, bool) \
        and INT_MIN <= task_id <= INT_MAX


def get_task(conn, task_id: int) -> dict | None:
    if not is_possible_id(task_id):
        return None
    row = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
    return _row(row) if row else None


def list_open(conn) -> list[dict]:
    rows = conn.execute(f"SELECT * FROM task WHERE finished_at IS NULL {OPEN_ORDER}")
    return [_row(r) for r in rows]


def count_finished_on(conn, day: str) -> int:
    """How many tasks left the page on a given local day — the empty-state reward."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM task WHERE finished_at IS NOT NULL "
        "AND substr(finished_at, 1, 10) = ?",
        (day,),
    ).fetchone()
    return row["n"]


def list_archive(conn, sort: str = "finished", direction: str = "desc",
                 query: str = "", outcome: str = "") -> list[dict]:
    """Finished tasks. `sort`, `direction` and `outcome` are allowlisted, not
    interpolated — the only thing the caller can put into SQL is a bound
    parameter."""
    column = ARCHIVE_SORTS.get(sort, ARCHIVE_SORTS["finished"])
    order = ARCHIVE_DIRECTIONS.get(direction, "DESC")

    where = ["finished_at IS NOT NULL"]
    params: list[object] = []
    if query:
        where.append("title LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(query)}%")
    if outcome in OUTCOMES:
        where.append("outcome = ?")
        params.append(outcome)

    sql = (
        f"SELECT * FROM task WHERE {' AND '.join(where)} "
        f"ORDER BY {column} {order}, id {order}"
    )
    return [_row(r) for r in conn.execute(sql, params)]


def _escape_like(text: str) -> str:
    """`%` and `_` in a search box are literal characters, not wildcards."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- writes ------------------------------------------------------------------


def create_task(conn, title: str) -> dict:
    cur = conn.execute(
        "INSERT INTO task (title, created_at) VALUES (?, ?)", (title, now())
    )
    conn.commit()
    return get_task(conn, cur.lastrowid)


def update_task(conn, task_id: int, fields: dict) -> dict | None:
    """Patch an open task. `fields` is built by the caller from an explicit
    allowlist; nothing reaches the column list from a request body."""
    allowed = {"title", "quadrant", "due"}
    sets = [f"{k} = ?" for k in fields if k in allowed]
    if not sets:
        return get_task(conn, task_id)
    params = [fields[k] for k in fields if k in allowed]
    params.append(task_id)
    conn.execute(f"UPDATE task SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    return get_task(conn, task_id)


def complete(conn, task_id: int, outcome: str = "done", jira_key: str | None = None) -> dict | None:
    conn.execute(
        "UPDATE task SET finished_at = ?, outcome = ?, jira_key = ? "
        "WHERE id = ? AND finished_at IS NULL",
        (now(), outcome, jira_key, task_id),
    )
    conn.commit()
    return get_task(conn, task_id)


def restore(conn, task_id: int) -> dict | None:
    """Put a task back on the page. Serves both the undo stack and the archive's
    Restore button — they are the same operation."""
    conn.execute(
        "UPDATE task SET finished_at = NULL, outcome = NULL, jira_key = NULL WHERE id = ?",
        (task_id,),
    )
    conn.commit()
    return get_task(conn, task_id)


def mark_triaged(conn, task_id: int, day: str | None) -> dict | None:
    """`None` clears the stamp, putting the task back in the queue."""
    conn.execute("UPDATE task SET triaged_on = ? WHERE id = ?", (day, task_id))
    conn.commit()
    return get_task(conn, task_id)


# --- triage ------------------------------------------------------------------


def triage_queue(conn, day: str | None = None, include_triaged: bool = False) -> dict:
    """The morning ritual's work list.

    Four reasons a task wants looking at, in the order they are presented:

    1. unsorted — it has no quadrant, so it is sitting at the bottom of the page
    2. disowned — it carries a date and is ranked `Never`, which is a date
       promised to someone and disowned in the same breath
    3. due — today or tomorrow, whatever its quadrant, because sorting by
       quadrant first would otherwise bury a commitment made to someone else
    4. stale — it has been in `Now` for a week, which usually means it was never
       really urgent or it is being avoided

    A task can qualify under more than one; it appears once, under the first
    that applies. `disowned` outranks `due` deliberately — for a dated `Never`
    task, "you said you would not do this" is the part you did not already
    know.

    A task already triaged today is excluded, which is what stops the ritual
    asking twice and what decides whether it fires on its own.

    `include_triaged` lifts that exclusion, for the on-demand run: having
    triaged everything this morning must not make the ritual unavailable at
    four in the afternoon when the day has moved on.
    """
    day = day or today()
    tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    stale_before = (date.fromisoformat(day) - timedelta(days=STALE_DAYS)).isoformat()

    def fetch(sql: str, params: tuple) -> list[dict]:
        return [_row(r) for r in conn.execute(sql, params)]

    base = "SELECT * FROM task WHERE finished_at IS NULL AND (triaged_on IS NULL OR triaged_on < ?)"
    if include_triaged:
        # `?` is still bound, so both branches take the same parameters.
        base = "SELECT * FROM task WHERE finished_at IS NULL AND (? IS NOT NULL)"

    unsorted = fetch(f"{base} AND quadrant IS NULL ORDER BY created_at, id", (day,))
    disowned = fetch(
        f"{base} AND quadrant = {NEVER} AND due IS NOT NULL ORDER BY due, id", (day,)
    )
    due = fetch(
        f"{base} AND quadrant IS NOT NULL AND due IS NOT NULL AND due <= ? ORDER BY due, id",
        (day, tomorrow),
    )
    stale = fetch(
        f"{base} AND quadrant = 1 AND COALESCE(triaged_on, substr(created_at, 1, 10)) <= ? "
        "ORDER BY created_at, id",
        (day, stale_before),
    )

    seen: set[int] = set()
    queue: list[dict] = []
    for group, reason in ((unsorted, "unsorted"), (disowned, "disowned"),
                          (due, "due"), (stale, "stale")):
        for task in group:
            if task["id"] in seen:
                continue
            seen.add(task["id"])
            queue.append({**task, "reason": reason})

    triaged_today = conn.execute(
        "SELECT 1 FROM task WHERE triaged_on = ? LIMIT 1", (day,)
    ).fetchone()

    return {
        "queue": queue,
        "counts": {
            reason: sum(1 for t in queue if t["reason"] == reason)
            for reason in ("unsorted", "disowned", "due", "stale")
        },
        # Fires on the first load of a day with work waiting. Pressing `p` runs
        # it again regardless; this flag only drives the automatic open.
        "auto": bool(queue) and not triaged_today,
    }

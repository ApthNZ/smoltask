"""smoltask: a notebook that ticks.

No auth, no users, no audit trail. It is meant to run on the machine of the
person using it. See SECURITY.md.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import date

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db

HERE = os.path.dirname(os.path.abspath(__file__))

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# --- plumbing ----------------------------------------------------------------


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = db.connect()
    try:
        db.init_db(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="smoltask", lifespan=lifespan)


def bad(message: str):
    raise HTTPException(status_code=400, detail=message)


def missing():
    raise HTTPException(status_code=404, detail="No such task.")


# --- validation --------------------------------------------------------------


def clean_line(raw: str) -> str:
    """One line of text, as a ruled line can carry it.

    Control characters are stripped rather than rejected — something pasted from
    somewhere else should not be an error, it should just lose the formatting a
    single line cannot carry anyway. Whitespace runs collapse to one space.
    """
    text = "".join(
        " " if ch in "\t\n\r" else ch
        for ch in (raw or "")
        if ch in "\t\n\r" or unicodedata.category(ch)[0] != "C"
    )
    return re.sub(r"\s+", " ", text).strip()


def clean_title(raw: str) -> str:
    """A title is one line of a notebook: `clean_line`, then a hard 1..80,
    which the schema also enforces."""
    text = clean_line(raw)
    if not text:
        raise ValueError("A task needs a title.")
    if len(text) > db.MAX_TITLE:
        raise ValueError(f"A task title is at most {db.MAX_TITLE} characters.")
    return text


def validate_due(value: str | None) -> str | None:
    """None clears the date. Anything else must be a real calendar day."""
    if value is None or value == "":
        return None
    if not DATE_RE.match(value):
        raise ValueError(f"Not a date: {value!r}. Expected YYYY-MM-DD.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Not a real date: {value!r}.") from None
    return value


def validate_quadrant(value: int | None) -> int | None:
    """None is unsorted, which is a resting state and not an error."""
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value not in (1, 2, 3, 4):
        raise ValueError("A quadrant is 1, 2, 3 or 4, or nothing at all.")
    return value


def clean_labels(raw: "LabelsIn") -> dict:
    """The user's names for the quadrants. A name is required — a section
    heading with nothing in it is a gap in the page — and two quadrants cannot
    share one, or `1` and `3` would file into sections that look the same.
    Definitions and axes may be empty; the page just leaves them out."""
    def bounded(text: str, limit: int, what: str) -> str:
        text = clean_line(text)
        if len(text) > limit:
            raise ValueError(f"{what} is at most {limit} characters.")
        return text

    quadrants = []
    for n, q in enumerate(raw.quadrants, start=1):
        name = bounded(q.name, db.MAX_NAME, f"Priority {n}'s name")
        if not name:
            raise ValueError(f"Priority {n} needs a name.")
        quadrants.append({
            "name": name,
            "definition": bounded(q.definition, db.MAX_DEFINITION, f"Priority {n}'s definition"),
        })
    names = [q["name"].casefold() for q in quadrants]
    if len(set(names)) != len(names):
        raise ValueError("Two priorities cannot share a name.")

    return {
        "quadrants": quadrants,
        "matrix": {
            key: [bounded(t, db.MAX_AXIS, "An axis label") for t in getattr(raw.matrix, key)]
            for key in ("columns", "rows")
        },
    }


def guarded(fn, *args):
    try:
        return fn(*args)
    except ValueError as exc:
        bad(str(exc))


# --- state -------------------------------------------------------------------


@app.get("/health")
def health(conn=Depends(get_conn)):
    """Touches the database, so a container with an unreadable or unwritable
    volume fails the check instead of reporting green on a broken app."""
    open_tasks = conn.execute(
        "SELECT COUNT(*) AS n FROM task WHERE finished_at IS NULL"
    ).fetchone()["n"]
    return {"status": "ok", "open": open_tasks}


@app.get("/api/tasks")
def read_tasks(conn=Depends(get_conn)):
    day = db.today()
    return {
        "today": day,
        "tasks": db.list_open(conn),
        "triage": {
            **db.triage_queue(conn, day),
            # What an on-demand run would offer once today's queue is empty.
            "all": db.triage_queue(conn, day, include_triaged=True)["queue"],
        },
        "done_today": db.count_finished_on(conn, day),
        "labels": db.get_labels(conn),
    }


@app.get("/api/archive")
def read_archive(sort: str = "finished", dir: str = "desc", q: str = "",
                 outcome: str = "", conn=Depends(get_conn)):
    if sort not in db.ARCHIVE_SORTS:
        bad("Sort by created or finished.")
    if dir not in db.ARCHIVE_DIRECTIONS:
        bad("Direction is asc or desc.")
    if outcome and outcome not in db.OUTCOMES:
        bad("Outcome is done or promoted.")
    return {"tasks": db.list_archive(conn, sort, dir, q[:db.MAX_TITLE], outcome)}


# --- tasks -------------------------------------------------------------------


class TaskIn(BaseModel):
    title: str = Field(max_length=4000)
    due: str | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, max_length=4000)
    quadrant: int | None = None
    due: str | None = None


@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskIn, conn=Depends(get_conn)):
    title = guarded(clean_title, payload.title)
    due = guarded(validate_due, payload.due)
    return db.create_task(conn, title, due)


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, payload: TaskPatch, conn=Depends(get_conn)):
    task = db.get_task(conn, task_id)
    if task is None:
        missing()
    if task["finished_at"] is not None:
        bad("That task is in the archive. Restore it first.")

    # Only the fields actually sent are touched, so a null `due` clears the date
    # while an absent `due` leaves it alone.
    sent = payload.model_fields_set
    fields: dict = {}
    if "title" in sent:
        fields["title"] = guarded(clean_title, payload.title)
    if "quadrant" in sent:
        fields["quadrant"] = guarded(validate_quadrant, payload.quadrant)
    if "due" in sent:
        fields["due"] = guarded(validate_due, payload.due)
    if not fields:
        bad("Nothing to change.")

    updated = db.update_task(conn, task_id, fields)

    # A deliberate change counts as having looked at the task, so triage does
    # not ask again the same day. The exception is a change that *creates* a
    # contradiction: ranking a dated task `Never` is the moment the problem
    # appears, not the moment it is resolved, and marking it looked-at would
    # hide it until tomorrow. The stamp is cleared instead, so triage asks —
    # once. Skipping it there silences it for the day like anything else.
    if db.is_disowned(updated) and not db.is_disowned(task):
        return db.mark_triaged(conn, task_id, None) or updated
    return db.mark_triaged(conn, task_id, db.today()) or updated


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, conn=Depends(get_conn)):
    task = db.get_task(conn, task_id)
    if task is None:
        missing()
    if task["finished_at"] is not None:
        return task  # idempotent: a double-click is not an error
    return db.complete(conn, task_id)


@app.post("/api/tasks/{task_id}/restore")
def restore_task(task_id: int, conn=Depends(get_conn)):
    """Undo and the archive's Restore button are the same operation."""
    if db.get_task(conn, task_id) is None:
        missing()
    return db.restore(conn, task_id)


@app.post("/api/tasks/{task_id}/triaged")
def mark_triaged(task_id: int, conn=Depends(get_conn)):
    """Skipping a task in triage still counts as having looked at it."""
    task = db.get_task(conn, task_id)
    if task is None:
        missing()
    return db.mark_triaged(conn, task_id, db.today())


# --- settings ----------------------------------------------------------------


class QuadrantLabelIn(BaseModel):
    name: str = Field(max_length=4000)
    definition: str = Field(default="", max_length=4000)


class MatrixLabelsIn(BaseModel):
    columns: list[str] = Field(min_length=2, max_length=2)
    rows: list[str] = Field(min_length=2, max_length=2)


class LabelsIn(BaseModel):
    quadrants: list[QuadrantLabelIn] = Field(min_length=4, max_length=4)
    matrix: MatrixLabelsIn


class SettingsIn(BaseModel):
    labels: LabelsIn


@app.get("/api/settings")
def read_settings(conn=Depends(get_conn)):
    """The defaults travel with the settings so "Restore defaults" can fill the
    form without saving — the Save button stays the only thing that writes."""
    return {"labels": db.get_labels(conn), "defaults": db.DEFAULT_LABELS}


@app.put("/api/settings")
def write_settings(payload: SettingsIn, conn=Depends(get_conn)):
    labels = guarded(clean_labels, payload.labels)
    return {"labels": db.set_labels(conn, labels), "defaults": db.DEFAULT_LABELS}


# --- static ------------------------------------------------------------------


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")

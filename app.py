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


def clean_title(raw: str) -> str:
    """A title is one line of a notebook.

    Control characters are stripped rather than rejected — a title pasted from
    somewhere else should not be an error, it should just lose the formatting
    that a single ruled line cannot carry anyway. Length is then a hard 1..80,
    which the schema also enforces.
    """
    text = "".join(
        " " if ch in "\t\n\r" else ch
        for ch in (raw or "")
        if ch in "\t\n\r" or unicodedata.category(ch)[0] != "C"
    )
    text = re.sub(r"\s+", " ", text).strip()
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
        "triage": db.triage_queue(conn, day),
        "done_today": db.count_finished_on(conn, day),
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


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, max_length=4000)
    quadrant: int | None = None
    due: str | None = None


@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskIn, conn=Depends(get_conn)):
    title = guarded(clean_title, payload.title)
    return db.create_task(conn, title)


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
    # Any deliberate change counts as having looked at it, so triage does not
    # ask again the same day.
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


# --- static ------------------------------------------------------------------


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")

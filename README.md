# smoltask

> ### ⚠️ This was written by an AI. Don't run it in production.
>
> Every line of this repository — the storage, the API, the page, the tests and
> this README — was written by Claude (Anthropic's Opus 5) over one evening,
> working from a specification. A human designed it, argued with it, and
> reviewed the behaviour; a human did not audit the code.
>
> It has **no authentication of any kind**. Anyone who can reach the page can
> read and edit every task. It has never been load-tested, pen-tested, or run by
> anyone other than its author. It stores everything in one SQLite file with no
> migrations to speak of.
>
> It is a notebook, and it is shared in case the shape of it is useful to
> someone. Treat it as a worked example, not as software you would trust your
> week to.

**Notebook-style task management.** A task takes two seconds to write and one key to be
rid of. That is the whole feature list.

A paper to-do list works right up until the page fills with a mix of done and
not-done, and you have to copy the survivors onto tomorrow's page. smoltask is
that page, except the ticked lines take themselves away, the survivors carry
forward on their own, and every morning it asks you which of them actually
matter today.

## The idea

Two kinds of tool, each half right.

A ticketing system is where work that other people need to see lives. It costs
thirty seconds and four mandatory fields to create one, and fifteen of them make
a board unreadable. It is not a capture tool, and using it as one is how you
stop capturing things.

A notebook captures in two seconds and never asks you for a field. But it can't
carry anything forward, and crossing a line out leaves it on the page.

smoltask is the notebook, with two changes. Ticked lines leave. Untriaged ones
come back tomorrow morning and ask to be ranked.

## What it does

**Write a task.** The capture line holds focus when the page opens. Type, press
Enter, it exists. No dialog, no second step, no field that must be filled before
the thing you just heard in a meeting can be written down. Focus stays put, so
three tasks is three sentences and three Enters.

**Date it as you write it.** End the line with `~` and a date — `call Bob ~fri`,
`renew passport ~+30` — and the task is filed with that date. It takes anything
the `d` box does. The date the line will file under shows at the right margin
before you press Enter, so a `~` word that isn't a date visibly isn't one. Only
the last word counts, and only when it starts with `~`, so a pasted URL, a path
like `~/notes` or "about ~5 mins" stays exactly as typed.

**Titles are capped at 80 characters, on one line.** This is a forcing function,
not a limitation. If it doesn't fit on a ruled line it isn't one thought, and
the place for the detail is wherever the work actually happens.

**Tick it.** The row leaves the page. That is the point — the payoff is an empty
page, not a page of struck-through lines.

**Undo is a stack.** Completion is destructive, so undo carries the weight.
`Ctrl+Z` five times brings back five tasks, which matters on the day your
machine lags and you tick a block of rows you meant to tick one of. Anything
older than the session is in the Archive with a Restore button.

**Rank it, later.** Tasks land unsorted, which is a resting state and not an
error. Ranking is a separate pass, because you triage better thirty seconds
after the meeting than during it. Four sections, Eisenhower underneath:

| Section | | |
|---|---|---|
| **Now** | urgent & important | do it |
| **Next** | important, not urgent | the work that actually matters |
| **Last** | urgent, not important | someone else's urgency |
| **Never** | neither | be honest |
| **Unsorted** | | at the bottom, where it belongs |

Those are the defaults. The names and the line beside each one are yours to
change on the **Settings** tab, as are the edges of the grid triage shows — or
empty all four edges and the grid is just the keys. It's cosmetic: `1` is still
the one that goes stale, `4` still the one a date contradicts, and the order and
colours stay put.

Each ranked section has a colour — warm at the top, cool further down — on its
name and as a thin rule down the margin of its rows. `Never` and `Unsorted` get
none, because colouring them would imply they rank. A red date is the only red
on the page.

Untriaged tasks sort *last*, not first. A task that hasn't been triaged hasn't
earned a position, and an inbox on top would rank the most recently captured
thing as the most important thing — which is the reflex the whole ritual exists
to correct.

**The morning ritual.** On the first load of a day with anything waiting, the
page goes into triage: one task lit at a time, the rest dimmed, `1`–`4` to rank
and move on. `p` runs it again whenever you like. It asks about three things:

- tasks you haven't ranked
- anything **dated and ranked Never** — a date you promised someone and disowned
  in the same breath
- anything **due today or tomorrow, whatever its quadrant** — because ranking by
  quadrant first would otherwise bury a commitment you made to someone else
- anything that's sat in **Now** for a week, which usually means it was never
  really urgent, or you're avoiding it

You can tick a task during triage. Triage is where you notice a task stopped
being a thing. You can also write one: `/` (or a click on the capture line)
takes a new task without leaving triage, and it joins the end of the queue.
Clicking any task makes it the one being triaged.

**Due dates, quietly.** `d` on a task, then `tod`, `tom`, `fri`, `+3`, or a
date — any prefix of the word will do, so `t`, `to` and `today` are all today.
A date turns red when it needs a human and nothing else happens. There are no
reminders, no notifications and no recurrence, and there will not be.

A date needs a human for one of two reasons: it has passed, or the task is
ranked **Never** — which means you promised someone a date and told yourself you
will never do it. The morning ritual asks about that one too, once, and stops if
you tell it you meant it.

## Keys

Focus starts in the capture line, because capture is sacred. Plain letters are
text while you are typing there and shortcuts while the list has focus — `Esc`
in an empty capture line steps down into the list.

| | |
|---|---|
| `Enter` | commit the task, stay in the line |
| `Esc` | clear the line; again to step into the list |
| `j` `k` / `↑` `↓` | move between tasks |
| `space` / `x` | complete |
| `Enter` / `e` | edit in place |
| `1`–`4` | rank · `0` unsorts |
| `d` | due date — `tod`, `tom`, `fri`, `+3`, a date, `-` to clear |
| `p` | run triage |
| `a` / `t` / `s` | Archive / Tasks / Settings |
| `/` | back to the capture line to write another — in triage too |
| `Ctrl+Z` / `u` | undo the last completion, repeatedly |

The keyboard is the good path, not the power-user path. A list that reflows
under a mouse cursor is precisely how the wrong row gets ticked.

## The archive

Everything that left the page, with **which way it left**: `✓` if you ticked it,
`→ PROJ-412` if it became a ticket. You never choose that — it records which
button you pressed, so that "did I ever deal with X?" can answer *"yes, it's
PROJ-412"* rather than just *"yes"*.

Sortable by created or finished, filterable by title and by outcome, and every
row can be restored. There is no delete button: a task made by mistake is ticked
like any other, and a little junk in the archive is cheaper than a second way to
make things disappear.

## Try it

```sh
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8108
```

Then open <http://127.0.0.1:8108>. The database is `smoltask.db` beside the
code; set `SMOLTASK_DB` to put it somewhere else. On a Windows laptop, see
[docs/windows.md](docs/windows.md).

With Docker:

```sh
docker compose up -d --build
```

**Set `TZ`** in a `.env` file to the timezone you live in. Every "today" in the
app is the server's today, and a container without it runs in UTC — the page
will warn you if its date and your browser's disagree.

The compose file publishes on `127.0.0.1` only. To serve smoltask to the rest of
your network, set `SMOLTASK_BIND=0.0.0.0` in `.env` **and** list the name you
will browse to in `SMOLTASK_ALLOWED_HOSTS` — the app refuses any Host header it
was not told about, which is its defence against DNS rebinding. The comments in
`docker-compose.yml` explain both, and why a host firewall does not narrow a
Docker-published port.

## What it will never have

No assignees. No projects. No tags. No attachments. No subtasks. No recurrence.
No reminders or notifications. No multiple lists. No delete button. No cancelled
state, no workflow, no status beyond "on the page" and "off it". No sync. No
mobile app. No authentication. No multi-user.

The list is the product. The full reasoning is in [DESIGN.md](DESIGN.md), which
is worth reading before proposing a feature — most of them are in there already,
under a heading explaining why they aren't here.

One thing is designed but not built: turning a task into a Jira ticket, one-way
and one-shot, after which it moves to the archive with the key attached. Section
7 of the design has the shape.

## Testing

```sh
python3 run_tests.py     # or: pytest -q
```

Security tests are not optional and live in `tests/test_security.py`. See
[SECURITY.md](SECURITY.md) and [SECURITY_STATUS.md](SECURITY_STATUS.md).

## Licence

Public domain, via the [Unlicense](LICENSE).

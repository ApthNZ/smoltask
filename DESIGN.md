# smoltask — design

> **smoltask — a notebook that ticks.**
> A task takes two seconds to write and one key to be rid of. That is the whole
> feature list.

A paper to-do list works right up until the page fills with a mix of done and
not-done and you have to copy the survivors onto tomorrow's page. smoltask is
that page, except the ticked lines take themselves away, the survivors carry
forward on their own, and every morning it asks you which of them actually
matter today.

**The test every feature has to pass:** capture a task in under two seconds,
tick it when it's done, and never lose one to a mis-click. Anything that does
not serve that sentence does not go in.

---

## 1. The problem being solved

Two tools, each half-right:

- **Jira** is where work that other people need to see lives. It costs thirty
  seconds and four mandatory fields to create a ticket, and fifteen tickets make
  a board unreadable. Not a capture tool.
- **Outlook tasks** capture in two seconds, which is the one thing it gets
  right. But completion is *destructive and invisible*: a completed task is
  gone, functionally unfindable, and a laggy machine plus a block of clicks is
  an unrecoverable event.

The gap is the notebook. Someone says "could you email bob", you write
`Email bob`, and later you tick it. smoltask is that, with the carry-forward
automated and the mis-click recoverable.

## 2. Non-goals

Stated up front because this list is the product:

No assignees. No projects. No tags or labels. No attachments. No subtasks. No
recurrence. No reminders or notifications. No multiple lists. No delete button.
No cancelled state, no workflow, no status beyond "on the page" and "off it".
No sync. No mobile app. No auth. No multi-user. No email integration — it was
considered and binned.

## 3. Screens

Two. `Tasks` and `Archive`, in a nav bar borrowed from smolplan.

### 3.1 Tasks — the page

Single centred column, max-width ~720px. Notebook density: `--row: 30px` per
task, one line each, a `--line-soft` rule between them like ruled paper. No
cards, no padding, no chrome.

**The capture row** sits at the top of the list and holds focus on page load.
An empty tick box, then a bare text input. Type, `Enter`, the task commits, the
input clears, focus stays put. Nothing else happens — no prompt, no modal, no
second step. The task lands **unsorted**, which is a legitimate resting state.

Input is hard-capped at **80 characters**, single line, no wrapping possible. A
counter appears at 65 and turns `--red` at 80. If it doesn't fit on a notebook
line it isn't one thought.

**A task row:**

```
•  Email bob about the capacity numbers              PROJ-412   Fri   [ ]
```

A bullet in the margin, the title, then blank paper, then the Jira key and due
date, then the tick box **at the right margin** — where a pen would reach it.
The date goes `--red` when it needs a human and nothing else moves: no banner,
no count, no nagging.

**Red on a date means the date is a problem**, and there are two ways for that
to be true:

- it has **passed**, or
- the task is ranked **Never**. A date on a Never task is a date you promised
  someone and disowned in the same breath, and that is worth being told. The
  tooltip says which of the two it is, or both.

That is the whole of red on this page. Nothing else claims it, and a test
enforces that. Quadrant is shown by which section the row is in, not by a badge, so
the row itself stays clean.

**Three targets, three meanings.** Clicking the words edits them; clicking the
bullet or the blank paper after the title selects the row without opening its
text; clicking the tick completes it. This is why the title is sized to its own
words rather than filling the row — a full-width title would leave nowhere to
click that *isn't* the editor. The bullet is muted until you hover and takes the
accent colour when the row is the one the keyboard is pointing at.

**Sections**, in this order:

| Section | Eisenhower | Header reads | Hue |
|---|---|---|---|
| Now | do — urgent + important | `Now — urgent & important` | 30, warm |
| Next | schedule — important, not urgent | `Next — important, not urgent` | 210, blue |
| Last | delegate — urgent, not important | `Last — urgent, not important` | 265, violet |
| Never | delete — neither | `Never — neither` | none |
| Unsorted | — | `Unsorted` | none |

**A little colour, on the two things that carry meaning**: the section name, and
a thin rule down the left margin of the rows inside it. Warm at the top, cool
further down, and nothing at all for the two sections that are not a priority —
`Never` and `Unsorted` stay grey, because colouring them would say they rank.

The hues are smolplan's, and are the ones it picked to stay clear of the green
and red it uses for status. That matters here: **a red date is the only red on
the page**, and it stays that way.

The axis is printed in muted text beside the name, and the ranking key in front
of it — `1 Now — urgent & important` — so the mapping is learnable without a
legend.

**The names and definitions are the user's, not the code's.** They are what the
table above ships with. A Settings tab edits the four names, the line beside
each, and the four edges of the triage grid; they are stored in a `setting`
row and read with a fallback to the defaults, so a damaged row costs a label,
never the page. What stays fixed is everything behaviour hangs off: the key,
the order, the hue, `1` going stale and `4` being the one a date contradicts.
Renaming is cosmetic by construction, which is why it needs no code change. The names are ordinal rather than instructional, because with no
assignees "delegate" is meaningless and "delete" is a lie — nothing is ever
deleted, it just never rises to the top.

`Unsorted` carries no number. `0` is what unsorts a task, and numbering the
section `5` would put it on the scale the other four are on.

**Unsorted sits at the bottom.** A task that has not been triaged has not earned
a position, and putting the inbox on top would rank the most recently captured
thing as the most important thing — which is exactly the reflex the ritual
exists to correct. New tasks wait at the bottom until triage places them.

Within a section: due date ascending, undated last, then created ascending —
oldest first, the order a notebook would have them in.

**No counters.** There is no "4 on the page" or "1 archived" in the header. Both
restated something already on screen and in view, and the space is better spent
on notifications.

**Empty state.** When the page is clear it says so in one line, with the day's
count as the reward:

```
Nothing on the page. 7 ticked today.
```

### 3.2 Completion and undo

Ticking removes the row. That is the inbox-zero payoff and it is deliberate —
but it means undo carries the weight that strike-through would have carried, so
undo has to be good:

- An undo bar appears at the bottom: `Email bob — done.  Undo (Ctrl+Z)`.
- `Ctrl+Z` is a **stack**, not one step. The laggy-machine-completed-five-rows
  case means pressing it five times. That case is the reason this app exists; it
  is not allowed to be the case undo can't handle.
- Anything older than the session is recovered from the Archive instead.

Note that keyboard completion (`space` on the focused row, focus then moves down
one) has no mis-click failure mode at all — the list reflowing under a mouse
cursor is precisely the Outlook trap. The keyboard is the good path; the mouse
is the fallback.

### 3.3 Archive — what left the page

A table: outcome, task, created, finished. Click a header to sort by created or
finished, either direction.

**Outcome** is the marker, and it has two values because there are two ways off
the page:

| Marker | Means |
|---|---|
| `✓` | You ticked it. |
| `→ PROJ-412` | It became a Jira ticket. Links to it. |

This is not a second kind of completion and you never choose it — it's a record
of which button you pressed. It exists so that "did I ever deal with X?" can
answer *"yes, it's PROJ-412"* rather than just *"yes"*. Filter buttons: All /
Done / Promoted.

A filter-as-you-type box sits above the table. It's the recovery path for
anything past the undo stack, and it is the only search in the product.

**Restore** on each row puts the task back on the page with its quadrant and due
date intact. Same operation as undo, same endpoint.

### 3.4 The morning ritual — a mode, not a page

Paper makes you rewrite yesterday's survivors every morning. The drudgery is
annoying; the triage it forces is the valuable part. smoltask does the copying
and charges you the triage.

**Fires** on the first load of a calendar day when the queue is non-empty, and
any time you press `p`. Re-runnable on demand, always skippable, never blocks
capture — typing in the capture row just works and triage picks up after.

"Picks up after" is literal. The queue is a snapshot (a refreshed queue steps
over every second task), so a task written mid-triage is appended to it — without
that it could be neither walked to nor clicked, and the lowest the arrows reached
was the last task that existed when triage began. `/` goes to the capture line
without leaving triage; `Esc` or `↓` from there goes back to the lit task.

**A click picks.** Clicking a row in triage makes it the lit task: one already
in the queue is jumped to, as the arrows would; one that is not is slotted in at
the current place, so the task you were on comes straight after it. Ticking a
row that is not the lit one takes it out of the queue and leaves the pointer
where it was — it used to advance, stepping off the lit task unseen.

**It is a mode on the Tasks page, not a modal.** The list stays visible and
slightly dimmed; one task is highlighted at a time. A thin bar at the top:

```
Triage — 4 to sort, 2 due soon, 1 stale                        Esc to leave
```

**The queue**, in order:

1. **Unsorted** tasks, oldest first — they are sitting at the bottom of the
   page until triage places them, so this is what empties the queue.
2. **Dated, but ranked `Never`.** A date promised to someone and disowned in
   the same breath. It outranks the next one deliberately: for a dated `Never`
   task due tomorrow, "you said you would not do this" is the part you did not
   already know.
3. **Due today or tomorrow, whatever the quadrant.** This is the pressure valve:
   sorting by quadrant then date means a `Last` task due tomorrow sorts below
   every `Now` task, and "I'll have that back to you tomorrow" is exactly the
   commitment you don't want buried. The ritual surfaces it regardless.
4. **Stale `Now`** — anything sitting in the urgent-and-important section for
   more than seven days. That's the Eisenhower drift: it was never really
   urgent, or you're avoiding it. Either way it needs re-ranking or ticking.

A task can qualify under more than one. It appears once, under the first that
applies.

**Creating a contradiction does not silence it.** Every other deliberate change
counts as having looked at a task, which is what stops the ritual asking twice
in a day. Ranking a dated task `Never` is the exception: that is the moment the
problem appears, not the moment it is resolved, so the looked-at stamp is
*cleared* rather than set and triage asks — once. Skipping it there silences it
for the day like anything else, and it comes back tomorrow, because the
contradiction is still there. Clearing the date or moving it out of `Never` is a
real answer and ends it.

**The bar carries no key hints.** The legend at the foot of the page already
shows the triage keys; repeating them made the bar wrap.

**Under the bar, the matrix.** A 2×2 of the four keys, shown in triage and
nowhere else:

```
                 urgent        not urgent
  important      1 Now         2 Next
  not important  3 Last        4 Never
```

Read across then down, `1`–`4` land on the Eisenhower quadrants in their classic
order. That is the whole argument for the shape: a row of four would be a
legend, restating what the section headers already say, while the grid shows
*why* the numbering is what it is. It earns its place because the headers can't
do this job during triage — an unused section is not rendered at all, so the
quadrant you never reach for is the one with nothing on screen to learn from.

The axes are on the edges, not in the cells. Repeating "urgent & important"
inside the top-left cell says the same thing twice, and the height is not free:
the highlighted task has to stay above the fold. The cells reuse the foot
legend's key styling, so a digit here looks like the key it is. `Never` is
uncoloured, as its section is — colouring it would say it ranks.

**Keys in triage:** `1`–`4` assign and advance, `d` set a due date, `space`
complete it, `n` skip, `/` write a new task, `Esc` leave. They are on the legend at the foot, as
everywhere else. Completing during triage matters — triage is
where you notice a task stopped being a thing.

`↑` `↓` and `k` `j` walk the queue. They are *navigation*: they mark nothing
and call nothing, so a task you passed over can be gone back to. `n` is the one
that skips and records having looked.

When the queue empties the bar reads `Page is triaged.` and the mode exits.

## 4. Keymap

Focus starts in the capture row, because capture is sacred.

**Capture row**

| Key | Does |
|---|---|
| `Enter` | Commit, clear, stay. A last word of `~fri` (anything `d` takes) files it with that date |
| `↓` | Move focus into the list |
| `Esc` | Clear the input; if already empty, move into the list |

**List, with a row focused**

| Key | Does |
|---|---|
| `j` `k` / `↑` `↓` | Move focus |
| `space` / `x` | Complete |
| `Enter` / `e` | Edit inline (`Enter` saves, `Esc` cancels) |
| `1`–`4` | Set quadrant |
| `0` | Back to Unsorted |
| `d` | Due date, then `tod` / `tom` / `fri` / `+3` / a typed date / `-` to clear |
| `J` | Promote to Jira |
| `u` | Undo the last completion (stack) |
| `p` | Enter or leave triage |
| `a` / `t` / `s` | Archive / Tasks / Settings |
| `/` | Back to the capture row to write another |

**Anywhere**

| Key | Does |
|---|---|
| `Ctrl+Z` | Undo the last completion (stack) |

Only `Ctrl+Z` is global, and in the capture row it is the browser's text undo
while the input has content, task undo when it's empty.

**The legend is on screen at all times** — a strip along the foot of the page,
not a help modal you have to know to open. It changes with context: the capture
keys while the capture line has focus, the list keys while the list does, the
triage keys in triage, the archive's in the archive. A legend that listed every
key regardless of context would be lying half the time, given the next
paragraph.

**Every other shortcut is a plain letter, so it only acts while focus is in the
list.** This is not a compromise, it is the point: capture is sacred, and a
bare `a` that navigated to the Archive would eat the first keystroke of "audit
the logs". `Esc` in an empty capture row steps down into the list, which is the
documented way out — so reaching the archive from a standing start is `Esc`,
`a`. The nav buttons are always clickable.

## 5. Data model

One SQLite file, no migrations to speak of, same as smolplan.

```sql
CREATE TABLE task (
  id          INTEGER PRIMARY KEY,
  title       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
  quadrant    INTEGER CHECK (quadrant IN (1,2,3,4)),   -- NULL = unsorted
  due         TEXT,                                     -- 'YYYY-MM-DD', NULL = none
  created_at  TEXT NOT NULL,                            -- ISO8601 UTC
  finished_at TEXT,                                     -- NULL = on the page
  outcome     TEXT CHECK (outcome IN ('done','promoted')),
  jira_key    TEXT,                                     -- set iff promoted
  triaged_on  TEXT,                                     -- last date triage touched it
  CHECK ((finished_at IS NULL) = (outcome IS NULL)),
  CHECK ((outcome = 'promoted') = (jira_key IS NOT NULL))
);
```

Notes on why it's this shape:

- **"On the page" is `finished_at IS NULL`.** The Archive is the complement.
  There is no status column and no state machine.
- **Rows are never deleted.** A task made by accident gets ticked like anything
  else. The archive accumulating a little junk is the accepted cost of not
  having a delete button.
- **`quadrant` is an integer** so it sorts without a lookup, and `NULL` is a
  real value meaning unsorted rather than a fifth quadrant.
- **`triaged_on`** is what stops the ritual re-asking about something you looked
  at this morning, and it gives "stale" a definition. It also removes the need
  for any app-state table: the ritual fires when the queue is non-empty and
  nothing was triaged today.
- **No undo table.** Undo is `restore`, which clears `finished_at`, `outcome`
  and `jira_key`. The stack of recently-completed ids lives in the page for the
  session; the Archive covers anything older.

## 6. API

```
GET    /api/tasks                    on the page, sorted for display
GET    /api/archive?sort=&dir=&q=&outcome=
POST   /api/tasks                    {title, due?}
GET    /api/settings                 {labels, defaults}
PUT    /api/settings                 {labels}  — names, definitions, grid axes
PATCH  /api/tasks/:id                {title?, quadrant?, due?}
POST   /api/tasks/:id/complete
POST   /api/tasks/:id/restore        serves both undo and archive restore
POST   /api/tasks/:id/promote        Jira; later
GET    /health                       opens the database, like smolplan's
```

## 7. Jira promote

One-way, one-shot, no sync. The task becomes a ticket, keeps the key, and
**moves to the Archive** marked `→ PROJ-412`. If it's in Jira it doesn't need to
be in two places.

Constraints to design around, settled later but not forgotten:

- On-prem Jira is **Data Center**, so REST **v2**, not the v3 in most docs.
  Auth by PAT (8.14+).
- **Mandatory fields will reject the create.** Project, issue type and any
  required field values come from config; there is no field editor and there
  never will be. If a project needs six mandatory fields, it isn't a promote
  target.
- On rejection: show what Jira said, leave the task exactly where it was.
- The 80-character title becomes the summary. There is no description, because
  there is nowhere in smoltask to have written one. That's the point.

## 8. Repo, history and secrets

**Model B: one history, two remotes.**

- `smoltask-private` is where work goes day to day.
- `smoltask` is a true **fast-forward mirror** — `public/main` is always an
  ancestor of `main`, so publishing is `git push public main`, forever.

This only holds if nothing that can't be public ever enters the history. A
private repo that later mirrors to a public one is a **delay, not a filter**: it
changes when a commit becomes visible, not whether it does. The one advantage
over a single public repo is the rewrite window — something committed but not
yet pushed publicly can still be rebased out of existence.

Its sibling project learned this the expensive way. One day-one commit put a
deployment host, a private subnet and a port into the history. The files were
scrubbed a few commits later; the commits were immortal, and publishing stayed a
hand-built squash for as long as that history lived.

Therefore, before any app code exists:

- `.gitignore`, `.gitleaks.toml` and the publish-guard pre-push hook at
  `git init`, not after the first scare.
- Create the public repo and push to it **immediately**, while it's three files.
  A mirror that exists from commit one keeps the fast-forward property real.
- Every deployment specific behind an env var with a sane default —
  `SMOLTASK_PORT`, `SMOLTASK_DB` — with the real values in a gitignored `.env`.
  A compose file that reads `${SMOLTASK_PORT:-8108}` is the template.
- The deployment host's name, port and firewall situation live wherever that
  machine is documented — never here. The app repo does not know where it runs.
- Machine-specific context for Claude goes in a gitignored `CLAUDE_LOCAL.md`.

**New stakes:** smoltask talks to Jira, so a corporate hostname, a project key
and a **PAT** are in play — the sibling project had no outbound network and
genuinely held no secrets. All three live in `.env`, never in a config file,
never in a test fixture, never in a commit message explaining the setup. Add a
gitleaks rule for Jira PATs.

## 8b. Living with a tab left open

This page gets left open — that is what a notebook is for. Two consequences it
has to handle rather than ignore:

- **The day changes under it.** A tab opened yesterday would keep calling
  yesterday "today": a date one day out reading as due today, and a morning
  ritual that never fires because as far as the page is concerned the morning
  never came. The page checks once a minute and reloads when the local date has
  moved. It never does so while a task is being edited, a date is being typed,
  or there are words in the capture line — a reload would take them with it.
- **A date in another year must say so.** `18 Sep` twelve months out reads
  exactly like `18 Sep` next month. The year is shown when it is not this one.

## 9. Stack and deployment

Deliberately identical to its sibling project, so the setup guide carries over:

- Python + FastAPI on uvicorn, SQLite, no-build-step vanilla JS.
- The sibling project's `static/app.css` tokens verbatim — `--bg`, `--line-soft`, `--row:
  30px`, tabular numerals, light and dark. Red means "a human needs to look at
  this", which here means overdue and nothing else.
- Docker Compose on a development box; plain `uvicorn app:app` on the Windows
  laptop that actually uses it, which is the machine that matters — it's the
  only one that can reach Jira.
- Bound to `127.0.0.1` wherever it holds real work. This is your day laid out in
  one list, which is more than it sounds like.
- No authentication, and the README says so in a warning block up top.

## 10. Build order

Each step ends somewhere usable, and the gate exists before the code does.

| # | Step | Ends with |
|---|---|---|
| 1 | Scaffolding: `.gitignore`, gitleaks, publish-guard, LICENSE, SECURITY.md, README stub, `.env.example`. Push to both remotes. | An empty, publish-safe repo with a live mirror. |
| 2 | CI: `ci.yml`, `secret-scan.yml`, Dependabot + auto-merge, copied from smolplan. | The test gate exists before there are tests to run. |
| 3 | Data layer and API, with the CHECK constraints and a test suite. | `POST /api/tasks` works. |
| 4 | Tasks page: capture, list, tick, undo stack. No priority, no dates. | **Usable.** Already beats Outlook tasks. |
| 5 | Archive: outcome marker, sort, filter, search, restore. | Nothing can be lost. |
| 6 | Quadrants: sections, `1`–`4`, sort order. | The page is ranked. |
| 7 | The morning ritual. | Carry-forward is automated. |
| 8 | Due dates. | Commitments have a date. |
| 9 | Jira promote. | Tasks that grew up can leave. |

Stopping after step 5 would still be a product worth having. That's the test of
whether the order is right.

## 11. Open

- Empty-state copy, and whether the day's tick count is a nice reward or a
  gimmick that gets old by Thursday.
- Whether the unselected bullets are too faint to read as "click me". They are
  `--line` until hover on purpose, so the page stays quiet, but the affordance
  is only discoverable by trying it.

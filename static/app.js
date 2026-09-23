// smoltask front end. No build step, no framework, no dependencies.
//
// Three views, one page each. The tasks view is a notebook: a capture line, then
// ruled rows grouped by quadrant. Everything is reachable from the keyboard,
// because the mouse is what made the tool this replaces dangerous — a list that
// reflows under the cursor is how you complete the wrong row.

// Hues are smolplan's, chosen there to stay clear of the green and red used for
// status — so overdue stays the only red on the page. Warm at the top, cool
// further down, nothing at all for the two sections that are not a priority.
//
// The key and the hue are fixed, because behaviour hangs off the number: 1 goes
// stale, 4 is the one a date contradicts. What each is *called*, and what it
// means, is the user's — it comes from the server as `labels`, edited on the
// Settings tab. See `quadrants()`.
const QUADRANTS = [
  { n: 1, hue: 30 },
  { n: 2, hue: 210 },
  { n: 3, hue: 265 },
  { n: 4, hue: null },
];
const UNSORTED = { n: null, name: "Unsorted", definition: "not yet triaged", hue: null };
const NEVER = 4;
const STALE = 1;
const SECTIONS = [...QUADRANTS, UNSORTED];
const MAX_TITLE = 80;
// Must agree with db.MAX_NAME, MAX_DEFINITION and MAX_AXIS.
const MAX_NAME = 20;
const MAX_DEFINITION = 60;
const MAX_AXIS = 20;
// Room in the capture line for a date on the end of the title — " ~2026-09-30"
// — so a full 80-character title can still take one. The title is held to 80
// on its own; see onCaptureKey.
const DATE_ROOM = 12;
const COUNTER_FROM = 65;
const UNDO_VISIBLE_MS = 12000;
const DAY_CHECK_MS = 60000;

const WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// The legend at the foot of the page. Keyed by where you are, because a bare
// letter is text while the capture line has focus and a shortcut while the list
// does, and a legend that does not say so is worse than none.
const KEYMAPS = {
  capture: [["Enter", "add the task"], ["Esc", "step into the list"],
            ["Ctrl+Z", "undo a completion"]],
  list: [["j k ↑ ↓", "move"], ["space", "done"], ["1-4", "rank"], ["0", "unsort"],
         ["d", "due date"], ["e", "edit"], ["p", "triage"], ["a", "archive"],
         ["s", "settings"], ["/", "new task"], ["Ctrl+Z", "undo"]],
  triage: [["j k ↑ ↓", "move"], ["1-4", "rank"], ["d", "due date"],
           ["space", "done"], ["n", "skip"], ["/", "new task"], ["Esc", "leave triage"]],
  // Writing a task mid-triage. Letters are text here, like any capture line,
  // and the way back is to the lit task rather than into the list.
  triageCapture: [["Enter", "add it to the end of triage"], ["Esc", "back to triage"]],
  archive: [["t", "back to tasks"], ["click a heading", "sort"],
            ["Restore", "put it back on the page"]],
  settings: [["Tab", "next field"], ["Enter", "save"], ["Esc t", "back to tasks"]],
};

const state = {
  view: "tasks",
  today: "",
  tasks: [],
  triage: { queue: [], counts: {}, auto: false },
  doneToday: 0,
  focus: null,
  editing: null,
  dueFor: null,
  triaging: false,
  capturing: true,
  queue: [],
  qi: 0,
  undo: [],
  barUntil: 0,
  archive: { rows: [], sort: "finished", dir: "desc", q: "", outcome: "" },
  labels: null,
  // `draft` outlives a trip to another tab, so half-finished edits are still
  // there on the way back. Only Save writes; nothing is saved by leaving.
  settings: { draft: null, defaults: null },
};

// The four quadrants with the user's names on them.
function quadrants() {
  return QUADRANTS.map((q, i) => ({ ...q, ...state.labels.quadrants[i] }));
}

const nameOf = (n) => state.labels.quadrants[n - 1].name;

// --- tiny DOM helpers --------------------------------------------------------

function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "value") node.value = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  setChildren(node, ...kids);
  return node;
}

// Conditional children are written as `test ? el(...) : null`, and
// replaceChildren stringifies a null into the literal text "null" on the page.
// Everything goes through here instead; tests/test_frontend.py fails if a
// direct replaceChildren call reappears.
function setChildren(node, ...kids) {
  node.replaceChildren(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
}

const $ = (id) => document.getElementById(id);

// --- api ---------------------------------------------------------------------

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : response.statusText);
  }
  return response.json();
}

function toast(message, tone = "warn") {
  const node = $("toast");
  node.textContent = message;
  node.className = tone;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 3500);
}

// --- dates -------------------------------------------------------------------

const dayNumber = (iso) => Math.floor(Date.parse(`${iso}T00:00:00`) / 86400000);

function localDate(when = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`;
}

function formatDue(due, today) {
  const delta = dayNumber(due) - dayNumber(today);
  if (delta === 0) return "today";
  if (delta === 1) return "tomorrow";
  const date = new Date(`${due}T00:00:00`);
  if (delta > 1 && delta < 7) return WEEKDAYS[date.getDay()].replace(/^./, (c) => c.toUpperCase());
  // The year only when it is not this one — otherwise a date twelve months out
  // reads exactly like one next month.
  const year = date.getFullYear() === Number(today.slice(0, 4)) ? "" : ` ${date.getFullYear()}`;
  return `${date.getDate()} ${MONTHS[date.getMonth()]}${year}`;
}

function shiftDays(iso, days) {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  return localDate(date);
}

// `d` then: t, tom, a weekday, +N, an ISO date, or - to clear. Returns
// undefined when it cannot tell, which leaves the box open rather than
// guessing at a date the user did not mean.
function parseDue(input, today) {
  const text = (input || "").trim().toLowerCase();
  if (text === "" || text === "-") return null;
  // Any prefix of the word, rather than one blessed abbreviation — "tod" is as
  // natural a thing to type as "t". Today is tested first, so the shared prefix
  // "t"/"to" resolves to today rather than being ambiguous.
  if ("today".startsWith(text)) return today;
  if ("tomorrow".startsWith(text)) return shiftDays(today, 1);
  if (/^\+\d+$/.test(text)) return shiftDays(today, parseInt(text.slice(1), 10));
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const weekday = WEEKDAYS.findIndex((d) => d.startsWith(text.slice(0, 3)));
  if (weekday >= 0) {
    const current = new Date(`${today}T00:00:00`).getDay();
    return shiftDays(today, ((weekday - current + 7) % 7) || 7);
  }
  return undefined;
}

// `call Bob ~fri` files the task with a date in one go: the last word, when it
// starts with `~` and is something the `d` box would take. Anything else stays
// text. That rule is what keeps a pasted URL safe — `/` would have split every
// one of them — and a path like ~/notes, or "about ~5 mins", reads as no date,
// because neither is a `~` word the date box understands. `~~fri` works too, as
// a courtesy to the obvious guess.
const INLINE_DUE = /\s~+(\S+)$/;

function splitDue(line, today) {
  const text = (line || "").trim();
  const match = INLINE_DUE.exec(text);
  const due = match ? parseDue(match[1], today) : undefined;
  // parseDue answers null for "clear the date", which is not a date to file.
  if (typeof due !== "string") return { title: text, due: null };
  return { title: text.slice(0, match.index).trim(), due };
}

// --- loading -----------------------------------------------------------------

// A server in the wrong timezone gets every "today" question wrong — the tick
// count, due today, the morning ritual — and does it silently. The browser
// knows what day it is here, so say so once rather than being quietly wrong.
function warnIfTheServerIsOnADifferentDay(serverToday) {
  if (warnIfTheServerIsOnADifferentDay.warned) return;
  const local = localDate();
  if (serverToday && serverToday !== local) {
    warnIfTheServerIsOnADifferentDay.warned = true;
    toast(`This server thinks today is ${serverToday}; your machine says ${local}. Set TZ.`);
  }
}

async function loadTasks({ autoTriage = false } = {}) {
  const data = await api("/api/tasks");
  warnIfTheServerIsOnADifferentDay(data.today);
  state.today = data.today;
  state.tasks = data.tasks;
  state.triage = data.triage;
  state.doneToday = data.done_today;
  state.labels = data.labels;
  if (state.focus !== null && !state.tasks.some((t) => t.id === state.focus)) state.focus = null;
  if (autoTriage && data.triage.auto && data.triage.queue.length) startTriage();
  render();
}

async function loadArchive() {
  const { sort, dir, q, outcome } = state.archive;
  const params = new URLSearchParams({ sort, dir, q, outcome });
  const data = await api(`/api/archive?${params}`);
  state.archive.rows = data.tasks;
  render();
}

// --- rendering ---------------------------------------------------------------

function render() {
  for (const button of $("tabs").children) button.classList.toggle("on", button.dataset.view === state.view);
  if (state.view === "tasks") renderTasks();
  else if (state.view === "settings") renderSettings();
  else renderArchive();
  renderUndo();
  renderKeys();
}

function whichKeymap() {
  if (state.view === "archive") return "archive";
  if (state.view === "settings") return "settings";
  if (state.triaging) return state.capturing ? "triageCapture" : "triage";
  return state.capturing ? "capture" : "list";
}

function renderKeys() {
  setChildren($("keys"), ...KEYMAPS[whichKeymap()].map(([key, what]) =>
    el("span", { class: "chord" }, el("kbd", {}, key), el("i", {}, what))));
}

function renderTasks() {
  const blocks = [];
  if (state.triaging) blocks.push(triageBar(), quadrantGrid());
  blocks.push(captureRow());

  if (!state.tasks.length) {
    blocks.push(el("div", { class: "empty" },
      state.doneToday
        ? `Nothing on the page. ${state.doneToday} ticked today.`
        : "Nothing on the page."));
  } else {
    for (const section of [...quadrants(), UNSORTED]) {
      const rows = state.tasks.filter((t) => t.quadrant === section.n);
      if (!rows.length) continue;
      const hue = section.hue === null ? null : `--h: ${section.hue}`;
      blocks.push(el("div", { class: `section ${hue ? "hued" : ""}`, style: hue },
        // The key that puts a task here. The legend says `1-4 rank` without
        // saying which is which, and an unused section is not rendered at all,
        // so this is the only place the mapping is on the page all day.
        section.n ? el("span", { class: "rank" }, section.n) : null,
        el("span", { class: "name" }, section.name),
        section.definition ? el("span", { class: "axis" }, `— ${section.definition}`) : null));
      for (const task of rows) blocks.push(taskRow(task, section.hue));
    }
  }
  setChildren($("view"), ...blocks);

  if (state.editing !== null) focusInput(`[data-edit="${state.editing}"]`);
  else if (state.dueFor !== null) focusInput(`[data-due="${state.dueFor}"]`);
  else if (!state.triaging && state.focus === null) focusInput("#capture");
}

function focusInput(selector) {
  const node = document.querySelector(selector);
  if (node) { node.focus(); node.select?.(); }
}

function captureRow() {
  const input = el("input", {
    id: "capture",
    maxlength: MAX_TITLE + DATE_ROOM,
    placeholder: "Write a task, press Enter · end with ~fri to date it",
    autocomplete: "off",
    oninput: updateCounter,
    onkeydown: onCaptureKey,
    onfocus: () => { state.capturing = true; renderKeys(); },
    onblur: () => { state.capturing = false; renderKeys(); },
  });
  return el("div", { class: "capture" },
    el("span", { class: "bullet ghost" }, "•"),
    input,
    el("span", { class: "gap" }),
    el("span", { id: "counter", class: "counter" }),
    el("span", { id: "capdue", class: "due" }),
    el("div", { class: "box" }));
}

// The counter counts the title, not the line: a `~fri` on the end is not part
// of the eighty. The date it will file under is shown where the row will show
// it, so what Enter is about to do is on screen before it happens — and a `~`
// word that is *not* a date visibly isn't one.
function updateCounter() {
  const input = $("capture");
  const counter = $("counter");
  const capdue = $("capdue");
  if (!input || !counter || !capdue) return;
  const { title, due } = splitDue(input.value, state.today);
  const used = title.length;
  counter.textContent = used >= COUNTER_FROM ? `${used}/${MAX_TITLE}` : "";
  counter.classList.toggle("full", used >= MAX_TITLE);
  capdue.textContent = due ? formatDue(due, state.today) : "";
  capdue.title = due ? `Due ${due}` : "";
}

function taskRow(task, hue = null) {
  const focused = state.focus === task.id;
  const current = state.triaging && queueTask();
  const isCurrent = current && current.id === task.id;
  const classes = ["row"];
  if (hue !== null) classes.push("hued");
  if (isCurrent) classes.push("lit");
  else if (state.triaging) classes.push("dim");
  else if (focused) classes.push("on");

  // Clicking anywhere that is not the title or the tick selects the row, so
  // there is a way to pick a task up without putting the cursor in its text.
  return el("div", {
      class: classes.join(" "),
      style: hue === null ? null : `--h: ${hue}`,
      "data-id": task.id,
      onclick: () => select(task.id),
    },
    el("button", {
      class: "bullet",
      title: "Select",
      "aria-label": `Select ${task.title}`,
      onclick: (e) => { e.stopPropagation(); select(task.id); },
    }, "•"),
    state.editing === task.id
      ? el("input", {
          class: "title-edit",
          "data-edit": task.id,
          value: task.title,
          maxlength: MAX_TITLE,
          autocomplete: "off",
          onkeydown: (e) => onEditKey(e, task),
          onblur: () => { state.editing = null; render(); },
        })
      : el("span", {
          class: "title",
          title: "Click to edit",
          onclick: (e) => {
            e.stopPropagation();
            state.focus = task.id;
            state.editing = task.id;
            render();
          },
        }, task.title),
    // Blank paper. Clicking it selects the row; the row's own handler does it.
    el("span", { class: "gap" }),
    task.jira_key ? el("span", { class: "key" }, task.jira_key) : null,
    state.dueFor === task.id
      ? el("input", {
          class: "duebox",
          "data-due": task.id,
          placeholder: "tod · +3 · fri · 2026-09-30 · empty clears",
          autocomplete: "off",
          onkeydown: (e) => onDueKey(e, task),
          onblur: () => { state.dueFor = null; render(); },
        })
      : dueLabel(task),
    el("button", {
      class: "tick",
      title: "Complete (space)",
      "aria-label": `Complete ${task.title}`,
      onclick: (e) => { e.stopPropagation(); completeTask(task.id); },
    }, "✓"));
}

function select(id) {
  if (state.triaging) { pickForTriage(id); return; }
  if (state.focus === id && state.editing === null) return;
  state.focus = id;
  state.editing = null;
  render();
}

function dueLabel(task) {
  if (!task.due) return el("span", { class: "due" }, "");
  const overdue = dayNumber(task.due) < dayNumber(state.today);
  // A date on a task ranked Never is a date you have promised someone and told
  // yourself you will not keep. Same red as overdue, because it is the same
  // message: this date needs a human. Nothing else moves.
  const disowned = task.quadrant === NEVER;
  const why = [overdue ? "overdue" : null,
               disowned ? `ranked ${nameOf(NEVER)}` : null].filter(Boolean);
  return el("span", {
    class: `due ${overdue || disowned ? "over" : ""}`,
    title: why.length ? `Due ${task.due} — ${why.join(", and ")}` : `Due ${task.due}`,
  }, formatDue(task.due, state.today));
}

function triageBar() {
  const task = queueTask();
  const left = state.queue.slice(state.qi);
  const remaining = (reason) => left.filter((t) => t.reason === reason).length;
  const parts = [];
  if (remaining("unsorted")) parts.push(`${remaining("unsorted")} to sort`);
  if (remaining("disowned")) parts.push(`${remaining("disowned")} dated ${nameOf(NEVER)}`);
  if (remaining("due")) parts.push(`${remaining("due")} due soon`);
  if (remaining("stale")) parts.push(`${remaining("stale")} stale`);

  const why = {
    unsorted: "not triaged yet",
    disowned: `dated, but ranked ${nameOf(NEVER)}`,
    due: "due today or tomorrow",
    stale: `in ${nameOf(STALE)} for over a week`,
    picked: "picked by hand",
  }[task && task.reason] || "";

  // No key hints here: the legend at the foot of the page already shows the
  // triage keys, and repeating them made the bar wrap onto two lines.
  return el("div", { class: "triage" },
    el("b", {}, task ? "Triage" : "Page is triaged."),
    // A queue holding only hand-picked tasks has no reasons to count.
    task ? el("span", {}, `${state.qi + 1} of ${state.queue.length}${
      parts.length ? ` — ${parts.join(", ")}` : ""}`) : null,
    task ? el("span", { class: "why" }, `· ${why}`) : null);
}

// The digits are the matrix. Read across then down, 1-4 land on the classic
// Eisenhower quadrants in order, so the 2x2 says *why* the numbering is what it
// is rather than just listing it again. Only in triage, which is the one place
// the digits are under your fingers in a run.
//
// The axes sit on the edges rather than in the cells: repeating "urgent &
// important" inside the top-left cell says the same thing twice, and the height
// is not free — the highlighted task has to stay above the fold.
//
// Names and axes are the user's, from Settings. Someone who has stopped
// thinking in Eisenhower terms can empty all four axes, and the grid is then
// just the four keys, two by two, with no edges claiming a meaning they dropped.
function quadrantGrid() {
  const { columns, rows } = state.labels.matrix;
  const [now, next, last, never] = quadrants();
  if (![...columns, ...rows].some(Boolean)) {
    return el("div", { class: "matrix bare" },
      matrixCell(now), matrixCell(next), matrixCell(last), matrixCell(never));
  }
  const head = (text) => el("span", { class: "head" }, text);
  return el("div", { class: "matrix" },
    head(""), head(columns[0]), head(columns[1]),
    head(rows[0]), matrixCell(now), matrixCell(next),
    head(rows[1]), matrixCell(last), matrixCell(never));
}

// Never has no hue on purpose, here as in the sections: colouring it would say
// it ranks.
function matrixCell(quadrant) {
  return el("span", {
    class: `cell chord ${quadrant.hue === null ? "" : "hued"}`,
    style: quadrant.hue === null ? null : `--h: ${quadrant.hue}`,
    "data-cell": quadrant.n,
  }, el("kbd", {}, quadrant.n), el("i", {}, quadrant.name));
}

// --- archive -----------------------------------------------------------------

function renderArchive() {
  const rows = state.archive.rows;

  const filter = (value, label) => el("button", {
    class: state.archive.outcome === value ? "on" : "",
    onclick: () => { state.archive.outcome = value; loadArchive(); },
  }, label);

  const header = (key, label) => el("th", {
    class: "sortable",
    onclick: () => {
      const next = state.archive.sort === key && state.archive.dir === "desc" ? "asc" : "desc";
      state.archive.sort = key;
      state.archive.dir = next;
      loadArchive();
    },
  }, `${label}${state.archive.sort === key ? (state.archive.dir === "desc" ? " ↓" : " ↑") : ""}`);

  setChildren($("view"),
    el("div", { class: "tools" },
      el("input", {
        id: "search",
        value: state.archive.q,
        placeholder: "Filter by title",
        autocomplete: "off",
        oninput: (e) => { state.archive.q = e.target.value; loadArchive(); },
      }),
      el("div", { class: "filters" },
        filter("", "All"),
        filter("done", "Done"),
        filter("promoted", "Promoted"))),
    rows.length
      ? el("table", {},
          el("thead", {}, el("tr", {},
            el("th", {}, "Outcome"),
            el("th", {}, "Task"),
            header("created", "Created"),
            header("finished", "Finished"),
            el("th", {}, ""))),
          el("tbody", {}, ...rows.map(archiveRow)))
      : el("div", { class: "empty" },
          state.archive.q || state.archive.outcome
            ? "Nothing matches."
            : "The archive is empty. Tick something."));

  if (state.archive.q) {
    const search = $("search");
    if (search) { search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
  }
}

function archiveRow(task) {
  return el("tr", {},
    el("td", { class: "outcome" },
      task.outcome === "promoted"
        ? el("span", {}, "→ ", el("a", { href: "#", title: "The Jira ticket this became" }, task.jira_key || "ticket"))
        : el("span", { class: "done" }, "✓")),
    el("td", { class: "what", title: task.title }, task.title),
    el("td", {}, (task.created_at || "").slice(0, 10)),
    el("td", {}, (task.finished_at || "").slice(0, 10)),
    el("td", {}, el("button", {
      class: "restore",
      onclick: async () => {
        await api(`/api/tasks/${task.id}/restore`, { method: "POST" });
        toast(`Restored "${task.title}"`, "ok");
        loadArchive();
      },
    }, "Restore")));
}

// --- settings ----------------------------------------------------------------

// What the priorities are called and what they mean — cosmetic, so it is data
// rather than code. The keys, the order and the colours are not on this page:
// they are what the rest of the app's behaviour is built on.
const clone = (value) => JSON.parse(JSON.stringify(value));

async function loadSettings() {
  const data = await api("/api/settings");
  state.labels = data.labels;
  state.settings.defaults = data.defaults;
  if (!settingsDirty()) state.settings.draft = clone(data.labels);
  render();
}

function settingsDirty() {
  const { draft } = state.settings;
  return draft !== null && JSON.stringify(draft) !== JSON.stringify(state.labels);
}

function renderSettings() {
  const { draft } = state.settings;
  if (!draft) { setChildren($("view")); return; }

  // One input shape for every field. `set` writes the draft; nothing is sent
  // until Save.
  const field = (value, max, set, attrs) => el("input", {
    value,
    maxlength: max,
    autocomplete: "off",
    ...attrs,
    oninput: (e) => { set(e.target.value); settingsChanged(); },
    onkeydown: onSettingsKey,
  });

  const rows = draft.quadrants.map((q, i) => {
    const hue = QUADRANTS[i].hue;
    return el("div", { class: `label-row ${hue === null ? "" : "hued"}`,
                       style: hue === null ? null : `--h: ${hue}` },
      el("span", { class: "chord" }, el("kbd", {}, i + 1)),
      field(q.name, MAX_NAME, (v) => { q.name = v; }, {
        class: "name", "aria-label": `Name of priority ${i + 1}`,
      }),
      field(q.definition, MAX_DEFINITION, (v) => { q.definition = v; }, {
        class: "definition", placeholder: "no definition",
        "aria-label": `Definition of priority ${i + 1}`,
      }));
  });

  // The grid as triage shows it, with its edges editable in place — so what an
  // axis label is for is obvious from where it sits.
  const axis = (key, at, label) => field(draft.matrix[key][at], MAX_AXIS,
    (v) => { draft.matrix[key][at] = v; },
    { class: "head", placeholder: label.toLowerCase(), "aria-label": label });
  const [now, next, last, never] = QUADRANTS.map((q, i) => ({ ...q, ...draft.quadrants[i] }));
  const grid = el("div", { class: "matrix editable" },
    el("span", {}), axis("columns", 0, "Left column"), axis("columns", 1, "Right column"),
    axis("rows", 0, "Top row"), matrixCell(now), matrixCell(next),
    axis("rows", 1, "Bottom row"), matrixCell(last), matrixCell(never));

  setChildren($("view"),
    el("div", { class: "settings" },
      el("h2", {}, "Priorities"),
      el("p", { class: "note" },
        "What each priority is called on the page, and the line of explanation " +
        "beside it. The keys, the order and the colours stay as they are."),
      el("div", { class: "labels" }, ...rows),
      el("h2", {}, "Triage grid"),
      el("p", { class: "note" },
        "The edges of the grid triage shows. Leave all four empty and the grid " +
        "is just the four keys."),
      grid,
      el("div", { class: "actions" },
        el("button", { id: "save", class: "primary", onclick: saveSettings }, "Save"),
        el("button", {
          onclick: () => { state.settings.draft = clone(state.settings.defaults); render(); },
        }, "Restore defaults"),
        el("span", { id: "unsaved", class: "unsaved" }))));
  settingsChanged();
}

// Called on every keystroke, so it touches the few nodes that change rather
// than re-rendering — a re-render would take the cursor out of the field.
function settingsChanged() {
  const { draft } = state.settings;
  draft.quadrants.forEach((q, i) => {
    const name = document.querySelector(`[data-cell="${i + 1}"] i`);
    if (name) name.textContent = q.name;
  });
  const dirty = settingsDirty();
  const save = $("save");
  if (save) save.disabled = !dirty;
  const unsaved = $("unsaved");
  if (unsaved) unsaved.textContent = dirty ? "Unsaved changes" : "";
}

async function saveSettings() {
  if (!settingsDirty()) return;
  try {
    const data = await api("/api/settings", {
      method: "PUT", body: JSON.stringify({ labels: state.settings.draft }),
    });
    state.labels = data.labels;
    state.settings.draft = clone(data.labels);
    render();
    toast("Saved.", "ok");
  } catch (err) {
    toast(err.message);
  }
}

function onSettingsKey(event) {
  if (["Enter", "Escape"].includes(event.key)) event.stopPropagation();
  if (event.key === "Enter") {
    event.preventDefault();
    saveSettings();
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.target.blur();
  }
}

// --- undo --------------------------------------------------------------------

function renderUndo() {
  const bar = $("undo");
  const visible = state.view === "tasks" && state.undo.length && Date.now() < state.barUntil;
  bar.hidden = !visible;
  if (!visible) return;
  const last = state.undo[state.undo.length - 1];
  const more = state.undo.length - 1;
  setChildren(bar,
    el("span", { class: "what" },
      `${last.title} — done.${more ? ` · ${more} more undoable` : ""}`),
    el("button", { onclick: undoLast }, "Undo (Ctrl+Z)"));
}

// This page gets left open. Without this, a tab opened yesterday still calls
// yesterday "today": dates a day out read as due today, and the morning ritual
// never fires, because as far as the page is concerned the morning never came.
// Never while something is half-typed — a reload would take the words with it.
function checkForDayRollover() {
  if (state.today && localDate() === state.today) return false;
  if (state.editing !== null || state.dueFor !== null) return false;
  // A repaint there would take the cursor out of the field being typed in. The
  // Tasks tab reloads on the way back anyway.
  if (state.view === "settings") return false;
  const capture = $("capture");
  if (capture && capture.value) return false;
  loadTasks({ autoTriage: state.view === "tasks" && !state.triaging });
  return true;
}

async function undoLast() {
  const entry = state.undo.pop();
  if (!entry) { toast("Nothing to undo."); return; }
  await api(`/api/tasks/${entry.id}/restore`, { method: "POST" });
  state.barUntil = state.undo.length ? Date.now() + UNDO_VISIBLE_MS : 0;
  state.focus = entry.id;
  await loadTasks();
}

// --- actions -----------------------------------------------------------------

async function addTask(line) {
  const { title, due } = splitDue(line, state.today);
  if (!title) return;
  let task;
  try {
    task = await api("/api/tasks", { method: "POST", body: JSON.stringify({ title, due }) });
  } catch (err) {
    // Not written, so give the words back rather than losing them.
    const box = $("capture");
    if (box && !box.value) { box.value = line; updateCounter(); }
    toast(err.message);
    return;
  }
  // Triage picks it up after: the queue is a snapshot, so without this a task
  // written mid-triage could be neither walked to nor clicked on.
  if (state.triaging) state.queue.push({ ...task, reason: "unsorted" });
  await loadTasks();
  // The re-render destroys the input the keystroke came from, and focus falls
  // to the body. Rendering only restores it when nothing is selected, so with a
  // row selected the line went dead after one Enter and the next task typed
  // into nowhere. Pressing Enter in the capture line always keeps the line.
  focusInput("#capture");
}

async function completeTask(id) {
  const task = state.tasks.find((t) => t.id === id);
  if (!task) return;
  const order = visibleIds();
  const next = order[order.indexOf(id) + 1] ?? order[order.indexOf(id) - 1] ?? null;
  await api(`/api/tasks/${id}/complete`, { method: "POST" });
  state.undo.push({ id, title: task.title });
  state.barUntil = Date.now() + UNDO_VISIBLE_MS;
  setTimeout(renderUndo, UNDO_VISIBLE_MS + 50);
  if (state.triaging) {
    const current = queueTask();
    if (current && current.id === id) { advance(); return; }
    // Ticked by mouse on a row that is not the lit one. Advancing would step
    // off the task being triaged without anything having happened to it, so
    // the ticked one leaves the queue and the pointer stays where it is.
    const at = state.queue.findIndex((t) => t.id === id);
    if (at >= 0) {
      state.queue.splice(at, 1);
      if (at < state.qi) state.qi -= 1;
    }
    await loadTasks();
    return;
  }
  state.focus = next;
  await loadTasks();
}

async function patchTask(id, fields) {
  await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(fields) });
  await loadTasks();
}

async function setQuadrant(id, quadrant) {
  if (id === null) return;
  await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ quadrant }) });
  if (state.triaging) { advance(); return; }
  await loadTasks();
}

function promote() {
  toast("Jira promote isn't built yet — see DESIGN.md section 7.");
}

// --- triage ------------------------------------------------------------------

const queueTask = () => state.queue[state.qi] || null;

function startTriage() {
  // Today's queue first; once it is spent, an on-demand run offers everything
  // that still qualifies. Having triaged at nine must not make the ritual
  // unavailable at four, when the day has moved on.
  const source = state.triage.queue.length ? state.triage.queue : state.triage.all;
  if (!source || !source.length) { toast("Nothing to triage."); return; }
  // A snapshot, deliberately. The server's queue shrinks as tasks are triaged;
  // walking a shrinking list with a rising index steps over every second task.
  state.queue = source.slice();
  state.triaging = true;
  state.qi = 0;
  state.focus = null;
  state.editing = null;
  render();
}

function stopTriage() {
  state.triaging = false;
  state.queue = [];
  state.qi = 0;
  render();
}

// A click in triage means "this one": the lit task moves to it. One already in
// the queue is jumped to, as the arrows would; one that is not is slotted in
// at the current place, so the task you were on comes straight after it.
function pickForTriage(id) {
  const at = state.queue.findIndex((t) => t.id === id);
  if (at >= 0) {
    state.qi = at;
  } else {
    const task = state.tasks.find((t) => t.id === id);
    if (!task) return;
    state.queue.splice(state.qi, 0, { ...task, reason: "picked" });
  }
  state.dueFor = null;
  render();
}

async function advance() {
  state.qi += 1;
  state.dueFor = null;
  await loadTasks();
  if (state.qi >= state.queue.length) {
    const seen = state.queue.length;
    render();
    toast(`Page is triaged. ${seen} looked at.`, "ok");
    // Unless something was written in the moment before it closes, which puts
    // a task back in front of the pointer.
    setTimeout(() => { if (state.triaging && state.qi >= state.queue.length) stopTriage(); }, 1200);
    return;
  }
  render();
}

async function skipCurrent() {
  const task = queueTask();
  if (!task) return;
  await api(`/api/tasks/${task.id}/triaged`, { method: "POST" });
  advance();
}

// --- keyboard ----------------------------------------------------------------

function visibleIds() {
  const ids = [];
  for (const section of SECTIONS) {
    for (const task of state.tasks) if (task.quadrant === section.n) ids.push(task.id);
  }
  return ids;
}

// In triage this walks the queue; on the page it walks the rows. Moving through
// the queue marks nothing and calls nothing — it is navigation, so a task passed
// over can be gone back to. `n` is the one that skips and records it.
function step(by) {
  if (state.triaging) {
    if (!state.queue.length) return;
    state.qi = Math.min(Math.max(state.qi + by, 0), state.queue.length - 1);
    state.dueFor = null;
    render();
    return;
  }
  moveFocus(by);
}

function moveFocus(step) {
  const ids = visibleIds();
  if (!ids.length) return;
  const at = ids.indexOf(state.focus);
  if (at === -1) { state.focus = step > 0 ? ids[0] : ids[ids.length - 1]; }
  else { state.focus = ids[Math.min(Math.max(at + step, 0), ids.length - 1)]; }
  render();
}

// The document-level handler sees these keys too, and its Escape case would
// undo what these handlers just did — stepping down into the list and then
// immediately bouncing back to the capture row. Each handler that acts on a key
// stops it here.
function onCaptureKey(event) {
  const input = event.target;
  if (["Enter", "ArrowDown", "Escape"].includes(event.key)) event.stopPropagation();
  if (event.key === "Enter") {
    event.preventDefault();
    const value = input.value;
    // The line has room for a date on the end, so the eighty is held here
    // rather than by maxlength — and the words stay put when it is too long.
    if (splitDue(value, state.today).title.length > MAX_TITLE) {
      toast(`A task title is at most ${MAX_TITLE} characters.`);
      return;
    }
    input.value = "";
    updateCounter();
    addTask(value);
  } else if (event.key === "ArrowDown") {
    event.preventDefault();
    input.blur();
    leaveCapture();
  } else if (event.key === "Escape") {
    if (input.value) { input.value = ""; updateCounter(); }
    else { input.blur(); leaveCapture(); }
  }
}

// Out of the capture line: into the list, or in triage back to the lit task —
// the list's own focus means nothing there.
function leaveCapture() {
  if (state.triaging) render();
  else moveFocus(1);
}

function onEditKey(event, task) {
  if (["Enter", "Escape"].includes(event.key)) event.stopPropagation();
  if (event.key === "Enter") {
    event.preventDefault();
    const value = event.target.value.trim();
    state.editing = null;
    if (value && value !== task.title) patchTask(task.id, { title: value });
    else render();
  } else if (event.key === "Escape") {
    event.preventDefault();
    state.editing = null;
    render();
  }
}

function onDueKey(event, task) {
  if (["Enter", "Escape"].includes(event.key)) event.stopPropagation();
  if (event.key === "Enter") {
    event.preventDefault();
    const due = parseDue(event.target.value, state.today);
    if (due === undefined) { toast("Try tod, tom, fri, +3, 2026-09-30, or - to clear."); return; }
    state.dueFor = null;
    if (state.triaging) {
      api(`/api/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ due }) }).then(advance);
    } else {
      patchTask(task.id, { due });
    }
  } else if (event.key === "Escape") {
    event.preventDefault();
    state.dueFor = null;
    render();
  }
}

function target(event) {
  return state.triaging ? (queueTask() || {}).id ?? null : state.focus;
}

document.addEventListener("keydown", (event) => {
  const active = document.activeElement;
  const typing = active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA");

  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
    // While there is text in the box, Ctrl+Z belongs to the box.
    if (typing && active.value) return;
    event.preventDefault();
    undoLast();
    return;
  }
  if (typing) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;

  const id = target(event);

  switch (event.key) {
    case "j": case "ArrowDown": event.preventDefault(); step(1); break;
    case "k": case "ArrowUp": event.preventDefault(); step(-1); break;
    case " ": case "x":
      event.preventDefault();
      if (id !== null) completeTask(id);
      break;
    case "Enter": case "e":
      event.preventDefault();
      if (id !== null) { state.editing = id; render(); }
      break;
    case "1": case "2": case "3": case "4":
      event.preventDefault();
      if (id !== null) setQuadrant(id, Number(event.key));
      break;
    case "0":
      event.preventDefault();
      if (id !== null) setQuadrant(id, null);
      break;
    case "d":
      event.preventDefault();
      if (id !== null) { state.dueFor = id; render(); }
      break;
    case "J": event.preventDefault(); if (id !== null) promote(); break;
    case "u": event.preventDefault(); undoLast(); break;
    case "n":
      event.preventDefault();
      if (state.triaging) skipCurrent();
      break;
    case "p":
      event.preventDefault();
      if (state.view !== "tasks") { show("tasks"); return; }
      state.triaging ? stopTriage() : startTriage();
      break;
    case "/":
      // Triage never blocks capture, and writing a task is not leaving it:
      // what you write joins the end of the queue.
      event.preventDefault();
      if (state.view !== "tasks") break;
      state.focus = null;
      render();
      focusInput("#capture");
      break;
    case "a": event.preventDefault(); show("archive"); break;
    case "t": event.preventDefault(); show("tasks"); break;
    case "s": event.preventDefault(); show("settings"); break;
    case "Escape":
      event.preventDefault();
      if (state.triaging) stopTriage();
      else if (state.focus !== null) { state.focus = null; render(); focusInput("#capture"); }
      break;
    default: break;
  }
});

// --- views -------------------------------------------------------------------

function show(view) {
  if (state.view === view) return;
  state.view = view;
  state.focus = null;
  state.editing = null;
  state.dueFor = null;
  if (view === "archive") { stopTriage(); loadArchive(); }
  else if (view === "settings") { stopTriage(); loadSettings(); }
  else loadTasks();
}

$("tabs").addEventListener("click", (event) => {
  const view = event.target.dataset && event.target.dataset.view;
  if (view) show(view);
});

loadTasks({ autoTriage: true });

setInterval(checkForDayRollover, DAY_CHECK_MS);

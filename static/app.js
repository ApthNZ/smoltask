// smoltask front end. No build step, no framework, no dependencies.
//
// Two views, one page each. The tasks view is a notebook: a capture line, then
// ruled rows grouped by quadrant. Everything is reachable from the keyboard,
// because the mouse is what made the tool this replaces dangerous — a list that
// reflows under the cursor is how you complete the wrong row.

const QUADRANTS = [
  { n: 1, name: "Now", axis: "urgent & important" },
  { n: 2, name: "Next", axis: "important, not urgent" },
  { n: 3, name: "Last", axis: "urgent, not important" },
  { n: 4, name: "Never", axis: "neither" },
];
const UNSORTED = { n: null, name: "Unsorted", axis: "not yet triaged" };
const SECTIONS = [...QUADRANTS, UNSORTED];
const MAX_TITLE = 80;
const COUNTER_FROM = 65;
const UNDO_VISIBLE_MS = 12000;

const WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// The legend at the foot of the page. Keyed by where you are, because a bare
// letter is text while the capture line has focus and a shortcut while the list
// does, and a legend that does not say so is worse than none.
const KEYMAPS = {
  capture: [["Enter", "add the task"], ["Esc", "step into the list"],
            ["Ctrl+Z", "undo a completion"]],
  list: [["j k", "move"], ["space", "done"], ["1-4", "rank"], ["0", "unsort"],
         ["d", "due date"], ["e", "edit"], ["p", "triage"], ["a", "archive"],
         ["/", "capture line"], ["Ctrl+Z", "undo"]],
  triage: [["↑ ↓", "move"], ["1-4", "rank"], ["d", "due date"],
           ["space", "done"], ["n", "skip"], ["Esc", "leave triage"]],
  archive: [["t", "back to tasks"], ["click a heading", "sort"],
            ["Restore", "put it back on the page"]],
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
};

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

function formatDue(due, today) {
  const delta = dayNumber(due) - dayNumber(today);
  if (delta === 0) return "today";
  if (delta === 1) return "tomorrow";
  const date = new Date(`${due}T00:00:00`);
  if (delta > 1 && delta < 7) return WEEKDAYS[date.getDay()].replace(/^./, (c) => c.toUpperCase());
  return `${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

function shiftDays(iso, days) {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// `d` then: t, tom, a weekday, +N, an ISO date, or - to clear. Returns
// undefined when it cannot tell, which leaves the box open rather than
// guessing at a date the user did not mean.
function parseDue(input, today) {
  const text = (input || "").trim().toLowerCase();
  if (text === "" || text === "-") return null;
  if (text === "t" || text === "today") return today;
  if (text === "tom" || text === "tomorrow") return shiftDays(today, 1);
  if (/^\+\d+$/.test(text)) return shiftDays(today, parseInt(text.slice(1), 10));
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const weekday = WEEKDAYS.findIndex((d) => d.startsWith(text.slice(0, 3)));
  if (weekday >= 0) {
    const current = new Date(`${today}T00:00:00`).getDay();
    return shiftDays(today, ((weekday - current + 7) % 7) || 7);
  }
  return undefined;
}

// --- loading -----------------------------------------------------------------

// A server in the wrong timezone gets every "today" question wrong — the tick
// count, due today, the morning ritual — and does it silently. The browser
// knows what day it is here, so say so once rather than being quietly wrong.
function warnIfTheServerIsOnADifferentDay(serverToday) {
  if (warnIfTheServerIsOnADifferentDay.warned) return;
  const here = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const local = `${here.getFullYear()}-${pad(here.getMonth() + 1)}-${pad(here.getDate())}`;
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
  else renderArchive();
  renderUndo();
  renderKeys();
}

function whichKeymap() {
  if (state.view === "archive") return "archive";
  if (state.triaging) return "triage";
  return state.capturing ? "capture" : "list";
}

function renderKeys() {
  setChildren($("keys"), ...KEYMAPS[whichKeymap()].map(([key, what]) =>
    el("span", { class: "chord" }, el("kbd", {}, key), el("i", {}, what))));
}

function renderTasks() {
  $("count").textContent = state.tasks.length
    ? `${state.tasks.length} on the page`
    : "";

  const blocks = [];
  if (state.triaging) blocks.push(triageBar());
  blocks.push(captureRow());

  if (!state.tasks.length) {
    blocks.push(el("div", { class: "empty" },
      state.doneToday
        ? `Nothing on the page. ${state.doneToday} ticked today.`
        : "Nothing on the page."));
  } else {
    for (const section of SECTIONS) {
      const rows = state.tasks.filter((t) => t.quadrant === section.n);
      if (!rows.length) continue;
      blocks.push(el("div", { class: "section" },
        el("span", {}, section.name),
        section.axis ? el("span", { class: "axis" }, `— ${section.axis}`) : null));
      for (const task of rows) blocks.push(taskRow(task));
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
    maxlength: MAX_TITLE,
    placeholder: "Write a task, press Enter",
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
    el("div", { class: "box" }));
}

function updateCounter() {
  const input = $("capture");
  const counter = $("counter");
  if (!input || !counter) return;
  const used = input.value.length;
  counter.textContent = used >= COUNTER_FROM ? `${used}/${MAX_TITLE}` : "";
  counter.classList.toggle("full", used >= MAX_TITLE);
}

function taskRow(task) {
  const focused = state.focus === task.id;
  const current = state.triaging && queueTask();
  const isCurrent = current && current.id === task.id;
  const classes = ["row"];
  if (isCurrent) classes.push("lit");
  else if (state.triaging) classes.push("dim");
  else if (focused) classes.push("on");

  // Clicking anywhere that is not the title or the tick selects the row, so
  // there is a way to pick a task up without putting the cursor in its text.
  return el("div", {
      class: classes.join(" "),
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
          placeholder: "t / tom / fri / +3 / 2026-09-30 / -",
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
  if (state.focus === id && state.editing === null) return;
  state.focus = id;
  state.editing = null;
  render();
}

function dueLabel(task) {
  if (!task.due) return el("span", { class: "due" }, "");
  const overdue = dayNumber(task.due) < dayNumber(state.today);
  return el("span", {
    class: `due ${overdue ? "over" : ""}`,
    title: `Due ${task.due}`,
  }, formatDue(task.due, state.today));
}

function triageBar() {
  const task = queueTask();
  const left = state.queue.slice(state.qi);
  const remaining = (reason) => left.filter((t) => t.reason === reason).length;
  const parts = [];
  if (remaining("unsorted")) parts.push(`${remaining("unsorted")} to sort`);
  if (remaining("due")) parts.push(`${remaining("due")} due soon`);
  if (remaining("stale")) parts.push(`${remaining("stale")} stale`);

  const why = {
    unsorted: "not triaged yet",
    due: "due today or tomorrow",
    stale: `in Now for over a week`,
  }[task && task.reason] || "";

  return el("div", { class: "triage" },
    el("b", {}, task ? "Triage" : "Page is triaged."),
    task ? el("span", {}, `${state.qi + 1} of ${state.queue.length} — ${parts.join(", ")}`) : null,
    task ? el("span", { class: "why" }, `· ${why}`) : null,
    el("span", { class: "hint" }, task ? "1-4 rank · d date · space done · n skip · Esc leave" : "Esc to leave"));
}

// --- archive -----------------------------------------------------------------

function renderArchive() {
  const rows = state.archive.rows;
  $("count").textContent = rows.length ? `${rows.length} archived` : "";

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

async function undoLast() {
  const entry = state.undo.pop();
  if (!entry) { toast("Nothing to undo."); return; }
  await api(`/api/tasks/${entry.id}/restore`, { method: "POST" });
  state.barUntil = state.undo.length ? Date.now() + UNDO_VISIBLE_MS : 0;
  state.focus = entry.id;
  await loadTasks();
}

// --- actions -----------------------------------------------------------------

async function addTask(title) {
  const trimmed = title.trim();
  if (!trimmed) return;
  await api("/api/tasks", { method: "POST", body: JSON.stringify({ title: trimmed }) });
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
  if (state.triaging) { advance(); return; }
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

async function advance() {
  state.qi += 1;
  state.dueFor = null;
  await loadTasks();
  if (state.qi >= state.queue.length) {
    const seen = state.queue.length;
    render();
    toast(`Page is triaged. ${seen} looked at.`, "ok");
    setTimeout(stopTriage, 1200);
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
    input.value = "";
    updateCounter();
    addTask(value);
  } else if (event.key === "ArrowDown") {
    event.preventDefault();
    input.blur();
    moveFocus(1);
  } else if (event.key === "Escape") {
    if (input.value) { input.value = ""; updateCounter(); }
    else { input.blur(); moveFocus(1); }
  }
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
    if (due === undefined) { toast("Try t, tom, fri, +3, 2026-09-30, or - to clear."); return; }
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
      event.preventDefault();
      state.focus = null;
      if (state.triaging) stopTriage(); else render();
      focusInput("#capture");
      break;
    case "a": event.preventDefault(); show("archive"); break;
    case "t": event.preventDefault(); show("tasks"); break;
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
  else loadTasks();
}

$("tabs").addEventListener("click", (event) => {
  const view = event.target.dataset && event.target.dataset.view;
  if (view) show(view);
});

loadTasks({ autoTriage: true });

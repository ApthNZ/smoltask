"""Guards on the front end.

pytest cannot drive a browser here, so these assert on the source: the shape of
the markup, and the handful of mistakes that have been made before and would be
invisible until someone hit them in the real app.
"""

import re

import db
from conftest import ROOT

APP_JS = (ROOT / "static" / "app.js").read_text()
APP_CSS = (ROOT / "static" / "app.css").read_text()
INDEX = (ROOT / "static" / "index.html").read_text()


def test_index_loads_everything_it_needs():
    for asset in ("/static/app.css", "/static/app.js", "/static/favicon.svg", "/static/favicon.png"):
        assert asset in INDEX, f"index.html does not load {asset}"


def test_index_has_its_three_views_and_nothing_else():
    views = re.findall(r'data-view="(\w+)"', INDEX)
    assert views == ["tasks", "archive", "settings"], "three screens, deliberately"


def test_replacechildren_is_never_called_directly():
    """`el()` skips null children so conditionals can be written inline. Passing
    those straight to replaceChildren renders the literal text "null" to the
    user. Everything goes through setChildren, which filters the same way."""
    calls = re.findall(r"(\w+)\.replaceChildren\(", APP_JS)
    assert calls == ["node"], f"direct replaceChildren call: {calls}"
    assert "function setChildren(" in APP_JS


def test_the_title_limit_agrees_with_the_server():
    match = re.search(r"const MAX_TITLE = (\d+);", APP_JS)
    assert match and int(match.group(1)) == db.MAX_TITLE


def test_the_capture_input_enforces_the_limit_in_the_browser_too():
    """The line has room for a `~fri` on the end and no more; the title itself
    is held to the eighty before anything is sent, and the words stay put."""
    assert re.search(r"id: \"capture\",\s*\n\s*maxlength: MAX_TITLE \+ DATE_ROOM,", APP_JS)
    assert len(" ~2026-09-30") == int(re.search(r"const DATE_ROOM = (\d+);", APP_JS).group(1))
    body = APP_JS[APP_JS.index("function onCaptureKey("):]
    body = body[:body.index("\n}\n")]
    check = body.index("splitDue(value, state.today).title.length > MAX_TITLE")
    assert check < body.index('input.value = "";'), "the line is cleared before it is checked"


def test_the_sections_are_ordered_with_unsorted_last():
    # Unsorted is declared outside QUADRANTS and appended last, so an untriaged
    # task sorts to the bottom rather than ranking itself most important.
    assert "const SECTIONS = [...QUADRANTS, UNSORTED];" in APP_JS
    assert "for (const section of [...quadrants(), UNSORTED])" in APP_JS
    assert re.findall(r"\{ n: (\d), hue:", APP_JS) == ["1", "2", "3", "4"]


def test_the_quadrant_names_come_from_settings_not_the_source():
    """They are cosmetic, and the user wanted to change them without a code
    change. The defaults live in one place — the server — so the page cannot
    disagree with the settings screen about what "the default" is."""
    for name in ("Now", "Next", "Last", "Never"):
        assert f'"{name}"' not in APP_JS, f"{name} is spelled out in app.js"
    assert "...state.labels.quadrants[i]" in APP_JS
    assert "state.labels = data.labels;" in APP_JS
    assert [q["name"] for q in db.DEFAULT_LABELS["quadrants"]] == ["Now", "Next", "Last", "Never"]


def test_the_settings_limits_agree_with_the_server():
    for name in ("MAX_NAME", "MAX_DEFINITION", "MAX_AXIS"):
        match = re.search(rf"const {name} = (\d+);", APP_JS)
        assert match and int(match.group(1)) == getattr(db, name), name


def test_settings_are_saved_only_by_save():
    """Leaving the tab is not a decision to keep what was typed there, and
    Restore defaults only fills the form — Save is the one thing that writes."""
    assert APP_JS.count('method: "PUT"') == 1
    body = APP_JS[APP_JS.index("function renderSettings("):]
    body = body[:body.index("\n}\n")]
    assert "state.settings.draft = clone(state.settings.defaults); render();" in body
    assert "onclick: saveSettings" in body


def test_typing_in_settings_does_not_rerender():
    """A re-render per keystroke would take the cursor out of the field."""
    body = APP_JS[APP_JS.index("function settingsChanged("):]
    body = body[:body.index("\n}\n")]
    assert "render()" not in body
    assert "oninput: (e) => { set(e.target.value); settingsChanged(); }" in APP_JS


def test_the_day_rollover_leaves_settings_alone():
    body = APP_JS[APP_JS.index("function checkForDayRollover()"):]
    body = body[:body.index("\n}\n")]
    assert 'if (state.view === "settings") return false;' in body


def test_the_triage_queue_is_a_snapshot():
    """Refreshing the queue mid-pass steps over every second task: an acted-on
    task drops out of the server's queue and the rising index skips its
    replacement. This bug has been written once already."""
    assert "state.queue = source.slice()" in APP_JS
    assert "state.queue[state.qi]" in APP_JS
    assert "state.triage.queue[state.qi]" not in APP_JS


def test_the_quadrant_grid_is_shown_only_in_triage():
    """It answers "which digit is which", which is a question you only have in
    the run of 1-4 presses triage is. On the page all day it would be a legend
    restating four section headers that are already on screen."""
    assert "blocks.push(triageBar(), quadrantGrid());" in APP_JS
    assert APP_JS.count("quadrantGrid()") == 2, "the grid is rendered in one place"


def test_the_quadrant_grid_reads_from_the_one_list_of_quadrants():
    """Four names and hues typed out a second time is four chances for the grid
    to disagree with the sections it is explaining."""
    body = APP_JS[APP_JS.index("function quadrantGrid("):]
    body = body[:body.index("\n}\n")]
    assert "const [now, next, last, never] = quadrants();" in body
    cell = APP_JS[APP_JS.index("function matrixCell("):]
    cell = cell[:cell.index("\n}\n")]
    assert "quadrant.name" in cell and "quadrant.n" in cell and "quadrant.hue" in cell


def test_the_grid_is_laid_out_as_the_matrix_not_a_list():
    """Read across then down, 1-4 land on the classic quadrants. That ordering
    is the whole argument for a 2x2 — a row of four would be a legend."""
    body = APP_JS[APP_JS.index("function quadrantGrid("):]
    body = body[:body.index("\n}\n")]
    order = re.findall(r"matrixCell\((\w+)\)", body)
    # Once without axes, once with.
    assert order == ["now", "next", "last", "never"] * 2
    heads = re.findall(r'head\(([^)]*)\)', body)
    assert heads == ['""', "columns[0]", "columns[1]", "rows[0]", "rows[1]"]
    assert [*db.DEFAULT_LABELS["matrix"]["columns"], *db.DEFAULT_LABELS["matrix"]["rows"]] \
        == ["urgent", "not urgent", "important", "not important"]
    # Sized to its own four cells rather than stretched across the page: a
    # diagram to glance at, not a second bar.
    assert "grid-template-columns: auto auto auto;" in APP_CSS
    assert "width: max-content;" in APP_CSS


def test_the_grid_without_axes_is_two_by_two():
    """Someone who has dropped the Eisenhower framing can empty all four axes,
    and the grid stops claiming it."""
    body = APP_JS[APP_JS.index("function quadrantGrid("):]
    body = body[:body.index("\n}\n")]
    assert "if (![...columns, ...rows].some(Boolean))" in body
    assert '"matrix bare"' in body
    assert ".matrix.bare { grid-template-columns: auto auto; }" in APP_CSS


def test_never_is_uncoloured_in_the_grid_as_it_is_in_the_sections():
    """Colouring the fourth quadrant would say it ranks."""
    body = APP_JS[APP_JS.index("function matrixCell("):]
    body = body[:body.index("\n}\n")]
    assert 'quadrant.hue === null ? "" : "hued"' in body
    assert "quadrant.hue === null ? null : `--h: ${quadrant.hue}`" in body


def test_the_grid_borrows_the_legend_key_styling():
    """A digit in the grid is the key you press. One set of rules says what a
    key looks like, and the grid uses it rather than growing a second."""
    body = APP_JS[APP_JS.index("function matrixCell("):]
    body = body[:body.index("\n}\n")]
    assert "chord" in body and 'el("kbd", {}, quadrant.n)' in body
    assert APP_CSS.count(".chord kbd {") == 1


def test_the_section_headers_carry_their_rank_key():
    """An unused section is not rendered, so without this the mapping for a
    quadrant you have not filled is nowhere on the page."""
    assert 'section.n ? el("span", { class: "rank" }, section.n) : null,' in APP_JS
    # Unsorted has no key: `0` unsorts, and numbering it 5 would rank it.
    assert ".section .rank {" in APP_CSS


def test_undo_is_a_stack_not_a_single_step():
    """The laggy-machine-completed-five-rows case is the reason this app exists.
    Undo has to handle it."""
    assert "state.undo.push(" in APP_JS
    assert "state.undo.pop()" in APP_JS


def test_completion_is_undoable_from_the_keyboard():
    assert 'case "u":' in APP_JS
    assert 'event.key.toLowerCase() === "z"' in APP_JS


def test_the_keyboard_covers_the_documented_keys():
    for key in ('case "j":', 'case "k":', 'case " ":', 'case "d":',
                'case "1":', 'case "0":', 'case "p":', 'case "a":', 'case "t":',
                'case "Escape":'):
        assert key in APP_JS, f"keymap is missing {key}"


def test_typing_is_never_swallowed_by_a_shortcut():
    """Every single-letter shortcut is behind a check that focus is not in an
    input, or the capture box would be unusable."""
    assert re.search(r"if \(typing\) return;", APP_JS)


def test_ctrl_z_defers_to_the_browser_while_there_is_text():
    assert "if (typing && active.value) return;" in APP_JS


def test_input_handlers_stop_keys_reaching_the_global_handler():
    """Both handlers fire for a key pressed inside an input. The global Escape
    case would undo what the capture row's own handler just did — step down into
    the list, then bounce straight back up to the capture row."""
    for handler in ("onCaptureKey", "onEditKey", "onDueKey"):
        body = APP_JS[APP_JS.index(f"function {handler}("):][:400]
        assert "event.stopPropagation()" in body, f"{handler} lets its keys bubble"


def test_a_wrong_server_timezone_is_surfaced_not_swallowed():
    """A container with no TZ runs in UTC and gets every "today" question wrong
    without ever failing. The browser knows better and says so."""
    assert "warnIfTheServerIsOnADifferentDay" in APP_JS
    assert "Set TZ." in APP_JS


def test_adding_a_task_keeps_the_capture_line():
    """The re-render destroys the input the keystroke came from. Rendering only
    restores focus when nothing is selected, so with a row selected the line
    went dead after one Enter and the next task typed into nowhere."""
    body = APP_JS[APP_JS.index("async function addTask("):]
    body = body[:body.index("\n}\n")]
    assert body.rstrip().endswith('focusInput("#capture", { caretAtEnd: true });')


def test_the_next_task_survives_the_last_one_saving():
    """In fast capture the next line is being typed while the last one saves.
    The save re-renders the page, which rebuilt the capture line empty — and
    then re-focused it with everything selected, so the next keystroke replaced
    whatever had survived. Both are pinned: the words are carried across the
    render, and the focus after a capture puts the caret at the end."""
    render = APP_JS[APP_JS.index("function renderTasks("):]
    render = render[:render.index("\n}\n")]
    assert "carried" in render and "box.value = carried.value" in render


def test_the_date_box_says_how_to_clear_a_date():
    """It said so with a bare trailing "- ", in a box too narrow to show it. A
    hint that is cut off the end is the same as no hint: the way to clear a due
    date was, in practice, undocumented."""
    assert 'placeholder: "tod · +3 · fri · 2026-09-30 · empty clears"' in APP_JS
    # Pressing Enter on an empty box is what the hint now promises.
    parser = APP_JS[APP_JS.index("function parseDue("):][:600]
    assert 'if (text === "" || text === "-") return null;' in parser


def test_dates_accept_any_prefix_of_the_word():
    """"tod" is as natural a thing to type as "t", and one blessed abbreviation
    per word is a rule nobody can remember."""
    assert '"today".startsWith(text)' in APP_JS
    assert '"tomorrow".startsWith(text)' in APP_JS
    # Today is tested first, so the shared "t"/"to" prefix is not ambiguous.
    assert APP_JS.index('"today".startsWith(text)') < APP_JS.index('"tomorrow".startsWith(text)')
    assert 'placeholder: "tod · +3 · fri' in APP_JS


def test_the_legend_names_actions_not_parts_of_the_ui():
    """"capture line" names a thing on the page; the legend has room only to
    say what the key does."""
    assert '"capture line"' not in APP_JS
    assert '["/", "new task"]' in APP_JS


def test_the_key_legend_is_always_on_screen():
    """Not a help modal — a strip at the foot of every screen."""
    assert '<footer id="keys">' in INDEX
    assert "#keys {" in APP_CSS and "position: fixed; bottom: 0;" in APP_CSS
    for context in ("capture", "list", "triage", "triageCapture", "archive", "settings"):
        assert f"  {context}: [" in APP_JS, f"no legend for the {context} context"


def test_the_legend_tells_the_truth_about_where_focus_is():
    """A bare letter is text in the capture line and a shortcut in the list.
    The legend switches on that rather than listing both and hoping."""
    assert "function whichKeymap()" in APP_JS
    assert "state.capturing ? \"capture\" : \"list\"" in APP_JS
    assert "onfocus: () => { state.capturing = true; renderKeys(); }" in APP_JS


def test_notifications_are_in_the_header_and_cover_nothing():
    """At the top where the eyes are, but in the flow — a fixed bar sat over the
    first line of the page, which is the capture line, the one thing that must
    never be covered."""
    header = INDEX[INDEX.index("<header>"):INDEX.index("</header>")]
    assert '<div id="notify">' in header, "notifications are not in the header"
    assert not re.search(r"(?<!-)bottom: 18px", APP_CSS), "a notification is still pinned to the foot"
    notify = APP_CSS[APP_CSS.index("#notify {"):][:160]
    assert "position: fixed" not in notify, "notifications still float over the page"
    assert "flex-wrap: wrap" in APP_CSS[APP_CSS.index("header {"):][:220], \
        "a long notification would squash the header instead of wrapping"


def test_the_counters_are_gone():
    """"4 on the page" and "1 archived" restated what was already on screen."""
    assert "on the page`" not in APP_JS
    assert "archived`" not in APP_JS
    assert 'id="count"' not in INDEX


def test_both_ways_of_moving_are_advertised():
    for context in ("list", "triage"):
        keys = APP_JS[APP_JS.index(f"  {context}: ["):][:90]
        assert "j k \u2191 \u2193" in keys or "j k ↑ ↓" in keys, f"{context}: {keys[:60]}"


def test_quadrant_colour_comes_from_the_shared_palette():
    """A little colour, on the two things that carry meaning. The hues are
    smolplan's, picked there to stay clear of the green and red used for status
    — so overdue stays the only red on the page."""
    hues = re.findall(r"hue: (\d+|null)", APP_JS)
    assert hues == ["30", "210", "265", "null", "null"], hues
    assert ".section.hued .name { color: hsl(var(--h)" in APP_CSS
    assert ".row.hued { border-left-color: hsl(var(--h)" in APP_CSS


def test_a_row_without_a_quadrant_gets_no_colour():
    """Never and Unsorted are not priorities and should not look like one."""
    row = APP_JS[APP_JS.index("function taskRow(task,"):APP_JS.index("function select(id)")]
    assert 'style: hue === null ? null : `--h: ${hue}`' in row
    assert 'if (hue !== null) classes.push("hued");' in row


def test_good_news_is_not_delivered_in_red():
    assert "#toast.ok { background: var(--green-bg)" in APP_CSS
    assert "#toast.warn { background: var(--red-bg)" in APP_CSS
    assert 'toast(`Page is triaged. ${seen} looked at.`, "ok")' in APP_JS
    assert 'function toast(message, tone = "warn")' in APP_JS


def test_arrows_walk_the_triage_queue():
    """They did nothing at all in triage, which left the queue one-directional."""
    body = APP_JS[APP_JS.index("function step(by)"):][:420]
    assert "if (state.triaging)" in body
    assert "state.qi = Math.min(Math.max(state.qi + by, 0), state.queue.length - 1)" in body
    assert 'case "j": case "ArrowDown": event.preventDefault(); step(1); break;' in APP_JS


def test_a_task_can_be_selected_without_opening_its_text():
    """Clicking the title edits it. There has to be another way to pick a row
    up, or the keyboard is unreachable by mouse."""
    assert "function select(id)" in APP_JS
    row = APP_JS[APP_JS.index("function taskRow(task,"):APP_JS.index("function select(id)")]
    assert "onclick: () => select(task.id)" in row, "the row itself does not select"
    assert 'class: "bullet"' in row
    # The title's own handler must not also select-and-then-edit twice over.
    assert "e.stopPropagation();" in row


def test_the_title_does_not_fill_the_row():
    """If it did, "click the row to select" would be unreachable — nearly every
    click would land on the text and open the editor instead."""
    assert ".title {\n  flex: 0 1 auto;" in APP_CSS
    assert ".gap { flex: 1 1 auto;" in APP_CSS
    row = APP_JS[APP_JS.index("function taskRow(task,"):APP_JS.index("function select(id)")]
    assert row.index('class: "title"') < row.index('class: "gap"')


def test_the_tick_is_at_the_right_margin():
    """Bullet, then the words, then the tick — the way a line in a notebook
    reads."""
    row = APP_JS[APP_JS.index("function taskRow(task,"):APP_JS.index("function select(id)")]
    assert row.index('class: "bullet"') < row.index('class: "title"') < row.index('class: "tick"')
    capture = APP_JS[APP_JS.index("function captureRow()"):]
    capture = capture[:capture.index("\n}\n")]
    assert capture.index('class: "bullet ghost"') < capture.index('class: "box"')


def test_no_unicode_escapes_are_left_in_the_source():
    """The file uses literal characters. A mix means a search-and-replace over
    one spelling silently misses the other — which has now happened twice, once
    leaving a row with two tick buttons."""
    assert not re.findall(r"\\u[0-9a-fA-F]{4}", APP_JS)


def test_a_date_on_a_never_task_is_flagged():
    """A date on a task ranked Never is a date promised to someone and disowned
    in the same breath. It takes the same red as overdue, because it is the same
    message: this date needs a human."""
    body = APP_JS[APP_JS.index("function dueLabel(task)"):][:700]
    assert "const disowned = task.quadrant === NEVER;" in body
    assert "overdue || disowned" in body
    assert "`ranked ${nameOf(NEVER)}`" in body, "the tooltip does not say why it is red"
    assert "const NEVER = 4;" in APP_JS


def test_triage_explains_a_disowned_date():
    """The queue carries the reason; the bar has to be able to say it."""
    assert "disowned: `dated, but ranked ${nameOf(NEVER)}`" in APP_JS
    assert "dated ${nameOf(NEVER)}`" in APP_JS, "the bar does not count them"
    # And whatever the user has called the first quadrant goes stale.
    assert "stale: `in ${nameOf(STALE)} for over a week`" in APP_JS
    assert "const STALE = 1;" in APP_JS and db.NEVER == 4


def test_red_still_means_only_one_thing():
    """The rule is that red on the page means a date needs attention. It must
    not leak onto anything else."""
    reds = [line.strip() for line in APP_CSS.splitlines()
            if "var(--red)" in line and "toast" not in line and "counter" not in line]
    assert all(".due.over" in r or "#toast" in r for r in reds), reds


def test_the_page_notices_the_day_changing_under_it():
    """A notebook gets left open. A tab opened yesterday would keep calling
    yesterday "today": dates a day out reading as due today, and a morning
    ritual that never fires because the morning never came."""
    assert "function checkForDayRollover()" in APP_JS
    assert "setInterval(checkForDayRollover, DAY_CHECK_MS);" in APP_JS
    body = APP_JS[APP_JS.index("function checkForDayRollover()"):][:520]
    assert "localDate() === state.today" in body
    # It must not yank the page out from under someone mid-sentence.
    assert "state.editing !== null || state.dueFor !== null" in body
    assert "capture.value" in body


def test_a_date_in_another_year_says_so():
    """Without the year, a date twelve months out reads exactly like one next
    month."""
    body = APP_JS[APP_JS.index("function formatDue("):][:700]
    assert "date.getFullYear() === Number(today.slice(0, 4))" in body


def test_there_is_one_place_that_knows_what_day_it_is_here():
    assert "function localDate(" in APP_JS
    assert APP_JS.count("getMonth() + 1") == 1, "the local-date calculation is duplicated"


def test_the_page_never_reloads_itself():
    """Firefox restores form-control state across location.reload() by position,
    so a reload that drops a row shifts every later row onto a restored value
    belonging to a different record. Repaint from the API response instead."""
    assert "location.reload" not in APP_JS
    assert "location.href" not in APP_JS


def test_autocomplete_is_off_on_every_input():
    inputs = APP_JS.count('el("input", {')
    assert inputs == APP_JS.count('autocomplete: "off"'), "an input is missing autocomplete off"


def test_dark_theme_overrides_follow_the_rules_they_override():
    """Same specificity, so source order decides the winner. A dark block placed
    above its light rules silently loses."""
    root_light = APP_CSS.index(":root {")
    root_dark = APP_CSS.index("@media (prefers-color-scheme: dark)")
    assert root_light < root_dark
    # Every rule that hardcodes a colour instead of using a token needs a dark
    # counterpart, and it has to come after.
    for selector in (".triage", ".section.hued .name", ".row.hued",
                     ".matrix .cell.hued i"):
        light = APP_CSS.index(f"{selector} {{")
        dark = APP_CSS.index(f"  {selector} {{")
        assert light < dark, f"{selector}'s dark override comes before its light rules"


def test_the_notebook_row_height_is_a_token():
    assert "--row: 30px;" in APP_CSS
    assert "height: var(--row);" in APP_CSS


def test_titles_never_wrap():
    assert "white-space: nowrap" in APP_CSS


# --- triage and capture --------------------------------------------------------


def test_a_task_written_mid_triage_joins_the_queue():
    """The queue is a snapshot, so a task captured during triage could be
    neither walked to with the arrows nor clicked on — the lowest you could get
    was the last task that existed when triage started."""
    body = APP_JS[APP_JS.index("async function addTask("):]
    body = body[:body.index("\n}\n")]
    assert 'if (state.triaging) state.queue.push({ ...task, reason: "unsorted" });' in body


def test_clicking_a_row_in_triage_picks_it():
    """A click in triage did nothing at all: it set the list's focus, which
    triage does not look at."""
    assert "if (state.triaging) { pickForTriage(id); return; }" in APP_JS
    body = APP_JS[APP_JS.index("function pickForTriage("):]
    body = body[:body.index("\n}\n")]
    assert "state.qi = at;" in body
    assert 'state.queue.splice(state.qi, 0, { ...task, reason: "picked" });' in body
    assert 'picked: "picked by hand"' in APP_JS


def test_writing_a_task_does_not_end_triage():
    """`/` used to leave triage, so a manual run could not take a new task while
    the automatic one — reached by clicking the line — could. Triage never
    blocks capture."""
    case = APP_JS[APP_JS.index('    case "/":'):APP_JS.index('    case "a":')]
    assert "stopTriage" not in case
    assert 'focusInput("#capture");' in case
    assert '["/", "new task"], ["Esc", "leave triage"]' in APP_JS


def test_leaving_the_capture_line_in_triage_goes_back_to_the_lit_task():
    body = APP_JS[APP_JS.index("function onCaptureKey("):]
    body = body[:body.index("\n}\n")]
    assert "moveFocus" not in body
    assert body.count("leaveCapture()") == 2
    assert "if (state.triaging) render();" in APP_JS


def test_triage_does_not_close_on_a_task_written_as_it_finished():
    body = APP_JS[APP_JS.index("async function advance("):]
    body = body[:body.index("\n}\n")]
    assert "state.triaging && state.qi >= state.queue.length) stopTriage();" in body


def test_the_legend_in_a_triage_capture_says_letters_are_text():
    assert 'if (state.triaging) return state.capturing ? "triageCapture" : "triage";' in APP_JS


# --- dates on the capture line --------------------------------------------------


def test_a_date_can_ride_on_the_end_of_a_new_task():
    """`call Bob ~fri`. Only the last word, only with a `~`, and only when the
    date box would take it — so URLs, paths and "~5 mins" stay text."""
    assert r"const INLINE_DUE = /\s~+(\S+)$/;" in APP_JS
    body = APP_JS[APP_JS.index("function splitDue("):]
    body = body[:body.index("\n}\n")]
    assert "parseDue(match[1], today)" in body, "a second date grammar has appeared"
    # null is parseDue's "clear the date" — not a date to file.
    assert 'if (typeof due !== "string") return { title: text, due: null };' in body


def test_the_capture_line_shows_the_date_it_will_file():
    assert 'el("span", { id: "capdue", class: "due" })' in APP_JS
    body = APP_JS[APP_JS.index("function updateCounter("):]
    body = body[:body.index("\n}\n")]
    assert "formatDue(due, state.today)" in body
    # The eighty counts the title, not the date riding on it.
    assert "const used = title.length;" in body


def test_a_task_that_fails_to_save_keeps_its_words():
    body = APP_JS[APP_JS.index("async function addTask("):]
    body = body[:body.index("\n}\n")]
    assert "box.value = line;" in body


def test_ticking_another_row_in_triage_does_not_skip_the_lit_one():
    """Completing always advanced, so a mouse tick on any other row stepped off
    the task being triaged without anything having happened to it."""
    body = APP_JS[APP_JS.index("async function completeTask("):]
    body = body[:body.index("\n}\n")]
    assert "if (current && current.id === id) { advance(); return; }" in body
    assert "state.queue.splice(at, 1);" in body
    assert "if (at < state.qi) state.qi -= 1;" in body


def test_editing_a_title_puts_the_cursor_at_the_end_not_over_the_text():
    """Selecting the whole title meant the first keystroke replaced it, and
    getting to a word meant pressing Right first. An edit is usually one word."""
    assert 'focusInput(`[data-edit="${state.editing}"]`, { caretAtEnd: true });' in APP_JS
    body = APP_JS[APP_JS.index("function focusInput("):]
    body = body[:body.index("\n}\n")]
    assert "node.setSelectionRange(node.value.length, node.value.length)" in body


def test_styles_are_set_through_the_cssom_not_as_attributes():
    """The CSP refuses inline style attributes, so a `style` passed to `el()`
    and set with setAttribute rendered unstyled — the section hues vanished
    with nothing but a console warning. It goes through `node.style.cssText`."""
    assert 'k === "style") node.style.cssText = v' in APP_JS
    assert not re.search(r"setAttribute\(\s*[\"']style", APP_JS)
    assert "<script>" not in INDEX
    assert not re.search(r"\son\w+=", INDEX), "inline handlers are inline script"


def test_a_failed_capture_is_never_lost():
    """In fast capture the next task is already being typed when the first one
    fails, so "give the words back if the line is empty" usually meant losing
    them. They wait in `unsent`, the toast names them, and Enter on an empty
    line sends them again."""
    body = APP_JS[APP_JS.index("async function addTask("):]
    body = body[:body.index("\n}\n")]
    assert "state.unsent.push(line)" in body
    assert "unsent: []" in APP_JS
    assert "state.unsent.splice(0)" in APP_JS, "nothing resends them"


def test_a_failed_completion_says_so():
    body = APP_JS[APP_JS.index("async function completeTask("):]
    body = body[:body.index("\n}\n")]
    assert "catch (err)" in body and "toast(err.message)" in body

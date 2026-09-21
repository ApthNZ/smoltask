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


def test_index_has_both_views_and_nothing_else():
    views = re.findall(r'data-view="(\w+)"', INDEX)
    assert views == ["tasks", "archive"], "two screens, deliberately"


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
    assert re.search(r"id: \"capture\",\s*\n\s*maxlength: MAX_TITLE", APP_JS)


def test_the_sections_are_named_and_ordered():
    names = re.findall(r'name: "(\w+)", axis:', APP_JS)
    assert names == ["Now", "Next", "Last", "Never", "Unsorted"]
    # Unsorted is declared outside QUADRANTS and appended last, so an untriaged
    # task sorts to the bottom rather than ranking itself most important.
    assert "[...QUADRANTS, UNSORTED]" in APP_JS


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
    assert "const [now, next, last, never] = QUADRANTS;" in body
    assert "quadrant.name" in body and "quadrant.n" in body and "quadrant.hue" in body
    for name in ("Now", "Next", "Last", "Never"):
        assert f'"{name}"' not in body, f"{name} is spelled out in the grid"


def test_the_grid_is_laid_out_as_the_matrix_not_a_list():
    """Read across then down, 1-4 land on the classic quadrants. That ordering
    is the whole argument for a 2x2 — a row of four would be a legend."""
    body = APP_JS[APP_JS.index("function quadrantGrid("):]
    body = body[:body.index("\n}\n")]
    order = re.findall(r"cell\((\w+)\)", body)
    assert order == ["now", "next", "last", "never"]
    heads = re.findall(r'head\("([^"]*)"\)', body)
    assert heads == ["", "urgent", "not urgent", "important", "not important"]
    # Sized to its own four cells rather than stretched across the page: a
    # diagram to glance at, not a second bar.
    assert "grid-template-columns: auto auto auto;" in APP_CSS
    assert "width: max-content;" in APP_CSS


def test_never_is_uncoloured_in_the_grid_as_it_is_in_the_sections():
    """Colouring the fourth quadrant would say it ranks."""
    body = APP_JS[APP_JS.index("function quadrantGrid("):]
    body = body[:body.index("\n}\n")]
    assert 'quadrant.hue === null ? "" : "hued"' in body
    assert "quadrant.hue === null ? null : `--h: ${quadrant.hue}`" in body


def test_the_grid_borrows_the_legend_key_styling():
    """A digit in the grid is the key you press. One set of rules says what a
    key looks like, and the grid uses it rather than growing a second."""
    body = APP_JS[APP_JS.index("function quadrantGrid("):]
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
    body = APP_JS[APP_JS.index("async function addTask("):][:600]
    assert 'focusInput("#capture");' in body


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
    for context in ("capture", "list", "triage", "archive"):
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
    assert "bottom: 18px" not in APP_CSS, "a notification is still pinned to the foot"
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
    capture = APP_JS[APP_JS.index("function captureRow()"):][:600]
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
    assert '"ranked Never"' in body, "the tooltip does not say why it is red"
    assert "const NEVER = 4;" in APP_JS


def test_triage_explains_a_disowned_date():
    """The queue carries the reason; the bar has to be able to say it."""
    assert 'disowned: "dated, but ranked Never"' in APP_JS
    assert 'dated Never`' in APP_JS, "the bar does not count them"


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

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
    assert "state.queue = state.triage.queue.slice()" in APP_JS
    assert "state.queue[state.qi]" in APP_JS
    assert "state.triage.queue[state.qi]" not in APP_JS


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
    for selector in (".triage", ".undo"):
        light = APP_CSS.index(f"{selector} {{")
        dark = APP_CSS.index(f"  {selector} {{")
        assert light < dark, f"{selector}'s dark override comes before its light rules"


def test_the_notebook_row_height_is_a_token():
    assert "--row: 30px;" in APP_CSS
    assert "height: var(--row);" in APP_CSS


def test_titles_never_wrap():
    assert "white-space: nowrap" in APP_CSS

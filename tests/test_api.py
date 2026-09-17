"""The API surface: create, patch, complete, restore, and the shapes returned."""

from conftest import add


def test_health_opens_the_database(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "open": 0}
    add(client, "Email bob")
    assert client.get("/health").json()["open"] == 1


def test_a_new_task_is_unsorted_and_undated(client):
    task = add(client, "Email bob")
    assert task["quadrant"] is None
    assert task["due"] is None
    assert task["finished_at"] is None
    assert task["outcome"] is None


def test_creating_a_task_returns_201(client):
    assert client.post("/api/tasks", json={"title": "Email bob"}).status_code == 201


def test_patch_only_touches_fields_that_were_sent(client):
    task = add(client, "Email bob", quadrant=2, due="2026-09-20")
    patched = client.patch(f"/api/tasks/{task['id']}", json={"quadrant": 1}).json()
    assert patched["quadrant"] == 1
    assert patched["due"] == "2026-09-20", "an absent field was not left alone"


def test_an_explicit_null_clears_the_due_date(client):
    task = add(client, "Email bob", due="2026-09-20")
    assert client.patch(f"/api/tasks/{task['id']}", json={"due": None}).json()["due"] is None


def test_an_empty_patch_is_a_bad_request(client):
    task = add(client, "Email bob")
    assert client.patch(f"/api/tasks/{task['id']}", json={}).status_code == 400


def test_completing_moves_a_task_to_the_archive(client):
    task = add(client, "Email bob")
    done = client.post(f"/api/tasks/{task['id']}/complete").json()
    assert done["outcome"] == "done"
    assert done["finished_at"] is not None
    assert client.get("/api/tasks").json()["tasks"] == []
    assert [t["title"] for t in client.get("/api/archive").json()["tasks"]] == ["Email bob"]


def test_completing_twice_is_not_an_error(client):
    """A laggy machine sends the same click twice. That is not a failure state."""
    task = add(client, "Email bob")
    first = client.post(f"/api/tasks/{task['id']}/complete").json()
    second = client.post(f"/api/tasks/{task['id']}/complete")
    assert second.status_code == 200
    assert second.json()["finished_at"] == first["finished_at"]


def test_restore_puts_it_back_with_its_quadrant_and_date(client):
    task = add(client, "Email bob", quadrant=1, due="2026-09-20")
    client.post(f"/api/tasks/{task['id']}/complete")
    back = client.post(f"/api/tasks/{task['id']}/restore").json()
    assert back["finished_at"] is None and back["outcome"] is None
    assert back["quadrant"] == 1 and back["due"] == "2026-09-20"
    assert len(client.get("/api/tasks").json()["tasks"]) == 1


def test_restoring_many_in_a_row_works(client):
    """The undo stack is the whole reason this app exists — restoring five
    completions in sequence has to work, not just the most recent one."""
    ids = [add(client, f"Task {n}")["id"] for n in range(5)]
    for task_id in ids:
        client.post(f"/api/tasks/{task_id}/complete")
    assert client.get("/api/tasks").json()["tasks"] == []
    for task_id in reversed(ids):
        assert client.post(f"/api/tasks/{task_id}/restore").status_code == 200
    assert len(client.get("/api/tasks").json()["tasks"]) == 5


def test_patching_an_archived_task_is_refused(client):
    task = add(client, "Email bob")
    client.post(f"/api/tasks/{task['id']}/complete")
    response = client.patch(f"/api/tasks/{task['id']}", json={"quadrant": 1})
    assert response.status_code == 400
    assert "archive" in response.json()["detail"].lower()


def test_unknown_task_is_404(client):
    assert client.patch("/api/tasks/999", json={"quadrant": 1}).status_code == 404
    assert client.post("/api/tasks/999/complete").status_code == 404
    assert client.post("/api/tasks/999/restore").status_code == 404
    assert client.post("/api/tasks/999/triaged").status_code == 404


def test_the_page_payload_carries_what_the_page_needs(client):
    body = client.get("/api/tasks").json()
    assert set(body) == {"today", "tasks", "triage", "done_today"}
    assert set(body["triage"]) == {"queue", "counts", "auto", "all"}


def test_index_and_static_are_served(client):
    assert "smoltask" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200

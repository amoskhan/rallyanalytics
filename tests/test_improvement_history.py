"""Every improvement run is logged, and the last kept one can be undone (the HTTP API seam)."""
from .test_improvement import low_clears, run, strokes_rules_version
from .test_recheck_strokes import use_cutoffs


def history(client):
    return client.get("/api/improvement/history").json()["entries"]


def can_undo(client):
    return client.get("/api/improvement/history").json()["can_undo"]


def ready(client, data_dir, name="a"):
    low_clears(client, data_dir, "teaching", 30, name=f"{name}t")
    low_clears(client, data_dir, "test", 30, name=f"{name}s")


def test_there_is_no_history_before_any_run(client, data_dir):
    assert history(client) == []


def test_a_kept_run_is_logged_with_its_result(client, data_dir):
    ready(client, data_dir)
    run(client)
    client.post("/api/improvement/keep")

    [entry] = history(client)

    assert entry["outcome"] == "kept"
    assert entry["version"] == 2
    assert entry["accuracy"] == {"before": 0.0, "after": 1.0}
    assert entry["teaching"] == {"rallies": 30, "shots": 30}
    assert entry["test"] == {"rallies": 30, "shots": 30}
    assert entry["date"]


def test_a_discarded_run_is_logged_too(client, data_dir):
    ready(client, data_dir)
    run(client)
    client.post("/api/improvement/discard")

    assert [e["outcome"] for e in history(client)] == ["discarded"]


def test_a_run_waiting_for_a_decision_shows_as_pending(client, data_dir):
    ready(client, data_dir)
    run(client)

    assert [e["outcome"] for e in history(client)] == ["pending"]


def test_a_run_overtaken_by_a_newer_run_shows_as_replaced(client, data_dir):
    ready(client, data_dir)
    run(client)
    run(client)

    assert [e["outcome"] for e in history(client)] == ["pending", "replaced"]


def test_a_run_without_enough_checked_rallies_is_not_logged(client, data_dir):
    low_clears(client, data_dir, "test", 5)
    run(client)

    assert history(client) == []


def test_undo_goes_back_to_the_stroke_rules_before_the_last_keep(client, data_dir):
    ready(client, data_dir)
    run(client)
    client.post("/api/improvement/keep")

    r = client.post("/api/improvement/undo")

    assert r.json()["version"] == 1
    assert strokes_rules_version(client, data_dir) == (1, "lob")


def test_undo_is_logged(client, data_dir):
    ready(client, data_dir)
    run(client)
    client.post("/api/improvement/keep")
    client.post("/api/improvement/undo")

    newest = history(client)[0]
    assert newest["outcome"] == "undone"
    assert (newest["from_version"], newest["version"]) == (2, 1)


def test_undo_is_refused_with_the_original_stroke_rules(client, data_dir):
    assert client.post("/api/improvement/undo").status_code == 409


def test_undoing_twice_steps_back_twice(client, data_dir):
    ready(client, data_dir)
    run(client)
    client.post("/api/improvement/keep")
    low_clears(client, data_dir, "teaching", 40, label="lob", name="back")   # now teaches lob again
    run(client)
    assert client.post("/api/improvement/keep").json()["version"] == 3

    assert client.post("/api/improvement/undo").json()["version"] == 2
    assert client.post("/api/improvement/undo").json()["version"] == 1
    assert client.post("/api/improvement/undo").status_code == 409


def test_undo_is_only_offered_while_a_kept_improvement_is_in_use(client, data_dir):
    assert can_undo(client) is False
    ready(client, data_dir)
    run(client)
    client.post("/api/improvement/keep")
    assert can_undo(client) is True

    client.post("/api/improvement/undo")

    assert can_undo(client) is False


def test_a_result_waiting_when_undo_is_pressed_can_no_longer_be_kept(client, data_dir):
    ready(client, data_dir)
    run(client)
    client.post("/api/improvement/keep")
    run(client)                              # a new result, based on version 2

    client.post("/api/improvement/undo")     # back to version 1

    assert client.post("/api/improvement/keep").status_code == 409


def test_a_version_saved_before_undo_existed_can_still_be_undone(client, data_dir):
    use_cutoffs(data_dir, 2, overhead=0.85)   # an older store: its versions don't record what they replaced

    assert client.post("/api/improvement/undo").json()["version"] == 1

"""Re-check strokes: bring a Video's Strokes up to date with the current cut-offs (the HTTP API seam).

The sample Video's second Rally is a clear taken with the wrist just under the default overhead
height, so the default cut-offs call it a lob and an overhead cut-off of 0.85 calls it a clear.
"""
import json
import os

import pytest

from .samples import low_clear, save_video, serve_clear_lob_smash


def use_cutoffs(data_dir, version, **changes):
    """Make `changes` the current cut-offs, as keeping an improvement will."""
    from server.pipeline.strokes import DEFAULT_CUTOFFS
    store = {"current": version, "versions": [
        {"version": 1, "cutoffs": dict(DEFAULT_CUTOFFS), "created": 0},
        {"version": version, "cutoffs": {**DEFAULT_CUTOFFS, **changes}, "created": 1}]}
    with open(os.path.join(data_dir, "stroke_cutoffs.json"), "w", encoding="utf-8") as fh:
        json.dump(store, fh)


@pytest.fixture
def vid(data_dir):
    return save_video(data_dir, "sample-1", [serve_clear_lob_smash(), low_clear()])


def recheck(client, vid):
    return client.post(f"/api/videos/{vid}/recheck-strokes")


def app_strokes(client, vid):
    result = client.get(f"/api/videos/{vid}/result.json").json()
    return [[s["stroke"] for s in r["shot_metrics"]] for r in result["rallies"]]


def test_nothing_changes_when_the_cut_offs_are_the_same(client, vid):
    r = recheck(client, vid)

    assert r.status_code == 200
    assert r.json()["changed"] == 0
    assert app_strokes(client, vid) == [["long service", "clear", "lob", "smash"], ["lob"]]


def test_new_cut_offs_update_the_videos_strokes(client, data_dir, vid):
    use_cutoffs(data_dir, 2, overhead=0.85)

    r = recheck(client, vid)

    assert r.json()["changed"] == 1
    assert app_strokes(client, vid) == [["long service", "clear", "lob", "smash"], ["clear"]]


def test_the_reason_shown_for_a_stroke_is_updated_too(client, data_dir, vid):
    use_cutoffs(data_dir, 2, overhead=0.85)

    recheck(client, vid)

    shot = client.get(f"/api/videos/{vid}/result.json").json()["rallies"][1]["shot_metrics"][0]
    assert shot["contact"] == "overhead"
    assert "overhead" in shot["stroke_why"]


def test_the_video_remembers_which_cut_offs_its_strokes_came_from(client, data_dir, vid):
    use_cutoffs(data_dir, 2, overhead=0.85)

    assert recheck(client, vid).json()["cutoffs_version"] == 2
    result = client.get(f"/api/videos/{vid}/result.json").json()
    assert result["pipeline"]["analysis"]["stroke_cutoffs_version"] == 2


def test_corrections_are_never_overwritten(client, data_dir, vid):
    client.put(f"/api/videos/{vid}/review", json={"strokes": {"1:100": "drive", "0:160": "net shot"}})
    use_cutoffs(data_dir, 2, overhead=0.85)

    recheck(client, vid)

    assert client.get(f"/api/videos/{vid}/review").json()["strokes"] == {"1:100": "drive", "0:160": "net shot"}


def test_checked_rallies_are_never_changed(client, data_dir, vid):
    client.put(f"/api/videos/{vid}/rallies/1/checked")
    before = client.get(f"/api/videos/{vid}/review").json()["checked"]
    use_cutoffs(data_dir, 2, overhead=0.85)

    recheck(client, vid)

    assert client.get(f"/api/videos/{vid}/review").json()["checked"] == before
    assert before["1"]["strokes"] == {"1:100": "lob"}


def test_a_video_being_analysed_cannot_be_rechecked(client, data_dir, vid):
    with open(os.path.join(data_dir, "videos", vid, "status.json"), "w", encoding="utf-8") as fh:
        json.dump({"state": "analysing"}, fh)

    assert recheck(client, vid).status_code == 409


def test_a_video_without_a_result_cannot_be_rechecked(client, data_dir, vid):
    os.remove(os.path.join(data_dir, "videos", vid, "result.json"))

    assert recheck(client, vid).status_code == 404


def test_a_checked_rally_keeps_showing_the_strokes_that_were_confirmed(client, data_dir, vid):
    client.put(f"/api/videos/{vid}/rallies/1/checked")
    use_cutoffs(data_dir, 2, overhead=0.85)

    r = recheck(client, vid)

    assert app_strokes(client, vid)[1] == ["lob"]
    assert r.json()["changed"] == 0


def test_a_corrected_shot_is_not_counted_as_changed(client, data_dir, vid):
    client.put(f"/api/videos/{vid}/review", json={"strokes": {"1:100": "drive"}})
    use_cutoffs(data_dir, 2, overhead=0.85)

    assert recheck(client, vid).json()["changed"] == 0

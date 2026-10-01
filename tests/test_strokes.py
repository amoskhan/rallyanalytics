"""Stroke recognition from a saved Rally (the stroke module's seam)."""
from server.pipeline import strokes

from .samples import low_clear, save_video, serve_clear_lob_smash


def stroke_names(r, cutoffs=None):
    return [s["stroke"] for s in strokes.strokes_for_rally(r, cutoffs)]


def test_a_saved_rally_gets_its_strokes_with_the_default_cut_offs():
    assert stroke_names(serve_clear_lob_smash()) == ["long service", "clear", "lob", "smash"]


def test_each_stroke_comes_with_its_reason_contact_height_and_zones():
    lob = strokes.strokes_for_rally(serve_clear_lob_smash())[2]
    assert lob["contact"] == "underarm"
    assert lob["from_zone"] == "front"
    assert lob["to_zone"] == "rear"
    assert "underarm" in lob["why"]


def test_a_low_clear_is_called_a_lob_with_the_default_cut_offs():
    assert stroke_names(low_clear()) == ["lob"]


def test_lowering_the_overhead_cut_off_turns_the_low_clear_into_a_clear():
    cutoffs = {**strokes.DEFAULT_CUTOFFS, "overhead": 0.85}
    assert stroke_names(low_clear(), cutoffs) == ["clear"]


def test_cut_offs_left_out_keep_their_default_values():
    assert stroke_names(low_clear(), {"overhead": 0.85}) == ["clear"]
    assert stroke_names(serve_clear_lob_smash(), {"overhead": 0.85}) == ["long service", "clear", "lob", "smash"]


def test_changing_the_cut_offs_does_not_change_the_defaults():
    strokes.strokes_for_rally(low_clear(), {**strokes.DEFAULT_CUTOFFS, "overhead": 0.85})
    assert stroke_names(low_clear()) == ["lob"]


def test_re_working_out_a_saved_video_gives_the_strokes_it_was_saved_with(client, data_dir):
    vid = save_video(data_dir, "sample-1", [serve_clear_lob_smash(), low_clear()])

    result = client.get(f"/api/videos/{vid}/result.json").json()

    for r in result["rallies"]:
        assert stroke_names(r) == [s["stroke"] for s in r["shot_metrics"]]

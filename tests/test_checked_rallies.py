"""A Labeller checks a Rally: every Shot's Stroke is confirmed as it shows (the HTTP API seam).

Shots are keyed "<rally>:<contact frame>", the same key Corrections use. In the samples the
first Rally's Contacts are at frames 100, 130, 160 and 190; the second Rally's at frame 100.
"""
import pytest

from .samples import low_clear, save_video, serve_clear_lob_smash


@pytest.fixture
def vid(data_dir):
    # The Labeller has already corrected the second Rally's lob to a clear.
    return save_video(data_dir, "sample-1", [serve_clear_lob_smash(), low_clear()],
                      review={"strokes": {"1:100": "clear"}})


def check(client, vid, rally):
    return client.put(f"/api/videos/{vid}/rallies/{rally}/checked")


def checked(client, vid):
    return client.get(f"/api/videos/{vid}/review").json().get("checked", {})


def test_checking_a_rally_confirms_every_shot_as_it_shows(client, vid):
    assert check(client, vid, 0).status_code == 200

    assert checked(client, vid)["0"]["strokes"] == {
        "0:100": "long service", "0:130": "clear", "0:160": "lob", "0:190": "smash"}


def test_checking_a_rally_confirms_the_labellers_corrections(client, vid):
    check(client, vid, 1)

    assert checked(client, vid)["1"]["strokes"] == {"1:100": "clear"}


def test_a_shot_set_to_unknown_is_checked_as_unknown(client, vid):
    client.put(f"/api/videos/{vid}/review", json={"strokes": {"1:100": "unknown"}})
    check(client, vid, 1)

    assert checked(client, vid)["1"]["strokes"] == {"1:100": "unknown"}


def test_only_the_rallies_checked_are_checked(client, vid):
    check(client, vid, 0)

    assert list(checked(client, vid)) == ["0"]


def test_unchecking_a_rally(client, vid):
    check(client, vid, 0)

    assert client.delete(f"/api/videos/{vid}/rallies/0/checked").status_code == 200
    assert checked(client, vid) == {}


def test_a_rally_that_does_not_exist_cannot_be_checked(client, vid):
    assert check(client, vid, 7).status_code == 404


def test_correcting_a_shot_in_a_checked_rally_keeps_it_checked_with_the_new_stroke(client, vid):
    check(client, vid, 0)

    client.put(f"/api/videos/{vid}/review", json={"strokes": {"1:100": "clear", "0:160": "net shot"}})

    assert checked(client, vid)["0"]["strokes"]["0:160"] == "net shot"


def test_undoing_a_correction_in_a_checked_rally_goes_back_to_the_apps_stroke(client, vid):
    client.put(f"/api/videos/{vid}/review", json={"strokes": {"1:100": "clear", "0:160": "net shot"}})
    check(client, vid, 0)

    client.put(f"/api/videos/{vid}/review", json={"strokes": {"1:100": "clear"}})

    assert checked(client, vid)["0"]["strokes"]["0:160"] == "lob"


def test_correcting_a_shot_does_not_check_its_rally(client, vid):
    client.put(f"/api/videos/{vid}/review", json={"strokes": {"0:160": "net shot"}})

    assert checked(client, vid) == {}


def test_re_analysing_a_video_with_checked_rallies_is_refused_without_permission(client, vid):
    check(client, vid, 0)

    r = client.post(f"/api/videos/{vid}/retry")

    assert r.status_code == 409
    assert "1 Checked rally" in r.json()["detail"]
    assert list(checked(client, vid)) == ["0"]


def test_re_analysing_with_new_court_corners_is_refused_too(client, vid):
    check(client, vid, 0)

    r = client.post(f"/api/videos/{vid}/analyse", json={"corners": [[0, 0], [9, 0], [9, 9], [0, 9]]})

    assert r.status_code == 409


def test_re_analysing_with_permission_clears_the_checked_rallies(client, vid):
    check(client, vid, 0)

    r = client.post(f"/api/videos/{vid}/retry?clear_checked=true")

    assert r.status_code == 200
    assert checked(client, vid) == {}


def test_re_analysing_a_video_with_no_checked_rallies_needs_no_permission(client, vid):
    assert client.post(f"/api/videos/{vid}/retry").status_code == 200


def test_old_stroke_names_are_checked_under_their_current_name(client, data_dir):
    vid = save_video(data_dir, "old-names", [serve_clear_lob_smash()],
                     review={"strokes": {"0:160": "lift", "0:100": "long serve"}})

    check(client, vid, 0)

    strokes = checked(client, vid)["0"]["strokes"]
    assert strokes["0:160"] == "lob"
    assert strokes["0:100"] == "long service"


def test_corrections_still_save_when_a_checked_rally_is_no_longer_in_the_result(client, data_dir):
    vid = save_video(data_dir, "gone", [serve_clear_lob_smash()],
                     review={"checked": {"5": {"checked_at": 0, "strokes": {"5:100": "lob"}}}})

    r = client.put(f"/api/videos/{vid}/review", json={"strokes": {"5:100": "clear"}})

    assert r.status_code == 200
    assert client.get(f"/api/videos/{vid}/review").json()["strokes"] == {"5:100": "clear"}

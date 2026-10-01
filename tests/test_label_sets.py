"""Each Video's Checked rallies go to the teaching set or the test set, for good (the HTTP API seam).

A Video is put in a set when its first Rally is checked; about 1 in 5 Videos go to test.
"""
import json
import os

from .samples import low_clear, save_video, serve_clear_lob_smash


def check(client, vid, rally):
    assert client.put(f"/api/videos/{vid}/rallies/{rally}/checked").status_code == 200


def set_of(client, vid):
    return client.get(f"/api/videos/{vid}/review").json().get("set")


def summary(client):
    return client.get("/api/labelling").json()


def two_rally_video(data_dir, vid, review=None):
    return save_video(data_dir, vid, [serve_clear_lob_smash(), low_clear()], review=review)


def video_in(client, data_dir, wanted):
    """A Video that lands in the `wanted` set when checked (the set depends on the id)."""
    for n in range(100):
        vid = two_rally_video(data_dir, f"{wanted}-{n}")
        check(client, vid, 0)
        if set_of(client, vid) == wanted:
            return vid
        client.delete(f"/api/videos/{vid}/rallies/0/checked")
    raise AssertionError(f"no id landed in {wanted}")


def test_a_video_has_no_set_until_a_rally_is_checked(client, data_dir):
    vid = two_rally_video(data_dir, "v1")

    assert set_of(client, vid) is None


def test_checking_the_first_rally_puts_the_video_in_a_set(client, data_dir):
    vid = two_rally_video(data_dir, "v1")

    check(client, vid, 0)

    assert set_of(client, vid) in ("teaching", "test")


def test_about_one_in_five_videos_go_to_the_test_set(client, data_dir):
    sets = []
    for n in range(200):
        vid = save_video(data_dir, f"many-{n}", [low_clear()])
        check(client, vid, 0)
        sets.append(set_of(client, vid))

    assert 0.12 <= sets.count("test") / len(sets) <= 0.28


def test_a_videos_set_never_changes_after_unchecking_and_rechecking(client, data_dir):
    vid = two_rally_video(data_dir, "v1")
    check(client, vid, 0)
    first = set_of(client, vid)

    client.delete(f"/api/videos/{vid}/rallies/0/checked")
    check(client, vid, 1)

    assert set_of(client, vid) == first


def test_a_videos_stored_set_wins_over_the_rule(client, data_dir):
    # Saved before a change to the assignment rule: whatever the rule says now, it stays.
    vid = video_in(client, data_dir, "teaching")
    path = os.path.join(data_dir, "videos", vid, "review.json")
    with open(path, encoding="utf-8") as fh:
        review = json.load(fh)
    review["set"] = "test"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(review, fh)

    check(client, vid, 1)

    assert set_of(client, vid) == "test"


def test_re_analysing_keeps_the_videos_set(client, data_dir):
    vid = two_rally_video(data_dir, "v1")
    check(client, vid, 0)
    first = set_of(client, vid)

    client.post(f"/api/videos/{vid}/retry?clear_checked=true")

    assert set_of(client, vid) == first


def test_the_summary_counts_checked_rallies_and_shots_per_set(client, data_dir):
    teach = video_in(client, data_dir, "teaching")
    check(client, teach, 1)                      # 4 Shots + 1 Shot
    test = video_in(client, data_dir, "test")    # 4 Shots

    s = summary(client)

    assert s["teaching"] == {"videos": 1, "rallies": 2, "shots": 5}
    assert s["test"] == {"videos": 1, "rallies": 1, "shots": 4}


def test_unknown_shots_are_left_out_of_the_counts(client, data_dir):
    vid = video_in(client, data_dir, "teaching")
    client.put(f"/api/videos/{vid}/review", json={"strokes": {"0:160": "unknown"}})

    assert summary(client)["teaching"]["shots"] == 3


def test_videos_with_no_checked_rallies_are_not_counted(client, data_dir):
    vid = video_in(client, data_dir, "teaching")
    client.delete(f"/api/videos/{vid}/rallies/0/checked")
    two_rally_video(data_dir, "never-checked")

    assert summary(client)["teaching"] == {"videos": 0, "rallies": 0, "shots": 0}
    assert summary(client)["test"] == {"videos": 0, "rallies": 0, "shots": 0}


def test_all_of_a_videos_checked_rallies_are_in_the_same_set(client, data_dir):
    vid = two_rally_video(data_dir, "v1")
    check(client, vid, 0)
    check(client, vid, 1)

    s = summary(client)

    assert sorted(s[set_of(client, vid)].values()) == [1, 2, 5]   # 1 video, 2 rallies, 5 shots
    assert set(s["teaching"].values()) == {0} or set(s["test"].values()) == {0}


def test_checking_a_rally_says_which_set_the_video_is_in(client, data_dir):
    vid = two_rally_video(data_dir, "v1")

    r = client.put(f"/api/videos/{vid}/rallies/0/checked").json()

    assert r["set"] == set_of(client, vid)


def test_a_damaged_review_does_not_break_the_summary(client, data_dir):
    vid = video_in(client, data_dir, "teaching")
    broken = two_rally_video(data_dir, "broken")
    with open(os.path.join(data_dir, "videos", broken, "review.json"), "w", encoding="utf-8") as fh:
        fh.write('{"checked": {"0"')

    assert summary(client)["teaching"] == {"videos": 1, "rallies": 1, "shots": 4}

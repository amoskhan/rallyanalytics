"""Run improvement: tune the cut-offs on the teaching set, score on the test set, keep or discard
(the HTTP API seam).

The workhorse sample is a clear taken with the wrist just under the default overhead height:
the default cut-offs call it a lob, a lower overhead cut-off calls it a clear. Labellers who
correct those to "clear" give the improvement something to fix.
"""
import os
import shutil

from .samples import low_clear, save_video, serve_clear_lob_smash
from .test_recheck_strokes import use_cutoffs


def labelled_video(client, data_dir, wanted, rallies, corrections=None, name="v"):
    """A Video in the `wanted` set (teaching or test), with `corrections` made and every Rally checked."""
    for n in range(200):
        vid = save_video(data_dir, f"{name}-{wanted}-{n}", rallies, review={"strokes": corrections or {}})
        r = client.put(f"/api/videos/{vid}/rallies/0/checked").json()
        if r["set"] == wanted:
            for i in range(1, len(rallies)):
                client.put(f"/api/videos/{vid}/rallies/{i}/checked")
            return vid
        shutil.rmtree(os.path.join(data_dir, "videos", vid))
    raise AssertionError(f"no id landed in {wanted}")


def low_clears(client, data_dir, wanted, n, label="clear", name="lc"):
    """n Rallies of one low clear each, labelled `label` by the Labeller."""
    corrections = {f"{i}:100": label for i in range(n)} if label != "lob" else {}
    return labelled_video(client, data_dir, wanted, [low_clear() for _ in range(n)], corrections, name)


def run(client):
    return client.post("/api/improvement").json()


def strokes_rules_version(client, data_dir):
    """The cut-off version in use, seen through Re-check strokes on an unlabelled Video."""
    vid = save_video(data_dir, "probe", [low_clear()])
    r = client.post(f"/api/videos/{vid}/recheck-strokes").json()
    stroke = client.get(f"/api/videos/{vid}/result.json").json()["rallies"][0]["shot_metrics"][0]["stroke"]
    shutil.rmtree(os.path.join(data_dir, "videos", vid))
    return r["cutoffs_version"], stroke


def test_with_too_few_checked_test_shots_there_is_no_report(client, data_dir):
    low_clears(client, data_dir, "teaching", 10)
    low_clears(client, data_dir, "test", 5)

    r = run(client)

    assert r["status"] == "not_enough"
    assert r["test_shots"] == 5


def test_an_improvement_fixes_clears_called_lobs_and_reports_the_gain(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    low_clears(client, data_dir, "test", 30)

    r = run(client)

    assert r["status"] == "ready"
    assert r["accuracy"] == {"before": 0.0, "after": 1.0}
    assert r["test_shots"] == 30
    assert r["strokes"]["clear"] == {"shots": 30, "before": 0.0, "after": 1.0}
    assert {"label": "clear", "called": "lob", "before": 30, "after": 0} in r["mixups"]
    assert r["cutoffs"]["overhead"]["before"] == 0.95
    assert r["cutoffs"]["overhead"]["after"] <= 0.9
    assert r["warning"] is None


def test_unknown_shots_are_left_out_of_teaching_and_scoring(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    low_clears(client, data_dir, "test", 30)
    low_clears(client, data_dir, "test", 10, label="unknown", name="unk")

    assert run(client)["test_shots"] == 30


def test_the_before_score_depends_only_on_the_test_set(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    low_clears(client, data_dir, "test", 30)
    before = run(client)["accuracy"]["before"]

    # More teaching data, labelled the opposite way, changes the tuning but not the before score.
    low_clears(client, data_dir, "teaching", 40, label="lob", name="more")

    assert run(client)["accuracy"]["before"] == before


def test_test_shots_are_never_learned_from(client, data_dir):
    # Teaching says these are lobs (the defaults agree); only the test set says clear.
    low_clears(client, data_dir, "teaching", 30, label="lob")
    low_clears(client, data_dir, "test", 30, label="clear")

    r = run(client)

    assert "overhead" not in r["cutoffs"]   # only cut-offs that changed are listed
    assert r["accuracy"] == {"before": 0.0, "after": 0.0}


def test_a_change_that_makes_the_test_score_worse_comes_with_a_warning(client, data_dir):
    low_clears(client, data_dir, "teaching", 30, label="clear")
    low_clears(client, data_dir, "test", 30, label="lob")

    r = run(client)

    assert r["accuracy"] == {"before": 1.0, "after": 0.0}
    assert r["warning"]


def test_the_result_waits_until_kept_or_discarded(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    low_clears(client, data_dir, "test", 30)
    run(client)

    assert client.get("/api/improvement").json()["accuracy"] == {"before": 0.0, "after": 1.0}
    assert strokes_rules_version(client, data_dir) == (1, "lob")


def test_discarding_leaves_the_cut_offs_as_they_were(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    low_clears(client, data_dir, "test", 30)
    run(client)

    assert client.post("/api/improvement/discard").status_code == 200

    assert client.get("/api/improvement").json() is None
    assert strokes_rules_version(client, data_dir) == (1, "lob")


def test_keeping_makes_the_tuned_cut_offs_the_ones_in_use(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    low_clears(client, data_dir, "test", 30)
    run(client)

    r = client.post("/api/improvement/keep")

    assert r.json()["version"] == 2
    assert client.get("/api/improvement").json() is None
    assert strokes_rules_version(client, data_dir) == (2, "clear")


def test_there_is_nothing_to_keep_without_a_run(client, data_dir):
    assert client.post("/api/improvement/keep").status_code == 409


def test_a_result_from_older_cut_offs_cannot_be_kept(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    low_clears(client, data_dir, "test", 30)
    run(client)
    use_cutoffs(data_dir, 2, smash_kmh=60)   # the cut-offs changed after that run

    assert client.post("/api/improvement/keep").status_code == 409


def test_other_strokes_survive_an_improvement(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)
    labelled_video(client, data_dir, "teaching", [serve_clear_lob_smash() for _ in range(5)], name="mix")
    low_clears(client, data_dir, "test", 30)
    labelled_video(client, data_dir, "test", [serve_clear_lob_smash() for _ in range(5)], name="mix")

    r = run(client)

    assert r["accuracy"]["after"] == 1.0
    assert r["strokes"]["smash"] == {"shots": 5, "before": 1.0, "after": 1.0}


def test_a_stroke_that_gets_clearly_worse_comes_with_a_warning_even_when_overall_improves(client, data_dir):
    low_clears(client, data_dir, "teaching", 30)                       # teaches: these are clears
    low_clears(client, data_dir, "test", 30)                           # clears: 0% -> 100%
    low_clears(client, data_dir, "test", 10, label="lob", name="lobs")  # lobs: 100% -> 0%

    r = run(client)

    assert r["accuracy"] == {"before": 0.25, "after": 0.75}
    assert r["strokes"]["lob"] == {"shots": 10, "before": 1.0, "after": 0.0}
    assert "lob" in r["warning"]

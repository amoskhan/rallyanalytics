"""Checked rallies: a Labeller's confirmation of every Shot's Stroke in a Rally.

Stored in the Video's review.json next to the Corrections, as
{"checked": {"<rally>": {"checked_at": t, "strokes": {"<rally>:<contact frame>": stroke}}}}.
The Strokes are a snapshot taken at checking: Re-check strokes never changes them, only the
Labeller's own Corrections do.

A Video's Checked rallies all belong to one set, "teaching" or "test", stored in the review as
"set" when its first Rally is checked and never changed after, so test scores stay honest.
"""
import hashlib
import os
import time

from . import job
from .strokes import LEGACY


def _shot_keys(rally):
    return [f"{rally['i']}:{h['f']}" for h in rally["hits"]]


def _strokes_as_shown(rally, corrections):
    """Each Shot's Stroke as the review shows it: the Correction, else the app's Stroke."""
    shown = {key: corrections.get(key) or (sm.get("stroke") or "unknown")
             for key, sm in zip(_shot_keys(rally), rally["shot_metrics"])}
    return {key: LEGACY.get(st, st) for key, st in shown.items()}   # names from before ShuttleSet


TEST_SHARE = 5   # 1 in 5 Videos go to the test set


def _set_for(vid):
    """The set a Video joins, from its id alone, so the same Video always lands the same way."""
    return "test" if int(hashlib.sha1(vid.encode()).hexdigest(), 16) % TEST_SHARE == 0 else "teaching"


def _rally(vid, i):
    result = job.read_json(vid, "result.json") or {}
    return next((r for r in result.get("rallies", []) if r["i"] == i), None)


def check(vid, i):
    """Mark Rally i checked. Returns the Checked rally, or None if there is no such Rally."""
    rally = _rally(vid, i)
    if rally is None:
        return None
    with job.review_lock(vid):
        review = job.read_json(vid, "review.json", {}) or {}
        entry = {"checked_at": time.time(), "strokes": _strokes_as_shown(rally, review.get("strokes", {}))}
        review.setdefault("checked", {})[str(i)] = entry
        review.setdefault("set", _set_for(vid))
        job.write_json(vid, "review.json", review)
    return entry


def uncheck(vid, i):
    with job.review_lock(vid):
        review = job.read_json(vid, "review.json", {}) or {}
        if review.get("checked", {}).pop(str(i), None) is not None:
            job.write_json(vid, "review.json", review)


def follow_corrections(vid, review, old_corrections):
    """Keep Checked rallies in step with the Labeller's Corrections: a Shot whose Correction
    was added, changed or removed takes its new Stroke as shown. Updates `review` in place;
    the caller holds the review lock."""
    new = review.get("strokes", {})
    changed = {k for k in set(old_corrections) | set(new) if old_corrections.get(k) != new.get(k)}
    for i, entry in review.get("checked", {}).items():
        touched = changed & set(entry["strokes"])
        rally = _rally(vid, int(i)) if touched else None
        if rally:   # a Rally gone from the result can't be re-read; leave its snapshot alone
            shown = _strokes_as_shown(rally, new)
            entry["strokes"].update({k: shown[k] for k in touched if k in shown})


def count(vid):
    return len((job.read_json(vid, "review.json", {}) or {}).get("checked", {}))


def clear(vid):
    with job.review_lock(vid):
        review = job.read_json(vid, "review.json", {}) or {}
        if review.pop("checked", None):
            job.write_json(vid, "review.json", review)


def summary():
    """Checked rallies and Shots in each set, across every Video. Unknown Shots don't count:
    they're left out of teaching and scoring."""
    out = {name: {"videos": 0, "rallies": 0, "shots": 0} for name in ("teaching", "test")}
    for vid in os.listdir(job.DATA):
        try:
            with job.review_lock(vid):
                review = job.read_json(vid, "review.json", {}) or {}
        except ValueError:   # a damaged review.json: leave that Video out rather than fail
            continue
        checked = review.get("checked", {})
        if not checked or review.get("set") not in out:
            continue
        counts = out[review["set"]]
        counts["videos"] += 1
        counts["rallies"] += len(checked)
        counts["shots"] += sum(st != "unknown" for entry in checked.values() for st in entry["strokes"].values())
    return out

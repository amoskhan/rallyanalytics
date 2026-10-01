"""Run improvement: tune the stroke rules' cut-offs on the teaching set, score them on the test set.

Only Checked rallies are used, and Unknown Shots are left out. The result waits as a pending
improvement until a Labeller keeps it (it becomes the new current cut-offs) or discards it.
See docs/training-process.md and ADR 0001.
"""
import os
import threading
import time
import uuid
from collections import Counter

from . import cutoffs as cutoffs_mod, labels as labels_mod, paths, storage
from .strokes import strokes_for_rally

MIN_TEST_SHOTS = 30      # below this many Checked test Shots a score means nothing
MIN_STROKE_SHOTS = 8     # a Stroke needs this many test Shots before a drop in it counts
WORSE_BY = 0.10          # ... and a drop of this much (10 points of accuracy) is worth a warning

# Where tuning looks for each cut-off, kept to badminton-sensible values.
RANGES = {
    "front_m": [round(1.5 + 0.1 * i, 2) for i in range(21)],      # 1.5 - 3.5 m from the net
    "rear_m": [round(3.5 + 0.1 * i, 2) for i in range(21)],       # 3.5 - 5.5 m
    "overhead": [round(0.7 + 0.05 * i, 2) for i in range(11)],    # 0.70 - 1.20 of hips-to-nose
    "underarm": [round(0.1 + 0.05 * i, 2) for i in range(11)],    # 0.10 - 0.60
    "smash_kmh": [35 + 2.5 * i for i in range(19)],               # 35 - 80 km/h
    "wrist_smash_kmh": [25 + 2.5 * i for i in range(13)],         # 25 - 55 km/h
}
PENDING = os.path.join(paths.DATA_ROOT, "stroke_improvement_pending.json")
# Every run that produced a report, with what became of it (pending, kept, discarded, replaced),
# and every undo. Oldest first on disk, newest first when read.
HISTORY = os.path.join(paths.DATA_ROOT, "stroke_improvement_history.json")
_lock = threading.Lock()   # the pending result and the history change one at a time


def _predict(rallies, cutoffs):
    """[(label, stroke the rules call it)] for every labelled Shot in `rallies`."""
    pairs = []
    for rally, labels in rallies:
        called = strokes_for_rally(rally, cutoffs)
        pairs += [(label, called[k]["stroke"]) for k, label in labels.items()]
    return pairs


def _accuracy(pairs):
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else 0.0


def _valid(c):
    return c["front_m"] < c["rear_m"] and c["underarm"] < c["overhead"] and c["wrist_smash_kmh"] < c["smash_kmh"]


def tune(rallies, start):
    """Cut-offs that get the most teaching Shots right: one cut-off at a time over its range,
    repeated until nothing improves. A tie keeps the current value, so nothing moves without
    a reason in the labels."""
    best, best_score = dict(start), _accuracy(_predict(rallies, start))
    for _ in range(5):
        improved = False
        for name, values in RANGES.items():
            for v in values:
                trial = {**best, name: v}
                if not _valid(trial):
                    continue
                score = _accuracy(_predict(rallies, trial))
                if score > best_score:
                    best, best_score, improved = trial, score, True
        if not improved:
            break
    return best


def _report(before, after, old, new):
    strokes = {}
    for label in sorted({a for a, _ in before}):
        b = [p for p in before if p[0] == label]
        a = [p for p in after if p[0] == label]
        strokes[label] = {"shots": len(b), "before": round(_accuracy(b), 3), "after": round(_accuracy(a), 3)}
    mb = Counter(p for p in before if p[0] != p[1])
    ma = Counter(p for p in after if p[0] != p[1])
    top = sorted(set(mb) | set(ma), key=lambda p: -max(mb[p], ma[p]))[:8]
    acc = {"before": round(_accuracy(before), 3), "after": round(_accuracy(after), 3)}
    worse = [s for s, v in strokes.items()
             if v["shots"] >= MIN_STROKE_SHOTS and round(v["before"] - v["after"], 3) >= WORSE_BY]
    problems = []
    if acc["after"] < acc["before"]:
        problems.append("Overall accuracy on the test set went down.")
    if worse:
        problems.append("Got clearly worse on: " + ", ".join(worse) + ".")
    warning = " ".join(problems) or None
    return {
        "accuracy": acc, "test_shots": len(before), "strokes": strokes,
        "mixups": [{"label": a, "called": b, "before": mb[(a, b)], "after": ma[(a, b)]} for a, b in top],
        "cutoffs": {k: {"before": old[k], "after": new[k]} for k in old if old[k] != new[k]},
        "warning": warning,
    }


def run():
    """Tune on the teaching set and score on the test set. Saves the result as pending."""
    data = [(which, r, l) for _, which, r, l in labels_mod.checked_rallies() if l]
    teaching = [(r, l) for s, r, l in data if s == "teaching"]
    test = [(r, l) for s, r, l in data if s == "test"]
    test_shots = sum(len(l) for _, l in test)
    teaching_shots = sum(len(l) for _, l in teaching)
    if test_shots < MIN_TEST_SHOTS or not teaching_shots:
        return {"status": "not_enough", "test_shots": test_shots, "teaching_shots": teaching_shots,
                "needed": MIN_TEST_SHOTS}
    version, current = cutoffs_mod.current()
    tuned = tune(teaching, current)
    report = {"status": "ready", "base_version": version, "teaching_shots": teaching_shots, "created": time.time(),
              **_report(_predict(test, current), _predict(test, tuned), current, tuned)}
    with _lock:
        earlier = _read_pending()
        if earlier:
            _set_outcome(earlier.get("run_id"), "replaced")
        run_id = _log({"outcome": "pending", "base_version": version, "accuracy": report["accuracy"],
                       "teaching": {"rallies": len(teaching), "shots": teaching_shots},
                       "test": {"rallies": len(test), "shots": test_shots}})
        storage.save_json(PENDING, {**report, "tuned": tuned, "run_id": run_id}, indent=1)
    return report


def pending():
    """The improvement waiting to be kept or discarded, or None."""
    p = _read_pending()
    if p:
        p.pop("tuned", None)
        p.pop("run_id", None)
    return p


def keep():
    """Make the pending cut-offs the current ones. Returns the new version. Raises LookupError
    when there is nothing to keep, ValueError when the cut-offs changed since the run."""
    with _lock:
        p = _read_pending()
        if not p:
            raise LookupError("There is no improvement waiting to be kept. Run one first.")
        if p["base_version"] != cutoffs_mod.current()[0]:
            raise ValueError("The stroke rules changed since this improvement was run. Run it again.")
        version = cutoffs_mod.add_version(p["tuned"])
        storage.remove(PENDING)
        _set_outcome(p.get("run_id"), "kept", version=version)
    return version


def discard():
    with _lock:
        p = _read_pending()
        storage.remove(PENDING)
        if p:
            _set_outcome(p.get("run_id"), "discarded")


def undo():
    """Go back to the stroke rules in use before the last Keep. Returns the version now in use.
    Raises LookupError when the original rules are in use."""
    with _lock:
        undone, now = cutoffs_mod.undo()
        _log({"outcome": "undone", "from_version": undone, "version": now})
    return now


def history():
    """Every logged run and undo, newest first, and whether Undo has anything to go back to."""
    return {"entries": list(reversed(_read_history())), "can_undo": cutoffs_mod.can_undo()}


def _read_history():
    try:
        return storage.load_json(HISTORY, [])
    except ValueError:   # a damaged log: start a fresh one rather than fail
        return []


def _log(entry):
    """Add an entry to the history. Returns its id. The caller holds _lock."""
    log = _read_history()
    entry = {"id": uuid.uuid4().hex, "date": time.strftime("%Y-%m-%d %H:%M"), **entry}
    log.append(entry)
    storage.save_json(HISTORY, log, indent=1)
    return entry["id"]


def _set_outcome(run_id, outcome, **extra):
    """Record what became of a logged run. The caller holds _lock."""
    log = _read_history()
    for entry in log:
        if entry["id"] == run_id:
            entry.update(outcome=outcome, **extra)
            storage.save_json(HISTORY, log, indent=1)
            return


def _read_pending():
    try:
        return storage.load_json(PENDING)
    except ValueError:   # a damaged file is no result at all
        return None

"""The stroke rules' cut-offs, saved as numbered versions so an improvement can be kept or undone.

The file holds {"current": n, "versions": [{"version": n, "cutoffs": {...}, "created": t,
"previous": m}, ...]}, where "previous" is the version in use when this one was kept (what Undo
goes back to). Version 1 is the hand-set defaults in strokes.py, written the first time the
file is read.
"""
import os
import threading
import time

from . import storage
from .paths import DATA_ROOT
from .strokes import DEFAULT_CUTOFFS

PATH = os.path.join(DATA_ROOT, "stroke_cutoffs.json")
_lock = threading.Lock()   # one change to the store at a time


def _load():
    store = storage.load_json(PATH)
    if store is None:
        store = {"current": 1, "versions": [{"version": 1, "cutoffs": dict(DEFAULT_CUTOFFS), "created": time.time()}]}
        _save(store)
    return store


def _save(store):
    storage.save_json(PATH, store, indent=1)


def current():
    """(version, cutoffs) the analysis and Re-check strokes should use now."""
    store = _load()
    v = next(v for v in store["versions"] if v["version"] == store["current"])
    return v["version"], {**DEFAULT_CUTOFFS, **v["cutoffs"]}


def add_version(cutoffs):
    """Save `cutoffs` as a new version and make it the current one. Returns its number."""
    with _lock:
        store = _load()
        version = max(v["version"] for v in store["versions"]) + 1
        store["versions"].append({"version": version, "cutoffs": dict(cutoffs), "created": time.time(),
                                  "previous": store["current"]})
        store["current"] = version
        _save(store)
    return version


def _previous(v):
    # Versions saved before Undo existed don't record what they replaced: they followed in order.
    return v.get("previous", v["version"] - 1 if v["version"] > 1 else None)


def can_undo():
    store = _load()
    return _previous(next(v for v in store["versions"] if v["version"] == store["current"])) is not None


def undo():
    """Go back to the version that was in use before the current one was kept.
    Returns (version undone, version now in use). Raises LookupError at the original version."""
    with _lock:
        store = _load()
        cur = next(v for v in store["versions"] if v["version"] == store["current"])
        previous = _previous(cur)
        if previous is None:
            raise LookupError("These are the original stroke rules: there is nothing to undo.")
        store["current"] = previous
        _save(store)
    return cur["version"], previous

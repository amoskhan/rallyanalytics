"""The stroke rules' cut-offs, saved as numbered versions so an improvement can be kept or undone.

The file holds {"current": n, "versions": [{"version": n, "cutoffs": {...}, "created": t}, ...]}.
Version 1 is the hand-set defaults in strokes.py, written the first time the file is read.
"""
import json
import os
import time

from .paths import DATA_ROOT
from .strokes import DEFAULT_CUTOFFS

PATH = os.path.join(DATA_ROOT, "stroke_cutoffs.json")


def _load():
    if not os.path.exists(PATH):
        store = {"current": 1, "versions": [{"version": 1, "cutoffs": dict(DEFAULT_CUTOFFS), "created": time.time()}]}
        _save(store)
        return store
    with open(PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _save(store):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=1)
    os.replace(tmp, PATH)


def current():
    """(version, cutoffs) the analysis and Re-check strokes should use now."""
    store = _load()
    v = next(v for v in store["versions"] if v["version"] == store["current"])
    return v["version"], {**DEFAULT_CUTOFFS, **v["cutoffs"]}

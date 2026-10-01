"""Saving and removing the app's JSON files safely.

A save writes a temporary file and swaps it in, so a reader never sees half a file. On Windows
the swap (and a removal) fails while another thread has the file open for reading; that read
takes milliseconds, so try again briefly rather than lose the save.
"""
import json
import os
import time

import numpy as np


def _np_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _retry(action):
    for attempt in range(20):
        try:
            return action()
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.025)


def save_json(path, obj, **dump_kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, default=_np_default, **dump_kw)
    _retry(lambda: os.replace(tmp, path))


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def remove(path):
    """Remove a file if it's there."""
    def rm():
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    _retry(rm)

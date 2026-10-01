"""Hand-written sample Rallies and Videos for tests, in the shape analysis saves them.

Court positions are in metres from the near baseline: the net is at 6.70 m, the far
baseline at 13.40 m. The Strokes noted here are worked out by hand from the badminton,
not from the code.
"""
import json
import os
import time


def contact(side, court, contact_h, front_depth=None, serve=False):
    return {"side": side, "serve": serve, "court": court, "contact_h": contact_h, "front_depth": front_depth}


def shot(flight_s, kmh, arc_pct, distance_m=None, direction="straight"):
    return {"flight_s": flight_s, "avg_speed_kmh": kmh, "arc_pct": arc_pct,
            "distance_m": distance_m, "direction": direction}


def rally(contacts, shots, landing, strokes=None):
    """A saved Rally. `strokes` are the Strokes the analysis stored for each Shot."""
    for k, (c, s) in enumerate(zip(contacts, shots)):
        c.setdefault("f", 100 + 30 * k)
        s.setdefault("f", c["f"])
        if strokes:
            s["stroke"] = strokes[k]
    return {"hits": contacts, "shot_metrics": shots, "landing": {"court": landing}}


def serve_clear_lob_smash():
    """Long serve, far player clears from the back, near player lunges and lobs, far player smashes."""
    return rally(
        [contact("near", [2.0, 2.5], 0.4, front_depth=4.0, serve=True),
         contact("far", [3.0, 12.5], 1.3, front_depth=5.5),
         contact("near", [3.0, 3.0], 0.2, front_depth=2.0),
         contact("far", [2.0, 12.5], 1.4, front_depth=5.5)],
        [shot(1.3, 20, 40),
         shot(1.2, 25, 30),
         shot(1.3, 20, 45),
         shot(0.4, 80, 10, distance_m=9.0)],
        landing=[3.0, 2.0],
        strokes=["long service", "clear", "lob", "smash"])


def low_clear():
    """A clear taken from mid court with the wrist just under the default overhead height
    (0.9 of hips-to-nose): the default rules call it a lob."""
    return rally(
        [contact("near", [3.0, 4.0], 0.9, front_depth=2.6)],
        [shot(1.2, 25, 30)],
        landing=[3.0, 12.5],
        strokes=["lob"])


def save_video(data_dir, vid, rallies, name="sample.mp4"):
    """Write a Video folder holding just what a finished analysis leaves behind (no video file)."""
    d = os.path.join(data_dir, "videos", vid)
    os.makedirs(d, exist_ok=True)
    files = {"info.json": {"id": vid, "name": name, "created": time.time()},
             "status.json": {"state": "done", "stage": "Analysis complete", "progress": 1},
             "result.json": {"version": 2, "mode": "singles",
                             "rallies": [{**r, "i": i} for i, r in enumerate(rallies)]}}
    for fname, obj in files.items():
        with open(os.path.join(d, fname), "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
    return vid

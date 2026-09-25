"""Player detection, pose and tracking with Ultralytics YOLO26-pose + ByteTrack.

Keeps only people standing on (or just around) the court, so spectators, umpires and
line judges drop out. Each kept detection is labelled with the court half it stands in.
"""
import os

import numpy as np

from .court import Court

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODEL_DIR = os.path.join(ROOT, "models")
DEFAULT_MODEL = os.environ.get("RALLYBOOK_POSE_MODEL", "yolo26m-pose.pt")

# COCO keypoint indices used downstream.
L_WRIST, R_WRIST, L_ANKLE, R_ANKLE = 9, 10, 15, 16


def _foot_point(box, kps):
    """Ground contact point in pixels: mean of confident ankles, else bottom-centre of the box."""
    ank = [kps[i] for i in (L_ANKLE, R_ANKLE) if kps[i][2] > 0.4]
    if ank:
        return float(np.mean([a[0] for a in ank])), float(max(a[1] for a in ank))
    return (box[0] + box[2]) / 2, box[3]


def track(video_path, court: Court, n_frames, stride=1, imgsz=1280, on_progress=lambda frac: None):
    """Returns {frame: [player, ...]} where player = {id, side, box, foot, court, kps}."""
    from ultralytics import YOLO

    os.makedirs(MODEL_DIR, exist_ok=True)
    model = YOLO(os.path.join(MODEL_DIR, DEFAULT_MODEL) if os.path.exists(os.path.join(MODEL_DIR, DEFAULT_MODEL)) else DEFAULT_MODEL)
    out = {}
    results = model.track(source=video_path, stream=True, persist=True, tracker="bytetrack.yaml",
                          imgsz=imgsz, conf=0.25, vid_stride=stride, verbose=False)
    for n, r in enumerate(results):
        f = n * stride
        if n % 25 == 0:
            on_progress(min(f / max(n_frames, 1), 1.0))
        if r.boxes is None or len(r.boxes) == 0:
            continue
        boxes = r.boxes.xyxy.cpu().numpy()
        ids = r.boxes.id.cpu().numpy().astype(int) if r.boxes.id is not None else np.arange(len(boxes)) + 10_000
        confs = r.boxes.conf.cpu().numpy()
        kps_all = r.keypoints.data.cpu().numpy() if r.keypoints is not None else np.zeros((len(boxes), 17, 3))
        people = []
        for box, tid, conf, kps in zip(boxes, ids, confs, kps_all):
            foot = _foot_point(box, kps)
            cx, cy = court.to_court([foot])[0]
            if not court.on_or_near_court(cx, cy, margin=1.2):
                continue
            people.append({
                "id": int(tid), "side": Court.side_of(cy), "conf": round(float(conf), 3),
                "box": [round(float(v), 1) for v in box],
                "foot": [round(foot[0], 1), round(foot[1], 1)],
                "court": [round(float(cx), 3), round(float(cy), 3)],
                "kps": [[round(float(k[0]), 1), round(float(k[1]), 1), round(float(k[2]), 2)] for k in kps],
            })
        if people:
            out[f] = people
    on_progress(1.0)
    return out


def select_players(frames, mode):
    """Keep the most confident 1 (singles) or 2 (doubles) people per court half in each frame."""
    per_side = 1 if mode == "singles" else 2
    kept = {}
    for f, people in frames.items():
        sel = []
        for side in ("near", "far"):
            cands = sorted((p for p in people if p["side"] == side), key=lambda p: -p["conf"])
            sel += cands[:per_side]
        kept[f] = sel
    return kept


def guess_mode(frames):
    """Singles or doubles, from how many people usually stand in each half."""
    counts = [max(sum(p["side"] == s for p in ps) for s in ("near", "far")) for ps in frames.values()]
    if not counts:
        return "singles"
    return "doubles" if np.median(counts) >= 2 else "singles"

"""Shuttle tracking with TrackNetV3 (third_party/TrackNetV3), run as a subprocess.

TrackNetV3 outputs one row per frame: Frame, Visibility, X, Y (pixels in the source video).
"""
import os
import re
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRACKNET_DIR = os.path.join(ROOT, "third_party", "TrackNetV3")
CKPT_DIR = os.path.join(ROOT, "models", "tracknetv3")
RUNNER = os.path.join(os.path.dirname(__file__), "_tracknet_runner.py")
BATCH = 8

TOTAL = re.compile(r"(\d+)/(\d+)")     # tqdm with a known total: "12/40"
COUNT = re.compile(r"(\d+)it\b")       # tqdm without a total (video stream): "12it"


def weights_present():
    return all(os.path.exists(os.path.join(CKPT_DIR, f)) for f in ("TrackNet_best.pt", "InpaintNet_best.pt"))


def csv_path(out_dir):
    return os.path.join(out_dir, "video_ball.csv")


def track(video_path, out_dir, n_frames, on_progress=lambda frac: None):
    """Run TrackNetV3 on a video (or reuse a previous run). Returns a DataFrame indexed by frame: v, x, y."""
    out_csv = csv_path(out_dir)
    if os.path.exists(out_csv) and os.path.getmtime(out_csv) > os.path.getmtime(video_path):
        on_progress(1.0)
        return _read(out_csv)
    if not weights_present():
        raise RuntimeError(f"TrackNetV3 weights missing in {CKPT_DIR}. Run setup.ps1.")
    os.makedirs(out_dir, exist_ok=True)
    video = os.path.abspath(video_path).replace("\\", "/")   # predict.py splits the name on "/"
    cmd = [sys.executable, "-u", RUNNER,
           "--video_file", video,
           "--tracknet_file", os.path.join(CKPT_DIR, "TrackNet_best.pt"),
           "--inpaintnet_file", os.path.join(CKPT_DIR, "InpaintNet_best.pt"),
           "--save_dir", os.path.abspath(out_dir),
           "--large_video", "--batch_size", str(BATCH)]
    proc = subprocess.Popen(cmd, cwd=TRACKNET_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    # Pass 1 (tracking, streamed, no total) is ~90% of the time; pass 2 (inpainting) has a total.
    tail, buf = [], b""
    while True:
        ch = proc.stdout.read(1)
        if not ch:
            break
        if ch not in (b"\r", b"\n"):
            buf += ch
            continue
        line = buf.decode("utf-8", "replace"); buf = b""
        if not line.strip():
            continue
        tail = (tail + [line])[-30:]
        if m := TOTAL.search(line):
            done, total = int(m.group(1)), int(m.group(2))
            on_progress(0.9 + 0.1 * done / max(total, 1))
        elif m := COUNT.search(line):
            on_progress(min(0.9, 0.9 * int(m.group(1)) * BATCH / max(n_frames, 1)))
    if proc.wait() != 0:
        raise RuntimeError("TrackNetV3 failed:\n" + "\n".join(tail))
    return _read(out_csv)


def _read(path):
    df = pd.read_csv(path)
    df = df.rename(columns={"Frame": "f", "Visibility": "v", "X": "x", "Y": "y"}).set_index("f")
    return df[["v", "x", "y"]]


def clean(df, n_frames, max_gap=4, max_jump_frac=0.12, width=1920):
    """Fill short gaps and drop single-frame teleports.

    Returns a dict of per-frame arrays: v/x/y (cleaned), raw_v/raw_x/raw_y (TrackNet output),
    outlier (removed as a false detection) and filled (interpolated across a short gap).
    """
    df = df.reindex(range(n_frames))
    raw_v = df["v"].fillna(0).to_numpy().astype(bool).copy()
    raw_x = df["x"].to_numpy(dtype=float).copy()
    raw_y = df["y"].to_numpy(dtype=float).copy()
    raw_x[~raw_v] = np.nan; raw_y[~raw_v] = np.nan
    v, x, y = raw_v.copy(), raw_x.copy(), raw_y.copy()

    # Remove isolated points that jump far from both neighbours (false detections).
    outlier = np.zeros(n_frames, bool)
    jump = max_jump_frac * width
    for i in range(1, n_frames - 1):
        if v[i] and v[i - 1] and v[i + 1]:
            d1 = np.hypot(x[i] - x[i - 1], y[i] - y[i - 1])
            d2 = np.hypot(x[i] - x[i + 1], y[i] - y[i + 1])
            dn = np.hypot(x[i + 1] - x[i - 1], y[i + 1] - y[i - 1])
            if d1 > jump and d2 > jump and dn < jump:
                v[i] = False; x[i] = np.nan; y[i] = np.nan; outlier[i] = True

    # Linear-interpolate gaps up to max_gap frames.
    s = pd.DataFrame({"x": x, "y": y}).interpolate(limit=max_gap, limit_area="inside")
    x, y = s["x"].to_numpy().copy(), s["y"].to_numpy().copy()
    v2 = ~np.isnan(x)
    filled = v2 & ~v
    return {"v": v2, "x": x, "y": y, "raw_v": raw_v, "raw_x": raw_x, "raw_y": raw_y,
            "outlier": outlier, "filled": filled,
            "params": {"max_gap_frames": max_gap, "outlier_jump_px": round(jump, 1)}}

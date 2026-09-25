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

PROGRESS = re.compile(r"(\d+)/(\d+)")


def weights_present():
    return all(os.path.exists(os.path.join(CKPT_DIR, f)) for f in ("TrackNet_best.pt", "InpaintNet_best.pt"))


def track(video_path, out_dir, on_progress=lambda frac: None):
    """Run TrackNetV3 on a video. Returns a DataFrame indexed by frame with columns v, x, y."""
    if not weights_present():
        raise RuntimeError(f"TrackNetV3 weights missing in {CKPT_DIR}. Run setup.ps1.")
    os.makedirs(out_dir, exist_ok=True)
    video = os.path.abspath(video_path).replace("\\", "/")   # predict.py splits the name on "/"
    cmd = [sys.executable, "-u", RUNNER,
           "--video_file", video,
           "--tracknet_file", os.path.join(CKPT_DIR, "TrackNet_best.pt"),
           "--inpaintnet_file", os.path.join(CKPT_DIR, "InpaintNet_best.pt"),
           "--save_dir", os.path.abspath(out_dir),
           "--large_video", "--batch_size", "8"]
    proc = subprocess.Popen(cmd, cwd=TRACKNET_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    # TrackNet runs two passes (tracking, then inpainting); weight them 85/15.
    phase, last_total, tail, buf = 0, None, [], b""
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
        m = PROGRESS.search(line)
        if m and "it" in line:
            done, total = int(m.group(1)), int(m.group(2))
            if last_total is not None and total != last_total:
                phase = 1
            last_total = total
            frac = done / max(total, 1)
            on_progress(0.85 * frac if phase == 0 else 0.85 + 0.15 * frac)
    if proc.wait() != 0:
        raise RuntimeError("TrackNetV3 failed:\n" + "\n".join(tail))
    name = os.path.splitext(os.path.basename(video))[0]
    df = pd.read_csv(os.path.join(out_dir, f"{name}_ball.csv"))
    df = df.rename(columns={"Frame": "f", "Visibility": "v", "X": "x", "Y": "y"}).set_index("f")
    return df[["v", "x", "y"]]


def clean(df, n_frames, max_gap=4, max_jump_frac=0.12, width=1920):
    """Fill short gaps and drop single-frame teleports. Returns arrays v, x, y of length n_frames."""
    df = df.reindex(range(n_frames))
    v = df["v"].fillna(0).to_numpy().astype(bool)
    x = df["x"].to_numpy(dtype=float)
    y = df["y"].to_numpy(dtype=float)
    x[~v] = np.nan; y[~v] = np.nan

    # Remove isolated points that jump far from both neighbours (false detections).
    jump = max_jump_frac * width
    for i in range(1, n_frames - 1):
        if v[i] and v[i - 1] and v[i + 1]:
            d1 = np.hypot(x[i] - x[i - 1], y[i] - y[i - 1])
            d2 = np.hypot(x[i] - x[i + 1], y[i] - y[i + 1])
            dn = np.hypot(x[i + 1] - x[i - 1], y[i + 1] - y[i - 1])
            if d1 > jump and d2 > jump and dn < jump:
                v[i] = False; x[i] = np.nan; y[i] = np.nan

    # Linear-interpolate gaps up to max_gap frames.
    s = pd.DataFrame({"x": x, "y": y})
    s = s.interpolate(limit=max_gap, limit_area="inside")
    x, y = s["x"].to_numpy(), s["y"].to_numpy()
    v = ~np.isnan(x)
    return v, x, y

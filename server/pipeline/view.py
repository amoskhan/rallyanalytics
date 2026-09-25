"""Which frames show the calibrated wide court view, and where the camera cuts.

Broadcast video mixes the wide playing view with close-ups, crowd shots, replays and
graphics. Shuttle "detections" in those frames are meaningless, so rallies are only
allowed to live inside stretches of the wide view, and a camera cut always ends one.

Court-view score: sample points along the court lines as the user calibrated them and
check that each is brighter than the floor just beside it (painted lines are white).
In the calibrated wide view most samples pass; in any other shot almost none do.
"""
import cv2
import numpy as np

from .court import Court, LENGTH, WIDTH, NET_Y, SINGLES_INSET, SHORT_SERVICE, DOUBLES_LONG_SERVICE

SCALE = 0.5                 # analyse at half resolution
CUT_THRESHOLD = 0.35        # Bhattacharyya distance between colour histograms of consecutive frames
VIEW_THRESHOLD = 0.35       # fraction of line samples that must look like painted lines


def _line_samples(court: Court, per_line=24):
    """Points on the court lines plus unit normals (in image space) for the brightness test."""
    lines = [((0, 0), (WIDTH, 0)), ((0, LENGTH), (WIDTH, LENGTH)), ((0, 0), (0, LENGTH)), ((WIDTH, 0), (WIDTH, LENGTH)),
             ((SINGLES_INSET, 0), (SINGLES_INSET, LENGTH)), ((WIDTH - SINGLES_INSET, 0), (WIDTH - SINGLES_INSET, LENGTH)),
             ((0, NET_Y - SHORT_SERVICE), (WIDTH, NET_Y - SHORT_SERVICE)), ((0, NET_Y + SHORT_SERVICE), (WIDTH, NET_Y + SHORT_SERVICE)),
             ((0, DOUBLES_LONG_SERVICE), (WIDTH, DOUBLES_LONG_SERVICE)),
             ((0, LENGTH - DOUBLES_LONG_SERVICE), (WIDTH, LENGTH - DOUBLES_LONG_SERVICE))]
    pts, normals = [], []
    for (x0, y0), (x1, y1) in lines:
        t = np.linspace(0.04, 0.96, per_line)
        cp = np.stack([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t], 1)
        ip = court.to_image(cp) * SCALE
        d = court.to_image([[x1, y1]])[0] - court.to_image([[x0, y0]])[0]
        n = np.array([-d[1], d[0]]) / (np.hypot(*d) + 1e-9)
        pts.append(ip); normals.append(np.repeat(n[None], len(ip), 0))
    return np.concatenate(pts), np.concatenate(normals)


def analyse(video_path, court: Court, n_frames, on_progress=lambda p: None):
    """Returns dict: score (per frame 0..1), wide (bool per frame), cuts (frame indices)."""
    pts, normals = _line_samples(court)
    cap = cv2.VideoCapture(video_path)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) * SCALE), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * SCALE)
    inside = (pts[:, 0] >= 4) & (pts[:, 0] < w - 4) & (pts[:, 1] >= 4) & (pts[:, 1] < h - 4)
    pts, normals = pts[inside], normals[inside]
    off = 4.0                                          # px (at half resolution) to the floor beside the line
    on = np.round(pts).astype(int)
    side_a = np.round(pts + normals * off).astype(int)
    side_b = np.round(pts - normals * off).astype(int)
    for arr in (side_a, side_b):
        arr[:, 0] = arr[:, 0].clip(0, w - 1); arr[:, 1] = arr[:, 1].clip(0, h - 1)

    scores, cuts, prev_hist = np.zeros(n_frames), [], None
    for f in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.int16)
        line = gray[on[:, 1], on[:, 0]]
        floor = np.maximum(gray[side_a[:, 1], side_a[:, 0]], gray[side_b[:, 1], side_b[:, 0]])
        scores[f] = float(np.mean(line - floor > 18)) if len(on) else 0.0

        hsv = cv2.cvtColor(cv2.resize(small, (160, 90)), cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if prev_hist is not None and cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA) > CUT_THRESHOLD:
            cuts.append(f)
        prev_hist = hist
        if f % 50 == 0:
            on_progress(f / max(n_frames, 1))
    cap.release()

    # Smooth the score over ~0.4 s so a player standing on a line doesn't flip the view off.
    k = 9
    smooth = np.convolve(np.pad(scores, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    # Never smooth across a cut.
    wide = smooth >= VIEW_THRESHOLD
    on_progress(1.0)
    return {"score": scores, "wide": wide, "cuts": cuts, "params": {
        "cut_threshold": CUT_THRESHOLD, "view_threshold": VIEW_THRESHOLD, "line_samples": int(len(on))}}

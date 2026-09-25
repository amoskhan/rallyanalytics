"""Video storage and the analysis job: normalise video -> shuttle -> players -> rallies."""
import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import traceback
import uuid

import cv2
import numpy as np

from . import analysis, players as players_mod, shuttle, view as view_mod
from .court import Court

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data", "videos")
os.makedirs(DATA, exist_ok=True)


def vdir(vid):
    return os.path.join(DATA, vid)


def read_json(vid, name, default=None):
    p = os.path.join(vdir(vid), name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _np_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def write_json(vid, name, obj):
    p = os.path.join(vdir(vid), name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"), default=_np_default)
    os.replace(tmp, p)


def set_status(vid, **kw):
    st = read_json(vid, "status.json", {}) or {}
    st.update(kw, updated=time.time())
    write_json(vid, "status.json", st)


def probe(path):
    cap = cv2.VideoCapture(path)
    meta = {"fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
            "w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}
    cap.release()
    meta["duration"] = round(meta["frames"] / meta["fps"], 2) if meta["fps"] else 0
    return meta


def _codec(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=codec_name", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except Exception:
        return ""


_NVENC = None


def _has_nvenc():
    global _NVENC
    if _NVENC is None:
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30)
            _NVENC = "h264_nvenc" in out.stdout
        except Exception:
            _NVENC = False
    return _NVENC


def normalise(src, dst, on_progress=lambda f: None):
    """Browser-playable H.264 MP4 at <=30 fps (TrackNet was trained on 30 fps broadcast video)."""
    meta = probe(src)
    if _codec(src) == "h264" and meta["fps"] <= 31 and src.lower().endswith(".mp4"):
        shutil.copyfile(src, dst)
        return
    enc = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21"] if _has_nvenc() else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    vf = ["-r", "30"] if meta["fps"] > 31 else []
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-i", src, *vf, *enc,
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", dst]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    total = max(meta["duration"], 1)
    for line in proc.stdout:
        if line.startswith("out_time_ms="):
            try:
                on_progress(min(int(line.split("=")[1]) / 1e6 / total, 1.0))
            except ValueError:
                pass
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg could not convert the video: " + proc.stderr.read()[-800:])


def create(upload_path, filename):
    vid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    os.makedirs(vdir(vid))
    ext = os.path.splitext(filename)[1].lower() or ".mp4"
    src = os.path.join(vdir(vid), "source" + ext)
    shutil.move(upload_path, src)
    write_json(vid, "info.json", {"id": vid, "name": filename, "created": time.time()})
    set_status(vid, state="converting", stage="Preparing video", progress=0)
    JOBS.put(("prepare", vid))
    return vid


def list_videos():
    out = []
    for vid in sorted(os.listdir(DATA), reverse=True):
        info = read_json(vid, "info.json")
        if info:
            out.append({**info, "status": read_json(vid, "status.json", {}), "meta": read_json(vid, "meta.json")})
    return out


def delete(vid):
    shutil.rmtree(vdir(vid), ignore_errors=True)


# ---------------------------------------------------------------- worker

JOBS: "queue.Queue[tuple[str, str]]" = queue.Queue()


def _prepare(vid):
    d = vdir(vid)
    src = next(os.path.join(d, f) for f in os.listdir(d) if f.startswith("source"))
    set_status(vid, state="converting", stage="Preparing video", progress=0)
    normalise(src, os.path.join(d, "video.mp4"), lambda p: set_status(vid, progress=round(p, 3)))
    write_json(vid, "meta.json", probe(os.path.join(d, "video.mp4")))
    if os.path.join(d, "video.mp4") != src:
        os.remove(src)
    set_status(vid, state="needs_court", stage="Mark the court corners", progress=1)


def _analyse(vid):
    d = vdir(vid)
    video = os.path.join(d, "video.mp4")
    meta = read_json(vid, "meta.json")
    cfg = read_json(vid, "court.json")
    court = Court(cfg["corners"])
    n, fps = meta["frames"], meta["fps"]

    timings = {}

    # Weights of each stage in the overall progress bar.
    def stage(name, lo, hi):
        set_status(vid, state="analysing", stage=name, progress=lo)
        timings[name] = time.time()
        return lambda p: set_status(vid, progress=round(lo + (hi - lo) * p, 3))

    def done(name):
        timings[name] = round(time.time() - timings[name], 1)

    S0 = "Checking camera view and cuts"
    S1, S2, S3 = "Tracking the shuttle (TrackNetV3)", "Finding players (YOLO26-pose)", "Splitting rallies and finding hits"
    shuttle_dir = os.path.join(d, "shuttle")
    cached_shuttle = os.path.exists(shuttle.csv_path(shuttle_dir))
    raw = shuttle.track(video, shuttle_dir, n, stage(S1, 0.0, 0.6))
    done(S1)
    sh = shuttle.clean(raw, n, width=meta["w"], fps=fps)

    # View check and player tracking are cached per court calibration.
    key = hashlib.md5(json.dumps(cfg["corners"]).encode()).hexdigest()[:10]
    view_file = os.path.join(d, f"view_{key}.npz")
    prog = stage(S0, 0.6, 0.65)
    cached_view = os.path.exists(view_file)
    if cached_view:
        z = np.load(view_file)
        vw = {"score": z["score"], "wide": z["wide"], "cuts": z["cuts"].tolist(), "params": json.loads(str(z["params"]))}
    else:
        vw = view_mod.analyse(video, court, n, prog)
        np.savez(view_file, score=vw["score"], wide=vw["wide"], cuts=np.array(vw["cuts"], int), params=json.dumps(vw["params"]))
    done(S0)
    cache = read_json(vid, "players_raw.json")
    cached_players = bool(cache and cache.get("key") == key)
    prog = stage(S2, 0.65, 0.95)
    if cached_players:
        people = {int(f): ps for f, ps in cache["frames"].items()}
        prog(1.0)
    else:
        people = players_mod.track(video, court, n, stride=1, on_progress=prog)
        write_json(vid, "players_raw.json", {"key": key, "frames": {str(f): ps for f, ps in people.items()}})
    done(S2)
    mode = cfg.get("mode") if cfg.get("mode") in ("singles", "doubles") else players_mod.guess_mode(people)
    kept = players_mod.select_players(people, mode)

    stage(S3, 0.95, 1.0)
    rallies, candidates, params = analysis.find_rallies(sh, kept, court, fps, mode, vw)
    done(S3)

    write_json(vid, "players.json", {str(f): [[p["id"], 0 if p["side"] == "near" else 1, *p["box"],
                                              *[c for k in p["kps"] for c in ((k[0], k[1]) if k[2] > 0.3 else (-1, -1))]]
                                             for p in ps] for f, ps in kept.items() if ps})

    def arr(a, ok):
        return [None if not o else round(float(val), 1) for val, o in zip(a, ok)]

    # Per-frame counts for the coverage timeline: detected people (all) and kept players per side.
    counts = {"all": [len(people.get(f, [])) for f in range(n)],
              "near": [sum(p["side"] == "near" for p in kept.get(f, [])) for f in range(n)],
              "far": [sum(p["side"] == "far" for p in kept.get(f, [])) for f in range(n)]}
    ids = {p["id"] for ps in kept.values() for p in ps}
    tracker_ids = {p["track"] for ps in kept.values() for p in ps}
    in_rally = np.zeros(n, bool)
    for r in rallies:
        in_rally[r["start"]:r["end"] + 1] = True
    pipeline = {
        "timings_s": timings, "cached": {"shuttle": cached_shuttle, "players": cached_players, "view": cached_view},
        "view": {"wide_frames": int(vw["wide"].sum()), "cuts": len(vw["cuts"]), **vw["params"]},
        "shuttle": {"frames": n, "detected": int(sh["raw_v"].sum()), "after_cleaning": int(sh["v"].sum()),
                    "outliers_removed": int(sh["outlier"].sum()), "gaps_filled": int(sh["filled"].sum()),
                    "detected_in_rallies": int((sh["raw_v"] & in_rally).sum()), "rally_frames": int(in_rally.sum()),
                    **sh["params"]},
        "players": {"frames_with_player": int(sum(1 for f in range(n) if kept.get(f))),
                    "tracker_ids": len(tracker_ids), "player_slots": len(ids), "expected_players": 2 if mode == "singles" else 4,
                    "avg_detected_people": round(float(np.mean(counts["all"])), 2) if n else 0,
                    "model": players_mod.DEFAULT_MODEL},
        "analysis": params,
    }
    write_json(vid, "result.json", {
        "version": 2, "meta": meta, "mode": mode, "court": court.to_json(),
        "shuttle": {"x": arr(sh["x"], sh["v"]), "y": arr(sh["y"], sh["v"]),
                    "raw_x": arr(sh["raw_x"], sh["raw_v"]), "raw_y": arr(sh["raw_y"], sh["raw_v"]),
                    "outlier": np.flatnonzero(sh["outlier"]).tolist(), "filled": np.flatnonzero(sh["filled"]).tolist()},
        "counts": counts, "candidates": candidates, "pipeline": pipeline,
        "view": {"score": [round(float(a), 2) for a in vw["score"]], "cuts": [int(c) for c in vw["cuts"]]},
        "rallies": rallies, "summary": analysis.summarise(rallies),
    })
    set_status(vid, state="done", stage="Analysis complete", progress=1)


def _worker():
    while True:
        kind, vid = JOBS.get()
        try:
            (_prepare if kind == "prepare" else _analyse)(vid)
        except Exception as e:  # keep the worker alive; surface the error in the UI
            traceback.print_exc()
            prev = read_json(vid, "status.json", {}) or {}
            set_status(vid, state="error", error=str(e)[-1500:],
                       retry="prepare" if kind == "prepare" else "analyse", stage=prev.get("stage"))
        finally:
            JOBS.task_done()


def start_worker():
    threading.Thread(target=_worker, daemon=True, name="rallybook-worker").start()
    # Resume anything interrupted by a restart.
    for vid in os.listdir(DATA):
        st = read_json(vid, "status.json", {}) or {}
        if st.get("state") == "converting":
            JOBS.put(("prepare", vid))
        elif st.get("state") in ("queued", "analysing"):
            JOBS.put(("analyse", vid))


def queue_analysis(vid, corners, mode):
    write_json(vid, "court.json", {"corners": corners, "mode": mode})
    set_status(vid, state="queued", stage="Waiting for the GPU", progress=0, error=None)
    JOBS.put(("analyse", vid))

"""Video storage and the analysis job: normalise video -> shuttle -> players -> rallies."""
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

from . import analysis, players as players_mod, shuttle
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


def write_json(vid, name, obj):
    p = os.path.join(vdir(vid), name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))
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

    # Weights of each stage in the overall progress bar.
    def stage(name, lo, hi):
        set_status(vid, state="analysing", stage=name, progress=lo)
        return lambda p: set_status(vid, progress=round(lo + (hi - lo) * p, 3))

    raw = shuttle.track(video, os.path.join(d, "shuttle"), stage("Tracking the shuttle (TrackNetV3)", 0.0, 0.6))
    v, x, y = shuttle.clean(raw, n, width=meta["w"])

    people = players_mod.track(video, court, n, stride=1, on_progress=stage("Finding players (YOLO26-pose)", 0.6, 0.95))
    mode = cfg.get("mode") if cfg.get("mode") in ("singles", "doubles") else players_mod.guess_mode(people)
    kept = players_mod.select_players(people, mode)

    stage("Splitting rallies and finding hits", 0.95, 1.0)
    rallies = analysis.find_rallies(v, x, y, kept, court, fps, mode)

    write_json(vid, "players.json", {str(f): [[p["id"], 0 if p["side"] == "near" else 1, *p["box"],
                                              *[c for k in p["kps"] for c in ((k[0], k[1]) if k[2] > 0.3 else (-1, -1))]]
                                             for p in ps] for f, ps in kept.items() if ps})
    write_json(vid, "result.json", {
        "version": 1, "meta": meta, "mode": mode, "court": court.to_json(),
        "shuttle": {"x": [None if not ok else round(float(a), 1) for a, ok in zip(x, v)],
                    "y": [None if not ok else round(float(b), 1) for b, ok in zip(y, v)]},
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

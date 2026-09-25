"""RallyBook local server: upload videos, run the analysis on the GPU, serve results.

Run from the repo root:  .venv\\Scripts\\python -m uvicorn server.app:app --port 8765
Then open http://localhost:8765/video.html
"""
import os
import tempfile

import cv2
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .pipeline import job, shuttle

app = FastAPI(title="RallyBook")


@app.on_event("startup")
def _startup():
    job.start_worker()


def _need(vid):
    if not os.path.isdir(job.vdir(vid)) or "/" in vid or "\\" in vid or ".." in vid:
        raise HTTPException(404, "No such video")


@app.get("/api/health")
def health():
    import torch
    return {"ok": True, "cuda": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "tracknet_weights": shuttle.weights_present()}


@app.get("/api/videos")
def videos():
    return job.list_videos()


@app.post("/api/videos")
async def upload(file: UploadFile = File(...)):
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(file.filename or "")[1], dir=job.DATA)
    with os.fdopen(fd, "wb") as out:
        while chunk := await file.read(8 * 1024 * 1024):
            out.write(chunk)
    return {"id": job.create(tmp, file.filename or "video.mp4")}


@app.get("/api/videos/{vid}")
def video_info(vid: str):
    _need(vid)
    return {"info": job.read_json(vid, "info.json"), "status": job.read_json(vid, "status.json", {}),
            "meta": job.read_json(vid, "meta.json"), "court": job.read_json(vid, "court.json")}


@app.delete("/api/videos/{vid}")
def video_delete(vid: str):
    _need(vid)
    job.delete(vid)
    return {"ok": True}


@app.get("/api/videos/{vid}/video.mp4")
def video_file(vid: str):
    _need(vid)
    p = os.path.join(job.vdir(vid), "video.mp4")
    if not os.path.exists(p):
        raise HTTPException(404, "Video is still being prepared")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/videos/{vid}/frame.jpg")
def frame(vid: str, t: float = 0.0):
    _need(vid)
    cap = cv2.VideoCapture(os.path.join(job.vdir(vid), "video.mp4"))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(t, 0) * 1000)
    ok, img = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(404, "Could not read that frame")
    return Response(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes(), media_type="image/jpeg")


class CourtIn(BaseModel):
    corners: list[list[float]]
    mode: str = "auto"


@app.post("/api/videos/{vid}/analyse")
def analyse(vid: str, body: CourtIn):
    _need(vid)
    if len(body.corners) != 4:
        raise HTTPException(400, "Mark exactly 4 court corners")
    if not shuttle.weights_present():
        raise HTTPException(500, "TrackNetV3 weights are missing. Run setup.ps1 first.")
    job.queue_analysis(vid, body.corners, body.mode)
    return {"ok": True}


@app.post("/api/videos/{vid}/retry")
def retry(vid: str):
    _need(vid)
    st = job.read_json(vid, "status.json", {}) or {}
    if st.get("retry") == "prepare":
        job.JOBS.put(("prepare", vid))
    elif job.read_json(vid, "court.json"):
        c = job.read_json(vid, "court.json")
        job.queue_analysis(vid, c["corners"], c.get("mode", "auto"))
    return {"ok": True}


@app.get("/api/videos/{vid}/result.json")
def result(vid: str):
    _need(vid)
    p = os.path.join(job.vdir(vid), "result.json")
    if not os.path.exists(p):
        raise HTTPException(404, "No result yet")
    return FileResponse(p, media_type="application/json")


@app.get("/api/videos/{vid}/players.json")
def players(vid: str):
    _need(vid)
    p = os.path.join(job.vdir(vid), "players.json")
    if not os.path.exists(p):
        raise HTTPException(404, "No player data yet")
    return FileResponse(p, media_type="application/json")


class ReviewIn(BaseModel):
    rallies: list[dict]


@app.put("/api/videos/{vid}/review")
def save_review(vid: str, body: ReviewIn):
    """Stores the user's corrections (winner per rally, deleted rallies) next to the result."""
    _need(vid)
    job.write_json(vid, "review.json", {"rallies": body.rallies})
    return {"ok": True}


@app.get("/api/videos/{vid}/review")
def get_review(vid: str):
    _need(vid)
    return job.read_json(vid, "review.json", {"rallies": []})


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# Serve only the two pages, not the whole repo folder.
@app.get("/")
@app.get("/index.html")
def page_scorer():
    return FileResponse(os.path.join(ROOT, "index.html"))


@app.get("/video.html")
def page_video():
    return FileResponse(os.path.join(ROOT, "video.html"))

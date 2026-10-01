"""Rally Analytics local server: upload videos, run the analysis on the GPU, serve results.

Run from the repo root:  .venv\\Scripts\\python -m uvicorn server.app:app --port 8765
Then open http://localhost:8765/video.html
"""
import os
import tempfile

import cv2
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .pipeline import improve, job, labels, shuttle

app = FastAPI(title="Rally Analytics")


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


@app.get("/api/labelling")
def labelling():
    """Checked rallies and Shots in the teaching and test sets, across all Videos."""
    return labels.summary()


@app.post("/api/improvement")
def run_improvement():
    """Tune the stroke rules on the teaching set and score them on the test set. The result
    waits until kept or discarded."""
    return improve.run()


@app.get("/api/improvement")
def pending_improvement():
    return improve.pending()


@app.post("/api/improvement/keep")
def keep_improvement():
    try:
        return {"version": improve.keep()}
    except (LookupError, ValueError) as e:
        raise HTTPException(409, str(e))


@app.post("/api/improvement/discard")
def discard_improvement():
    improve.discard()
    return {"ok": True}


@app.post("/api/improvement/undo")
def undo_improvement():
    """Go back to the stroke rules in use before the last Keep."""
    try:
        return {"version": improve.undo()}
    except LookupError as e:
        raise HTTPException(409, str(e))


@app.get("/api/improvement/history")
def improvement_history():
    """Every improvement run (pending, kept, discarded or replaced) and every undo, newest first."""
    return improve.history()


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


def _refuse_if_checked(vid, clear_checked):
    """Re-analysing can change a Video's Rallies, which would leave Checked rallies pointing at the
    wrong Shots. So it's refused while there are any, unless the Labeller agrees to clear them.
    The caller clears them once nothing else can stop the re-analysis."""
    n = labels.count(vid)
    if n and not clear_checked:
        raise HTTPException(409, f"This video has {n} Checked {'rally' if n == 1 else 'rallies'}. "
                                 "Re-analysing can change its rallies, so they would be unchecked.")


@app.post("/api/videos/{vid}/analyse")
def analyse(vid: str, body: CourtIn, clear_checked: bool = False):
    _need(vid)
    _refuse_if_checked(vid, clear_checked)
    if len(body.corners) != 4:
        raise HTTPException(400, "Mark exactly 4 court corners")
    if not shuttle.weights_present():
        raise HTTPException(500, "TrackNetV3 weights are missing. Run setup.ps1 first.")
    labels.clear(vid)
    job.queue_analysis(vid, body.corners, body.mode)
    return {"ok": True}


@app.post("/api/videos/{vid}/retry")
def retry(vid: str, clear_checked: bool = False):
    _need(vid)
    st = job.read_json(vid, "status.json", {}) or {}
    if st.get("retry") == "prepare":
        job.JOBS.put(("prepare", vid))
    elif job.read_json(vid, "court.json"):
        _refuse_if_checked(vid, clear_checked)
        labels.clear(vid)
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


@app.post("/api/videos/{vid}/recheck-strokes")
def recheck_strokes(vid: str):
    """Bring a Video's Strokes up to date with the current cut-offs, without re-analysing it."""
    _need(vid)
    if (job.read_json(vid, "status.json", {}) or {}).get("state") in ("converting", "queued", "analysing"):
        raise HTTPException(409, "This video is being analysed. Re-check its strokes when that's finished.")
    if not os.path.exists(os.path.join(job.vdir(vid), "result.json")):
        raise HTTPException(404, "No result yet")
    try:
        changed, version = job.recheck_strokes(vid)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"changed": changed, "cutoffs_version": version}


class ReviewIn(BaseModel):
    rallies: list[dict] | None = None
    names: dict[str, str] | None = None     # slot -> name: near1, near2, far1, far2
    strokes: dict[str, str] | None = None   # "<rally>:<frame>" -> stroke, the user's corrections
    hands: dict[str, str] | None = None     # slot -> racket hand "R" / "L"


@app.put("/api/videos/{vid}/review")
def save_review(vid: str, body: ReviewIn):
    """Stores the user's corrections (winner per rally) and player names next to the result.
    Only the fields sent are updated."""
    _need(vid)
    with job.review_lock(vid):
        _update_review(vid, body)
    return {"ok": True}


def _update_review(vid, body):
    cur = job.read_json(vid, "review.json", {}) or {}
    if body.rallies is not None:
        cur["rallies"] = body.rallies
    if body.names is not None:
        cur["names"] = {k: str(v)[:24] for k, v in body.names.items() if k in ("near1", "near2", "far1", "far2")}
    if body.hands is not None:
        cur["hands"] = {k: v for k, v in body.hands.items() if k in ("near1", "near2", "far1", "far2") and v in ("R", "L")}
    if body.strokes is not None:
        old = cur.get("strokes", {})
        cur["strokes"] = {k: str(v)[:20] for k, v in body.strokes.items()}
        labels.follow_corrections(vid, cur, old)
    job.write_json(vid, "review.json", cur)


@app.put("/api/videos/{vid}/rallies/{i}/checked")
def check_rally(vid: str, i: int):
    """A Labeller confirms every Shot's Stroke in Rally i as the review shows it."""
    _need(vid)
    entry = labels.check(vid, i)
    if entry is None:
        raise HTTPException(404, "No such rally")
    return {**entry, "set": job.read_json(vid, "review.json", {}).get("set")}


@app.delete("/api/videos/{vid}/rallies/{i}/checked")
def uncheck_rally(vid: str, i: int):
    _need(vid)
    labels.uncheck(vid, i)
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

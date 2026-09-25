# RallyBook

Badminton scoring and video analysis.

- **Scorebook** (`index.html`): a courtside scorer with BWF rally scoring, service-court tracking, rally tagging and match analysis. It's a single HTML file that works on its own or on GitHub Pages.
- **Video analysis** (`video.html` + `server/`): upload a match video and get back the shuttle's path, player tracking and a rally-by-rally breakdown. It runs locally on an NVIDIA GPU.

## Video analysis pipeline

| Stage | Tool |
|---|---|
| Shuttle tracking | [TrackNetV3](https://github.com/qaz812345/TrackNetV3) (MIT). A trajectory model built for badminton, with inpainting to fill gaps where the shuttle is hidden. |
| Players and pose | [Ultralytics YOLO26](https://docs.ultralytics.com/models/yolo26/) `yolo26m-pose` + ByteTrack. Only people standing on the court are kept. |
| Court | You click the 4 outer court corners once per video. A homography maps pixels to court metres. |
| Rallies | Splits the video into rallies, finds each hit (the shuttle turning around) and who played it, finds the landing spot and whether it was in or out, and guesses the rally winner. |

Best results come from broadcast-style video: camera high behind one baseline with the whole court in view.

### Setup (Windows, NVIDIA GPU)

```
powershell -ExecutionPolicy Bypass -File setup.ps1
```

This creates `.venv`, installs PyTorch (CUDA) and the requirements, clones TrackNetV3 into `third_party/`, and downloads the model weights into `models/`.

### Run

Double-click `start.bat`, then use http://localhost:8765/video.html. Uploaded videos and results are stored in `data/`, which is not committed.

## Keyboard

Scorebook: `1` / `2` award the rally to side A / B · `U` undoes the last rally
Video review: `[` / `]` move to the previous / next rally · `Space` plays or pauses

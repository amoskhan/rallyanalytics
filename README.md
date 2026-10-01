# Rally Analytics

Badminton match analysis for clubs, players and coaches. Upload a video of a match and get back its rallies, which side won each one, and the strokes played in every rally.

- **Video analysis** (`video.html` + `server/`): upload a video, mark the court, and get the shuttle's path, player tracking and a rally-by-rally breakdown with a stroke for every shot. It runs on a PC with an NVIDIA GPU.
- **Match report** (`index.html`): the score sheet and statistics for a match. An analysed video can be sent here to study later. It also works on its own as a courtside scorer (BWF rally scoring, service courts, rally outcomes), and on GitHub Pages.

The words used across the app and these docs (Video, Clip, Rally, Shot, Stroke, Side, Half and so on) are defined in [GLOSSARY.md](GLOSSARY.md).

## How a video is analysed

1. **Prepare.** The upload is converted to a browser-playable MP4 at 30 fps or lower, because the shuttle tracker was trained on 30 fps broadcast video.
2. **Court.** You click the 4 outer court corners once. That maps the picture onto the court in metres, so landing spots, distances and speeds are real.
3. **Shuttle.** [TrackNetV3](https://github.com/qaz812345/TrackNetV3) (MIT) finds the shuttle in every frame and fills short gaps where it is hidden.
4. **Players.** [Ultralytics YOLO26](https://docs.ultralytics.com/models/yolo26/) `yolo26m-pose` with ByteTrack finds each player's body position. Only people standing on the court are kept, and each is assigned to the near or far half.
5. **Rallies.** The shuttle track is split into rallies. Within each rally the app finds every contact (where the shuttle's flight changes sharply with a player's hand at it), who played it, where the last shot landed and whether it was in, and makes a guess at which side won.
6. **Strokes.** Each shot is given one of ShuttleSet's 18 stroke types (clear, lob, smash, net shot and so on) by hand-written rules in [server/pipeline/strokes.py](server/pipeline/strokes.py). The rules use how high the racket wrist was at contact, where the shot was hit from and went to, and its speed and arc. You can correct any stroke in the review.

The code for each step is in [server/pipeline/](server/pipeline/): `job.py` (prepare and run the steps), `court.py`, `shuttle.py`, `players.py`, `analysis.py` (rallies and contacts) and `strokes.py`.

## Filming

Results are best when the video looks like a TV broadcast:

- landscape, not portrait
- camera high and behind one baseline, steady on a tripod
- the whole court, all four corners, in view the whole time

Singles is supported best for now.

## Setup (Windows, NVIDIA GPU)

```
powershell -ExecutionPolicy Bypass -File setup.ps1
```

This creates `.venv`, installs PyTorch (CUDA) and the requirements, clones TrackNetV3 into `third_party/`, and downloads the model weights into `models/`.

## Run

Double-click `start.bat`, then use http://localhost:8765/video.html. Uploaded videos and results are stored in `data/`, which is not committed.

The match report alone needs no server: open `index.html` or the GitHub Pages site.

## Improving stroke recognition

The strokes are improved from rallies checked by experienced players, not from a public dataset. Why: [docs/adr/0001](docs/adr/0001-stroke-learning-from-labeller-corrections.md).

- [Labelling guide](docs/labelling-guide.md): for Labellers, on how to film training clips and check rallies.
- [Training process](docs/training-process.md): for whoever runs the improvements, on how to measure them and decide whether to keep them.

## Keyboard

Match report: `1` / `2` award the rally to side A / B · `U` undoes the last rally
Video review: `[` / `]` move to the previous / next rally · `Space` plays or pauses

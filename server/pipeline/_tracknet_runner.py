"""Runs TrackNetV3's predict.py unchanged, with shims for a current PyTorch.

- torch>=2.6 defaults torch.load(weights_only=True), which rejects TrackNet's checkpoints.
- predict.py imports test.py, which imports pycocotools only for evaluation; stub it if missing.
Run with cwd = third_party/TrackNetV3.
"""
import os
import runpy
import sys
import types

import torch

_load = torch.load
torch.load = lambda *a, **k: _load(*a, **{"weights_only": False, **k})

try:
    import pycocotools.coco  # noqa: F401
except ImportError:
    coco = types.ModuleType("pycocotools")
    coco.coco = types.SimpleNamespace(COCO=None)
    coco.cocoeval = types.SimpleNamespace(COCOeval=None)
    sys.modules.update({"pycocotools": coco, "pycocotools.coco": coco.coco, "pycocotools.cocoeval": coco.cocoeval})

sys.path.insert(0, os.getcwd())

# The stock median-background step stacks up to 1800 full-resolution frames (~11 GB at 1080p).
# The model only ever sees the background at 512x288, so build it from downscaled frames instead.
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import dataset  # noqa: E402


def _gen_median_small(self, max_sample_num, video_range):
    print("Generate median image (downscaled)...")
    start, end = 0, self.video_len
    if video_range is not None:
        start, end = max(0, video_range[0] * self.fps), min(video_range[1] * self.fps, self.video_len)
    step = max(1, (end - start) // min(max_sample_num, 400))
    frames = []
    for i in range(start, end, step):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = self.cap.read()
        if not ok:
            break
        frames.append(cv2.resize(frame, (self.WIDTH, self.HEIGHT), interpolation=cv2.INTER_AREA))
    median = np.median(np.stack(frames), 0)[..., ::-1]  # BGR to RGB
    if self.bg_mode == "concat":
        return np.moveaxis(median.astype("uint8"), -1, 0)
    # Other modes subtract the background from full-size frames, so scale it back up.
    return cv2.resize(median.astype("uint8"), (self.w, self.h), interpolation=cv2.INTER_LINEAR)


dataset.Video_IterableDataset.__gen_median__ = _gen_median_small

# On Windows, DataLoader worker processes re-import the main script, which would re-run
# the whole prediction in every worker. Load data in-process instead.
import torch.utils.data as tud  # noqa: E402

_DL = tud.DataLoader


class _InProcessLoader(_DL):
    def __init__(self, *a, **k):
        k["num_workers"] = 0
        super().__init__(*a, **k)


tud.DataLoader = _InProcessLoader


if __name__ == "__main__":
    sys.argv = ["predict.py"] + sys.argv[1:]
    runpy.run_path("predict.py", run_name="__main__")

"""Where the app saves things. Everything lives under one folder; tests point it at a temporary one."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_ROOT = os.environ.get("RALLYBOOK_DATA") or os.path.join(ROOT, "data")
VIDEOS = os.path.join(DATA_ROOT, "videos")

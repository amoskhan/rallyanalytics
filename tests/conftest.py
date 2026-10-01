"""Tests run against a temporary data folder with no GPU, no model weights and no video files."""
import os
import shutil
import tempfile

import pytest

# Must be set before the server is imported: the data folder is fixed at import time.
DATA_DIR = tempfile.mkdtemp(prefix="rallybook-test-")
os.environ["RALLYBOOK_DATA"] = DATA_DIR

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402


@pytest.fixture
def data_dir():
    """An empty data folder for each test."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    os.makedirs(os.path.join(DATA_DIR, "videos"))
    yield DATA_DIR


@pytest.fixture
def client(data_dir):
    # Not used as a context manager, so the analysis worker (GPU queue) never starts.
    return TestClient(app)

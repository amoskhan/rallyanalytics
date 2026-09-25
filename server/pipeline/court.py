"""Court geometry: a homography from the image plane to court metres.

Court coordinates: x runs across the court (0 = near-left sideline, 6.10 = near-right),
y runs along it (0 = near baseline, 13.40 = far baseline). The net is at y = 6.70.
"near" is the half closest to the camera.
"""
import numpy as np
import cv2

LENGTH = 13.40
WIDTH = 6.10
NET_Y = LENGTH / 2
SINGLES_INSET = 0.46          # singles sideline is 0.46 m inside the doubles sideline
SHORT_SERVICE = 1.98          # short service line distance from the net
DOUBLES_LONG_SERVICE = 0.76   # doubles long service line distance from the back line

# Order the user clicks the corners in.
CORNER_ORDER = ["near-left", "near-right", "far-right", "far-left"]
CORNER_COURT = np.float32([[0, 0], [WIDTH, 0], [WIDTH, LENGTH], [0, LENGTH]])


class Court:
    def __init__(self, corners_px):
        self.corners = np.float32(corners_px)
        self.H = cv2.getPerspectiveTransform(self.corners, CORNER_COURT)       # image -> court
        self.Hinv = cv2.getPerspectiveTransform(CORNER_COURT, self.corners)    # court -> image

    def to_court(self, pts):
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.H).reshape(-1, 2)

    def to_image(self, pts):
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.Hinv).reshape(-1, 2)

    @staticmethod
    def side_of(y):
        return "near" if y < NET_Y else "far"

    @staticmethod
    def is_in(x, y, mode, tol=0.05):
        """Is a landing point inside the rally-play court? Lines are in."""
        x0, x1 = (SINGLES_INSET, WIDTH - SINGLES_INSET) if mode == "singles" else (0.0, WIDTH)
        return (x0 - tol) <= x <= (x1 + tol) and -tol <= y <= LENGTH + tol

    def on_or_near_court(self, x, y, margin=1.5):
        return -margin <= x <= WIDTH + margin and -margin <= y <= LENGTH + margin

    def to_json(self):
        return {"corners": self.corners.tolist(), "H": self.H.tolist(), "Hinv": self.Hinv.tolist()}

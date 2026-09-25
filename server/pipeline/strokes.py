"""Rule-based stroke classification using the ShuttleSet taxonomy (18 types).

ShuttleSet (Wang et al., KDD 2023) labels BWF singles broadcasts with 18 shot types,
so using the same names keeps our labels comparable and lets a model be trained on
it later. Each shot is classified from what the pipeline measures:

- contact height from the hitter's racket wrist (0 = hips, 1 = nose; wrist_height)
- the court zone it was hit from and went to (next contact, or the landing)
- flight time, average speed, arc and direction
- context: first shot = serve; what the previous shot was

Every decision comes with a plain-English reason. Court zones by distance from the
net (each half is 6.70 m; the short service line is 1.98 m out): front < 2.5 m,
mid 2.5-4.3 m, rear > 4.3 m.
"""
from .court import NET_Y

STROKES = [  # ShuttleSet's 18 types, in the dataset's order and wording
    "net shot", "return net", "smash", "wrist smash", "lob", "defensive return lob", "clear",
    "drive", "driven flight", "back-court drive", "drop", "passive drop", "push", "rush",
    "defensive return drive", "cross-court net shot", "short service", "long service",
]
ATTACKS = ("smash", "wrist smash", "rush")
NET_ARRIVALS = ("net shot", "return net", "cross-court net shot", "drop", "passive drop")

FRONT, REAR = 2.5, 4.3          # metres from the net
OVERHEAD, UNDERARM = 0.95, 0.3  # racket-wrist height: 0 = hips, 1 = nose
SMASH_KMH, WRIST_SMASH_KMH = 55, 38

# Older labels (before the ShuttleSet taxonomy) -> new names, for saved corrections.
LEGACY = {"short serve": "short service", "long serve": "long service", "lift": "lob",
          "block": "return net", "net kill": "rush"}


def zone(depth):
    if depth is None:
        return None
    return "front" if depth < FRONT else "rear" if depth > REAR else "mid"


def wrist_height(player, hand=None):
    """Height of the player's highest wrist: 0 = hips, 1 = nose, >1 above the head.

    Uses the body, not the shuttle: the shuttle's position in the picture depends on its
    depth, so a shuttle over the net can look "above the head" of a player behind it.
    Players facing away from the camera hide their nose, so the head is estimated from
    the shoulders (the nose sits about 1.35x the hip-to-shoulder height above the hips).
    """
    if not player:
        return None
    kps = player["kps"]
    ok = lambda i: kps[i][2] > 0.3
    hips = [kps[i][1] for i in (11, 12) if ok(i)]
    # COCO keypoints are the player's own left (9) and right (10) wrist.
    idx = (9,) if hand == "L" else (10,) if hand == "R" else (9, 10)
    wrists = [kps[i][1] for i in idx if ok(i)]
    if not hips or not wrists:
        return None
    hip_y = sum(hips) / len(hips)
    if ok(0):
        head_y = kps[0][1]
    else:
        sh = [kps[i][1] for i in (5, 6) if ok(i)]
        if not sh:
            return None
        head_y = hip_y - 1.35 * (hip_y - sum(sh) / len(sh))
    if hip_y - head_y < 5:
        return None
    return round((hip_y - min(wrists)) / (hip_y - head_y), 2)


def height_band(h):
    if h is None:
        return None
    return "overhead" if h >= OVERHEAD else "underarm" if h < UNDERARM else "side"


def classify(shot, hit, nxt_court, prev_stroke, is_serve):
    """Returns (stroke, reason). shot = shot_metrics entry, hit = hit record."""
    from_d = abs(hit["court"][1] - NET_Y) if hit.get("court") else None
    to_d = abs(nxt_court[1] - NET_Y) if nxt_court else None
    zf, zt = zone(from_d), zone(to_d)
    h = hit.get("contact_h")
    band = height_band(h)
    t = shot["flight_s"]
    kmh = shot.get("avg_speed_kmh") or 0
    arc = shot.get("arc_pct") or 0
    cross = shot.get("direction") == "cross-court"
    flat = t < 0.7 and arc < 15
    facts = [f for f in (band, f"from the {zf} court" if zf else None, f"to the {zt} court" if zt else None,
                         f"{t:.2f} s flight", f"{kmh:.0f} km/h" if kmh else None,
                         f"after a {prev_stroke}" if prev_stroke else None) if f]
    why = lambda s: (s, ", ".join(facts))
    answering_attack = prev_stroke in ATTACKS
    answering_net = prev_stroke in NET_ARRIVALS

    if is_serve:
        # Short services skim the net: low arc, quick flight. Long ones go high to the back.
        high = arc >= 35 or t >= 1.1 or zt == "rear"
        return why("long service" if high else "short service")
    if band is None and zf is None:
        return ("unknown", "no player position or pose at contact")

    # --- front court: only net shot, cross-court net shot or lob are possible from here.
    # Short and quick is a net shot (cross-court if it crosses the centre line); anything
    # longer or higher is a lob.
    if zf == "front":
        if zt == "front" or (t < 0.9 and arc < 30 and zt != "rear"):
            return why("cross-court net shot" if cross else "net shot")
        return why("lob")

    # --- overhead: clear, drop, passive drop, smash, wrist smash (rush at the net)
    if band == "overhead":
        if kmh >= SMASH_KMH or (t < 0.55 and (shot.get("distance_m") or 0) > 5):
            return why("smash")
        if kmh >= WRIST_SMASH_KMH and t < 0.8 and zf != "rear":
            return why("wrist smash")
        if t >= 0.95 and zt != "front":
            return why("clear")
        # A drop reached late from deep (wrist only just overhead) is a passive drop.
        if zf == "rear" and h is not None and h < 1.1:
            return why("passive drop")
        return why("drop")

    # --- replies to an attack from mid/rear: defensive lob / drive, or a block to the net
    if answering_attack:
        if zt == "front":
            return why("return net")
        if t >= 0.9 or arc >= 30:
            return why("defensive return lob")
        return why("defensive return drive")

    # --- mid / rear court, below the head
    if band == "underarm" and (t >= 0.9 or arc >= 30):
        return why("lob")
    if t >= 0.95:
        return why("clear" if zf == "rear" and band == "side" else "lob")
    if zf == "rear" and flat:
        return why("back-court drive")
    if flat or kmh >= 40:
        return why("drive")
    if zt == "front":
        return why("drop" if band == "side" else "net shot")
    return why("push")

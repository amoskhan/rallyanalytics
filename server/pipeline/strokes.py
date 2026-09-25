"""Rule-based stroke classification for each shot.

Uses what the pipeline already measures: how high the contact was relative to the
hitter's body, where the hitter stood, where the shot went (the next contact or the
landing), flight time, speed and arc. Every decision returns a plain-English reason
so it can be checked against the video and the rules tuned from user corrections.

Court zones by distance from the net (each half is 6.70 m long; the short service
line is 1.98 m from the net): front < 2.5 m, mid 2.5-4.3 m, rear > 4.3 m.
"""
from .court import NET_Y

STROKES = ["short serve", "long serve", "clear", "smash", "drop", "net shot", "lift",
           "push", "drive", "net kill", "block"]

FRONT, REAR = 2.5, 4.3          # metres from the net
OVERHEAD, UNDERARM = 0.95, 0.3  # racket-wrist height: 0 = hips, 1 = nose


def zone(depth):
    if depth is None:
        return None
    return "front" if depth < FRONT else "rear" if depth > REAR else "mid"


def wrist_height(player):
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
    wrists = [kps[i][1] for i in (9, 10) if ok(i)]
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
    band = height_band(hit.get("contact_h"))
    t = shot["flight_s"]
    fast = (shot.get("avg_speed_kmh") or 0) >= 50 or (t < 0.6 and (shot.get("distance_m") or 0) > 4.5)
    facts = [f for f in (band, f"from the {zf} court" if zf else None,
                         f"to the {zt} court" if zt else None, f"{t:.2f} s flight") if f]
    why = lambda s: (s, ", ".join(facts))

    if is_serve:
        # Short serves skim the net: low arc, quick flight. Long serves go high to the back.
        high = (shot.get("arc_pct") or 0) >= 35 or t >= 1.1 or zt == "rear"
        return why("long serve" if high else "short serve")
    if band is None and zf is None:
        return ("unknown", "no player position or pose at contact")

    if band == "overhead":
        if zf == "front" and (fast or t < 0.5):
            return why("net kill")
        if zt == "rear" and t >= 0.9:
            return why("clear")
        if fast and t < 0.8:
            return why("smash")
        if zt == "front":
            return why("drop")
        # Overhead but not fast: long and high is a clear, otherwise a (slow or fast) drop.
        return why("clear" if t >= 0.95 else "drop")

    if band == "underarm":
        if prev_stroke in ("smash", "net kill") and zt == "front":
            return why("block")
        if zf == "front":
            if zt == "rear" or t >= 0.9:
                return why("lift")
            if zt == "front":
                return why("net shot")
            return why("push")
        if zt == "front":
            return why("block")
        return why("lift" if t >= 0.9 else "drive")

    # Side-arm (roughly shoulder height) or unknown height.
    if zf == "front":
        if fast or t < 0.45:
            return why("net kill" if band == "overhead" else "push")
        if zt == "front":
            return why("net shot")
        return why("lift" if (zt == "rear" or t >= 0.9) else "push")
    if t < 0.65 and (shot.get("arc_pct") or 0) < 8:
        return why("drive")
    if zt == "front":
        return why("drop" if band != "underarm" else "block")
    if t >= 0.95:
        # A long flight from side-arm height is a high shot: clear from the back, lift otherwise.
        return why("clear" if zf == "rear" else "lift")
    if zf == "mid" and (shot.get("avg_speed_kmh") or 0) < 40:
        return why("push")
    return why("drive")

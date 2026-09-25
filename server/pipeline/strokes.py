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
OVERHEAD, UNDERARM = 0.85, 0.35 # contact height as a fraction of hip-to-head height


def zone(depth):
    if depth is None:
        return None
    return "front" if depth < FRONT else "rear" if depth > REAR else "mid"


def contact_height(player, sy):
    """How high the contact was: 0 = hips, 1 = top of the head (box top), >1 above it."""
    if not player:
        return None
    box, kps = player["box"], player["kps"]
    hips = [kps[i][1] for i in (11, 12) if kps[i][2] > 0.3]
    hip_y = sum(hips) / len(hips) if hips else box[1] + 0.55 * (box[3] - box[1])
    top = box[1]
    if hip_y - top < 5:
        return None
    return round((hip_y - sy) / (hip_y - top), 2)


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
    fast = (shot.get("avg_speed_kmh") or 0) >= 60 or (t < 0.55 and (shot.get("distance_m") or 0) > 4.5)
    facts = [f for f in (band, f"from the {zf} court" if zf else None,
                         f"to the {zt} court" if zt else None, f"{t:.2f} s flight") if f]
    why = lambda s: (s, ", ".join(facts))

    if is_serve:
        return why("long serve" if (zt == "rear" or t >= 1.0) else "short serve")
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
        return why("smash" if t < 0.75 else "clear" if t >= 1.0 else "drop")

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
    if zt == "rear":
        return why("clear" if t >= 0.9 else "drive")
    return why("drive")

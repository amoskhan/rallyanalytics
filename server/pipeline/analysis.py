"""Turns per-frame shuttle and player tracks into rallies, hits, landings and a winner guess.

Assumes the camera is high behind one baseline (broadcast view), so the shuttle's
image y tells us which half it is travelling toward: near-side hits send it up the
image (y falls), far-side hits send it down (y rises). A hit is therefore a turning
point in the shuttle's y track.
"""
import numpy as np
from scipy.signal import find_peaks, savgol_filter

from .court import Court, NET_Y
from .players import L_WRIST, R_WRIST

OTHER = {"near": "far", "far": "near"}


def _segments(mask, max_gap):
    """Runs of True in mask, bridging gaps of up to max_gap False frames."""
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    segs, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > max_gap + 1:
            segs.append((start, prev)); start = i
        prev = i
    segs.append((start, prev))
    return segs


def _fill(a):
    a = a.copy()
    n = np.isnan(a)
    if n.all():
        return a
    a[n] = np.interp(np.flatnonzero(n), np.flatnonzero(~n), a[~n])
    return a


def _nearest_frame(players, f, search=4):
    for d in range(search + 1):
        for g in (f - d, f + d):
            if g in players and players[g]:
                return players[g]
    return []


def _hitter(players, f, side, sx, sy):
    """Player on `side` whose wrist (or box centre) is closest to the shuttle at frame f."""
    best, best_d = None, 1e18
    for p in _nearest_frame(players, f):
        if p["side"] != side:
            continue
        pts = [p["kps"][i][:2] for i in (L_WRIST, R_WRIST) if p["kps"][i][2] > 0.3]
        b = p["box"]
        pts.append([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
        d = min(np.hypot(px - sx, py - sy) for px, py in pts)
        if d < best_d:
            best, best_d = p, d
    return best


def _landing_frame(x, y, s, e, fps, still_px):
    """First frame of the shuttle's final motionless stretch (it has hit the floor), else e."""
    k = max(2, int(0.1 * fps))
    f = e
    while f - k > s:
        if np.hypot(x[f] - x[f - k], y[f] - y[f - k]) < still_px:
            f -= 1
        else:
            break
    return f, f < e - k


def find_rallies(v, x, y, players, court: Court, fps, mode):
    n = len(v)
    near_px = court.to_image([[3.05, 0]])[0]
    far_px = court.to_image([[3.05, 13.4]])[0]
    court_h = abs(near_px[1] - far_px[1])          # court length in image pixels
    still_px = max(3.0, 0.006 * court_h)

    rallies = []
    for s, e in _segments(v, max_gap=int(0.8 * fps)):
        dur = (e - s + 1) / fps
        if dur < 1.2 or v[s:e + 1].mean() < 0.6:
            continue
        xs, ys = _fill(x[s:e + 1]), _fill(y[s:e + 1])
        travel = np.nansum(np.hypot(np.diff(xs), np.diff(ys)))
        if travel < 0.8 * court_h:                  # shuttle never really flew: someone holding it, etc.
            continue

        land_f, settled = _landing_frame(x, y, s, e, fps, still_px)
        # Drop the stationary tail (shuttle on the floor or being picked up).
        e2 = land_f
        ys = _fill(y[s:e2 + 1])
        win = max(5, int(fps * 0.17) | 1)
        ysm = savgol_filter(ys, win, 2) if len(ys) > win else ys

        prom = 0.05 * court_h
        dist = max(3, int(0.28 * fps))
        near_hits, pn = find_peaks(ysm, prominence=prom, distance=dist)     # y max: shuttle low in image, near player
        far_hits, pf = find_peaks(-ysm, prominence=prom, distance=dist)     # y min: far player
        events = sorted([(int(i), "near", float(p)) for i, p in zip(near_hits, pn["prominences"])] +
                        [(int(i), "far", float(p)) for i, p in zip(far_hits, pf["prominences"])])

        # The serve: which way does the shuttle leave the start of the rally?
        k = min(len(ysm) - 1, max(2, int(0.15 * fps)))
        serve_side = "near" if ysm[k] < ysm[0] else "far"
        if not events or events[0][0] > int(0.3 * fps) or events[0][1] != serve_side:
            events.insert(0, (0, serve_side, float("inf")))

        # Enforce alternation: two hits in a row by the same side keep the stronger turn.
        alt = []
        for ev in events:
            if alt and alt[-1][1] == ev[1]:
                if ev[2] > alt[-1][2]:
                    alt[-1] = ev
            else:
                alt.append(ev)

        hits = []
        xs = _fill(x[s:e2 + 1])
        for i, side, _ in alt:
            f = s + i
            sx, sy = float(xs[i]), float(ys[i])
            p = _hitter(players, f, side, sx, sy)
            hits.append({"f": int(f), "side": side, "px": [round(sx, 1), round(sy, 1)],
                         "player": p["id"] if p else None,
                         "court": p["court"] if p else None})

        lx, ly = (x[land_f], y[land_f]) if not np.isnan(x[land_f]) else (x[e], y[e])
        cx, cy = court.to_court([[lx, ly]])[0]
        land_side = Court.side_of(cy)
        is_in = Court.is_in(cx, cy, mode)
        last = hits[-1]["side"]
        if land_side == last:
            winner, how = OTHER[last], "net"
        elif not is_in:
            winner, how = OTHER[last], "out"
        else:
            winner, how = last, "winner"

        rallies.append({
            "start": int(s), "end": int(e2), "t0": round(s / fps, 2), "t1": round(e2 / fps, 2),
            "duration": round((e2 - s + 1) / fps, 2),
            "hits": hits, "shots": len(hits), "server_side": hits[0]["side"],
            "landing": {"f": int(land_f), "px": [round(float(lx), 1), round(float(ly), 1)],
                        "court": [round(float(cx), 2), round(float(cy), 2)],
                        "side": land_side, "in": bool(is_in), "settled": bool(settled)},
            "winner_side": winner, "how": how,
            "confidence": "high" if settled and len(hits) >= 2 else "low",
            "movement": _movement(players, s, e2, fps),
        })
    for i, r in enumerate(rallies):
        r["i"] = i
    return rallies


def _movement(players, s, e, fps):
    """Metres covered by each on-court player (keyed by side, plus track id for doubles)."""
    step = max(1, int(fps / 10))
    paths = {}
    for f in range(s, e + 1, step):
        for p in players.get(f, []):
            paths.setdefault(p["id"], {"side": p["side"], "pts": []})["pts"].append(p["court"])
    out = []
    for pid, d in paths.items():
        pts = np.array(d["pts"])
        if len(pts) < 3:
            continue
        # Light smoothing so pose jitter doesn't count as running.
        k = min(5, len(pts))
        sm = np.stack([np.convolve(pts[:, j], np.ones(k) / k, mode="valid") for j in (0, 1)], axis=1)
        dist = float(np.sum(np.hypot(*np.diff(sm, axis=0).T)))
        out.append({"id": int(pid), "side": d["side"], "metres": round(dist, 1)})
    return out


def summarise(rallies):
    if not rallies:
        return {"rallies": 0}
    shots = [r["shots"] for r in rallies]
    durs = [r["duration"] for r in rallies]
    won = {"near": 0, "far": 0}
    how = {"winner": 0, "out": 0, "net": 0}
    for r in rallies:
        won[r["winner_side"]] += 1
        how[r["how"]] += 1
    return {
        "rallies": len(rallies),
        "avg_shots": round(float(np.mean(shots)), 1), "max_shots": int(max(shots)),
        "avg_duration": round(float(np.mean(durs)), 1), "max_duration": round(float(max(durs)), 1),
        "won": won, "how": how,
    }

"""Turns per-frame shuttle and player tracks into rallies, hits, landings and a winner guess.

Assumes the camera is high behind one baseline (broadcast view), so the shuttle's
image y tells us which half it is travelling toward: near-side hits send it up the
image (y falls), far-side hits send it down (y rises). A hit is therefore a turning
point in the shuttle's y track.

Everything the detector looks at is also returned (signals, thresholds, rejected
candidates) so the review page can show why it decided what it did.
"""
import numpy as np
from scipy.signal import find_peaks, savgol_filter

from .court import Court, NET_Y, WIDTH as COURT_W
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
    a = np.array(a, dtype=float)
    n = np.isnan(a)
    if n.all() or not n.any():
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
    return best, (None if best is None else float(best_d))


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


def _px_per_m(court, cx, cy):
    """Image pixels per court metre (across the court) at a court position."""
    a, b = court.to_image([[cx - 0.5, cy], [cx + 0.5, cy]])
    return float(np.hypot(*(b - a)))


def _r(v, n=2):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), n)


def find_rallies(sh, players, court: Court, fps, mode):
    v, x, y = sh["v"], sh["x"], sh["y"]
    near_px = court.to_image([[3.05, 0]])[0]
    far_px = court.to_image([[3.05, 13.4]])[0]
    court_h = float(abs(near_px[1] - far_px[1]))   # court length in image pixels
    still_px = max(3.0, 0.006 * court_h)
    params = {
        "rally_gap_s": 0.8, "min_rally_s": 1.2, "min_visible_frac": 0.6, "min_travel_courts": 0.8,
        "hit_prominence_px": round(0.08 * court_h, 1), "hit_min_gap_s": 0.28,
        "wobble_prominence_px": round(0.2 * court_h, 1), "wobble_gap_s": 0.45,
        "hand_near_px": round(0.12 * court_h, 1),
        "smooth_window_frames": max(5, int(fps * 0.17) | 1), "still_px": round(still_px, 1),
        "court_height_px": round(court_h, 1),
    }

    rallies, candidates = [], []
    for s, e in _segments(v, max_gap=int(params["rally_gap_s"] * fps)):
        dur = (e - s + 1) / fps
        vis = float(v[s:e + 1].mean())
        xs, ys = _fill(x[s:e + 1]), _fill(y[s:e + 1])
        travel = float(np.nansum(np.hypot(np.diff(xs), np.diff(ys))))
        cand = {"start": int(s), "end": int(e), "duration": round(dur, 2), "visible": round(vis, 2),
                "travel_courts": round(travel / court_h, 2)}
        reason = None
        if dur < params["min_rally_s"]:
            reason = f"too short ({dur:.1f} s < {params['min_rally_s']} s)"
        elif vis < params["min_visible_frac"]:
            reason = f"shuttle seen in only {vis:.0%} of frames"
        elif travel < params["min_travel_courts"] * court_h:
            reason = f"shuttle barely moved ({travel / court_h:.2f} court lengths)"
        if reason:
            candidates.append({**cand, "kept": False, "reason": reason})
            continue
        candidates.append({**cand, "kept": True, "reason": "rally"})
        rallies.append(_analyse_rally(s, e, sh, players, court, fps, mode, params))

    for i, r in enumerate(rallies):
        r["i"] = i
    return rallies, candidates, params


def _analyse_rally(s, e, sh, players, court, fps, mode, params):
    v, x, y = sh["v"], sh["x"], sh["y"]
    court_h = params["court_height_px"]
    land_f, settled = _landing_frame(x, y, s, e, fps, params["still_px"])
    e2 = land_f                                           # drop the stationary tail
    xs, ys = _fill(x[s:e2 + 1]), _fill(y[s:e2 + 1])
    win = params["smooth_window_frames"]
    ysm = savgol_filter(ys, win, 2) if len(ys) > win else ys.copy()

    prom, dist = params["hit_prominence_px"], max(3, int(params["hit_min_gap_s"] * fps))
    near_i, pn = find_peaks(ysm, prominence=prom, distance=dist)      # y max: shuttle low in image -> near player
    far_i, pf = find_peaks(-ysm, prominence=prom, distance=dist)      # y min: far player
    # Weaker turning points too, so the chart can show what fell under the threshold.
    weak_n, wn = find_peaks(ysm, prominence=prom * 0.35, distance=dist)
    weak_f, wf = find_peaks(-ysm, prominence=prom * 0.35, distance=dist)
    strong = set(near_i.tolist()) | set(far_i.tolist())
    below = [{"f": int(s + i), "side": sd, "prominence": round(float(p), 1)}
             for arr, props, sd in ((weak_n, wn, "near"), (weak_f, wf, "far"))
             for i, p in zip(arr, props["prominences"]) if int(i) not in strong]

    events = sorted([(int(i), "near", float(p)) for i, p in zip(near_i, pn["prominences"])] +
                    [(int(i), "far", float(p)) for i, p in zip(far_i, pf["prominences"])])

    # A small down-up wobble in the track shows as a peak and trough close together with
    # similar prominence. Drop such pairs unless a player's hand is at the shuttle for both.
    def hand_near(ev):
        _, d = _hitter(players, s + ev[0], ev[1], float(xs[ev[0]]), float(ys[ev[0]]))
        return d is not None and d < params["hand_near_px"]

    wobbles, changed = [], True
    while changed:
        changed = False
        for j in range(len(events) - 1):
            a, b = events[j], events[j + 1]
            if (a[1] != b[1] and b[0] - a[0] < params["wobble_gap_s"] * fps
                    and min(a[2], b[2]) < params["wobble_prominence_px"] and not (hand_near(a) and hand_near(b))):
                wobbles += [{"f": int(s + ev[0]), "side": ev[1], "prominence": round(ev[2], 1)} for ev in (a, b)]
                del events[j:j + 2]
                changed = True
                break

    # The serve: which way does the shuttle leave the start of the rally?
    k = min(len(ysm) - 1, max(2, int(0.15 * fps)))
    serve_side = "near" if ysm[k] < ysm[0] else "far"
    if not events or events[0][0] > int(0.3 * fps) or events[0][1] != serve_side:
        events.insert(0, (0, serve_side, float("inf")))

    # Enforce alternation: two hits in a row by the same side keep the stronger turn.
    alt, merged = [], []
    for ev in events:
        if alt and alt[-1][1] == ev[1]:
            loser = ev if ev[2] <= alt[-1][2] else alt[-1]
            merged.append({"f": int(s + loser[0]), "side": loser[1], "prominence": round(loser[2], 1)})
            if ev[2] > alt[-1][2]:
                alt[-1] = ev
        else:
            alt.append(ev)

    hits = []
    for i, side, p in alt:
        f = s + i
        pl, d = _hitter(players, f, side, float(xs[i]), float(ys[i]))
        hits.append({"f": int(f), "side": side, "px": [round(float(xs[i]), 1), round(float(ys[i]), 1)],
                     "prominence": None if p == float("inf") else round(p, 1), "serve": i == 0,
                     "player": pl["id"] if pl else None, "court": pl["court"] if pl else None,
                     "hand_dist_px": _r(d, 1)})

    lx, ly = (x[land_f], y[land_f]) if not np.isnan(x[land_f]) else (x[e], y[e])
    cx, cy = court.to_court([[lx, ly]])[0]
    # The floor projection only means something if the shuttle was near the floor. A last
    # sighting high in the air (lights, out of frame, camera cut) projects far off the court.
    plausible = -2.0 <= cx <= COURT_W + 2.0 and -3.0 <= cy <= 16.4
    last = hits[-1]["side"]
    if not plausible:
        land_side, is_in, winner, how = None, None, None, "unknown"
    else:
        land_side, is_in = Court.side_of(cy), Court.is_in(cx, cy, mode)
        if land_side == last:
            winner, how = OTHER[last], "net"
        elif not is_in:
            winner, how = OTHER[last], "out"
        else:
            winner, how = last, "winner"
    landing = {"f": int(land_f), "px": [round(float(lx), 1), round(float(ly), 1)],
               "court": [round(float(cx), 2), round(float(cy), 2)] if plausible else None, "side": land_side,
               "in": is_in, "settled": bool(settled), "plausible": bool(plausible)}

    shots = _shot_metrics(hits, landing, xs, ys, s, fps, court, court_h)
    speed = np.hypot(np.gradient(xs), np.gradient(ys)) * fps          # px/s along the image track
    step = 1
    return {
        "start": int(s), "end": int(e2), "t0": round(s / fps, 2), "t1": round(e2 / fps, 2),
        "duration": round((e2 - s + 1) / fps, 2),
        "hits": hits, "shots": len(hits), "server_side": hits[0]["side"], "shot_metrics": shots,
        "landing": landing, "winner_side": winner, "how": how,
        "confidence": "high" if settled and plausible and len(hits) >= 2 else "low",
        "movement": _movement(players, s, e2, fps),
        "tracking": {"frames": int(e2 - s + 1), "detected": int(sh["raw_v"][s:e2 + 1].sum()),
                     "filled": int(sh["filled"][s:e2 + 1].sum()), "outliers": int(sh["outlier"][s:e2 + 1].sum())},
        "signal": {"y_smooth": [round(float(a), 1) for a in ysm[::step]],
                   "speed_px_s": [round(float(a)) for a in speed[::step]],
                   "below_threshold": below, "merged": merged, "wobbles": wobbles},
    }


def _shot_metrics(hits, landing, xs, ys, s, fps, court, court_h):
    """Per shot: flight time, distance between hitter and next contact, average speed, arc, direction."""
    out = []
    for k, h in enumerate(hits):
        nxt = hits[k + 1] if k + 1 < len(hits) else None
        f1 = nxt["f"] if nxt else landing["f"]
        flight = (f1 - h["f"]) / fps
        a = h["court"]
        b = nxt["court"] if nxt else landing["court"]    # landing court is None when unknown
        dist = float(np.hypot(b[0] - a[0], b[1] - a[1])) if a and b else None
        avg = dist / flight if dist and flight > 0 else None

        i0, i1 = h["f"] - s, min(f1 - s, len(xs) - 1)
        seg_x, seg_y = xs[i0:i1 + 1], ys[i0:i1 + 1]
        peak_px = None
        if len(seg_x) > 2:
            first = max(3, int(0.2 * fps))
            sp = np.hypot(np.diff(seg_x[:first + 1]), np.diff(seg_y[:first + 1])) * fps
            peak_px = float(sp.max()) if len(sp) else None
        ppm = _px_per_m(court, *(a if a else court.to_court([h["px"]])[0]))
        peak_ms = peak_px / ppm if peak_px and ppm > 0 else None

        # Arc: how far the shuttle rises above the straight line between contact points (image px).
        arc = None
        if len(seg_x) > 2:
            p0, p1 = np.array([seg_x[0], seg_y[0]]), np.array([seg_x[-1], seg_y[-1]])
            chord = p1 - p0
            n = np.hypot(*chord)
            if n > 1:
                cross = (chord[0] * (seg_y - p0[1]) - chord[1] * (seg_x - p0[0])) / n
                arc = float(np.max(np.abs(cross))) / court_h * 100   # % of court height in the image

        direction = None
        if a and b:
            direction = "cross-court" if (a[0] - COURT_W / 2) * (b[0] - COURT_W / 2) < 0 and abs(b[0] - a[0]) > 1.2 else "straight"
        out.append({"k": k, "f": h["f"], "side": h["side"], "flight_s": round(flight, 2),
                    "distance_m": _r(dist, 1), "avg_speed_kmh": _r(avg * 3.6 if avg else None, 0),
                    "peak_speed_kmh": _r(peak_ms * 3.6 if peak_ms else None, 0),
                    "arc_pct": _r(arc, 1), "direction": direction, "to": "landing" if not nxt else "next hit"})
    return out


def _movement(players, s, e, fps):
    """Metres covered and top speed for each on-court player, plus their sampled court path."""
    step = max(1, int(fps / 10))
    paths = {}
    for f in range(s, e + 1, step):
        for p in players.get(f, []):
            paths.setdefault(p["id"], {"side": p["side"], "pts": [], "f": []})
            paths[p["id"]]["pts"].append(p["court"]); paths[p["id"]]["f"].append(f)
    out = []
    for pid, d in paths.items():
        pts = np.array(d["pts"])
        if len(pts) < 3:
            continue
        k = min(5, len(pts))       # light smoothing so pose jitter doesn't count as running
        sm = np.stack([np.convolve(pts[:, j], np.ones(k) / k, mode="valid") for j in (0, 1)], axis=1)
        seg = np.hypot(*np.diff(sm, axis=0).T)
        dt = step / fps
        seg = seg[seg / dt < 9.0]      # faster than 9 m/s is a tracking jump, not running
        out.append({"id": int(pid), "side": d["side"], "metres": round(float(seg.sum()), 1),
                    "top_speed_ms": round(float(seg.max() / dt), 1) if len(seg) else 0,
                    "path": [[round(float(a), 2), round(float(b), 2)] for a, b in sm[::2]]})
    return out


def summarise(rallies):
    if not rallies:
        return {"rallies": 0}
    shots = [r["shots"] for r in rallies]
    durs = [r["duration"] for r in rallies]
    won = {"near": 0, "far": 0, "unknown": 0}
    how = {"winner": 0, "out": 0, "net": 0, "unknown": 0}
    for r in rallies:
        won[r["winner_side"] or "unknown"] += 1
        how[r["how"]] += 1
    return {
        "rallies": len(rallies),
        "avg_shots": round(float(np.mean(shots)), 1), "max_shots": int(max(shots)),
        "avg_duration": round(float(np.mean(durs)), 1), "max_duration": round(float(max(durs)), 1),
        "won": won, "how": how,
    }

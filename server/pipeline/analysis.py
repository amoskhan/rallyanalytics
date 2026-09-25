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


def _hand_ratio(players, f, sx, sy):
    """Closest wrist (or body centre) of any player to the shuttle, as a fraction of that
    player's height in the picture, so near and far players are judged alike.
    Returns (ratio, side, player, distance_px); ratio is 9 when no player is found."""
    best = (9.0, None, None, None)
    for g in (f - 1, f, f + 1):
        for p in players.get(g, []):
            b = p["box"]
            bh = max(1.0, b[3] - b[1])
            pts = [p["kps"][i][:2] for i in (L_WRIST, R_WRIST) if p["kps"][i][2] > 0.3]
            pts.append([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
            d = min(float(np.hypot(px - sx, py - sy)) for px, py in pts)
            if d / bh < best[0]:
                best = (d / bh, p["side"], p, round(d, 1))
    return best


def _assign_sides(kept, xs, ys, court, players, s):
    """Most likely near/far label for each contact, given that shots alternate sides.

    Evidence per contact: which team's hand is nearest (weighted by how near), and whether
    the contact is below the net line in the picture (near half) or above it (far half).
    Viterbi over the sequence; a same-side repeat costs a penalty (it means a missed shot).
    """
    if not kept:
        return []
    net_y = float(court.to_image([[3.05, NET_Y]])[0][1])
    far_y = float(court.to_image([[3.05, 13.4]])[0][1])
    near_y = float(court.to_image([[3.05, 0.0]])[0][1])
    cost = []                                        # cost[t] = {side: cost}
    for h in kept:
        c = {"near": 0.0, "far": 0.0}
        if h["side"] is not None and h["hand_ratio"] is not None:
            w = 1.5 / (0.15 + h["hand_ratio"])     # a hand right at the shuttle is strong evidence
            c[OTHER[h["side"]]] += w
        y = float(ys[h["i"]])
        # Below the net line => near half (contacts there are almost always near players).
        z = (y - net_y) / max(1.0, (near_y - far_y) / 2)
        c["far"] += max(0.0, z) * 4.0
        c["near"] += max(0.0, -z) * 1.5            # far-half position is weaker: near players smash from high too
        cost.append(c)
    SAME = 6.0
    best = [{sd: cost[0][sd] for sd in ("near", "far")}]
    back = [{}]
    for t in range(1, len(kept)):
        best.append({}); back.append({})
        for sd in ("near", "far"):
            opts = {prev: best[t - 1][prev] + (SAME if prev == sd else 0.0) for prev in ("near", "far")}
            prev = min(opts, key=opts.get)
            best[t][sd] = opts[prev] + cost[t][sd]
            back[t][sd] = prev
    sd = min(best[-1], key=best[-1].get)
    out = [sd]
    for t in range(len(kept) - 1, 0, -1):
        sd = back[t][sd]
        out.append(sd)
    return out[::-1]


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


def _split(segs, breaks, ok):
    """Split segments at break frames; trim each piece to frames where ok is True."""
    out = []
    for s, e in segs:
        start = s
        for b in [b for b in breaks if s <= b <= e] + [e + 1]:
            idx = np.flatnonzero(ok[start:b])
            if len(idx):
                out.append((start + int(idx[0]), start + int(idx[-1])))
            start = b + 1
    return out


def find_rallies(sh, players, court: Court, fps, mode, view=None):
    v, x, y = sh["v"], sh["x"], sh["y"]
    n = len(v)
    wide = view["wide"] if view is not None else np.ones(n, bool)
    cuts = set(view["cuts"]) if view is not None else set()
    v_eff = v & wide
    near_px = court.to_image([[3.05, 0]])[0]
    far_px = court.to_image([[3.05, 13.4]])[0]
    court_h = float(abs(near_px[1] - far_px[1]))   # court length in image pixels
    still_px = max(3.0, 0.006 * court_h)
    params = {
        "rally_gap_s": 0.8, "min_rally_s": 1.2, "min_visible_frac": 0.6, "min_travel_courts": 0.8,
        "contact_strong": 0.8, "contact_weak": 0.5, "hand_strong": 0.7, "hand_weak": 0.3, "hit_min_gap_s": 0.25,
        "smooth_window_frames": max(5, int(fps * 0.17) | 1), "still_px": round(still_px, 1),
        "court_height_px": round(court_h, 1),
    }

    rallies, candidates = [], []
    # A rally can't span a camera cut or leave the wide court view.
    breaks = sorted(cuts | set(np.flatnonzero(~wide).tolist()))
    segs = _split(_segments(v_eff, max_gap=int(params["rally_gap_s"] * fps)), breaks, v_eff)
    # Where each wide-view stretch starts (video start or a cut back to the court).
    view_starts = [0] + [i for i in range(1, n) if wide[i] and (not wide[i - 1] or i in cuts)]
    for s, e in segs:
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
        vs = max([b for b in view_starts if b <= s], default=0)
        joined = s - vs < int(0.5 * fps)
        after = e + 1
        cut_end = after < n and (after in cuts or not wide[min(n - 1, after + 2)] or any(c in cuts for c in range(after, after + 3)))
        rallies.append(_analyse_rally(s, e, sh, players, court, fps, mode, params, joined, cut_end))

    for i, r in enumerate(rallies):
        r["i"] = i
    return rallies, candidates, params


def _analyse_rally(s, e, sh, players, court, fps, mode, params, joined=False, cut_end=False):
    v, x, y = sh["v"], sh["x"], sh["y"]
    court_h = params["court_height_px"]
    land_f, settled = _landing_frame(x, y, s, e, fps, params["still_px"])
    e2 = land_f                                           # drop the stationary tail
    xs, ys = _fill(x[s:e2 + 1]), _fill(y[s:e2 + 1])
    win = params["smooth_window_frames"]
    ysm = savgol_filter(ys, win, 2) if len(ys) > win else ys.copy()

    # Contact detector. A racket contact snaps the shuttle's velocity in a frame or two;
    # the top of a lift or clear is a smooth curve. So a hit is a sharp change between the
    # average velocity just before and just after a frame, with a player's hand at the shuttle.
    k = 2
    vx, vy = np.diff(xs), np.diff(ys)
    snap = np.zeros(len(xs))                   # velocity change, court heights per second
    for t in range(k, len(xs) - k):
        bx, by = vx[t - k:t].mean(), vy[t - k:t].mean()
        ax, ay = vx[t:t + k].mean(), vy[t:t + k].mean()
        snap[t] = np.hypot(ax - bx, ay - by) / court_h * fps
    peaks, props = find_peaks(snap, height=params["contact_weak"], distance=max(2, int(0.2 * fps)))

    hits_raw, rejected = [], []
    for i, h in zip(peaks, props["peak_heights"]):
        ratio, side, pl, d_px = _hand_ratio(players, s + int(i), float(xs[i]), float(ys[i]))
        ok = (h >= params["contact_strong"] and ratio <= params["hand_strong"]) or ratio <= params["hand_weak"]
        rec = {"i": int(i), "f": int(s + i), "strength": round(float(h), 2), "hand_ratio": _r(ratio if ratio < 9 else None),
               "side": side, "pl": pl, "hand_px": d_px}
        if ok:
            hits_raw.append(rec)
        else:
            rec["reason"] = "no hand near the shuttle" if ratio > params["hand_strong"] else "too weak for how far the hand was"
            rejected.append(rec)
    # Two contacts can't be closer than the minimum gap: keep the sharper one.
    kept, merged = [], []
    for hrec in hits_raw:
        if kept and hrec["i"] - kept[-1]["i"] < int(params["hit_min_gap_s"] * fps):
            loser = hrec if hrec["strength"] <= kept[-1]["strength"] else kept[-1]
            merged.append({"f": loser["f"], "side": loser["side"], "strength": loser["strength"]})
            if hrec["strength"] > kept[-1]["strength"]:
                kept[-1] = hrec
        else:
            kept.append(hrec)
    if not kept:                                 # always at least one shot per rally
        j = int(np.argmax(snap))
        ratio, side, pl, d_px = _hand_ratio(players, s + j, float(xs[j]), float(ys[j]))
        kept = [{"i": j, "f": s + j, "strength": round(float(snap[j]), 2), "hand_ratio": None, "side": side, "pl": pl, "hand_px": d_px}]

    # How did the rally start? A serve starts from a shuttle held still in the server's hand.
    k0 = max(2, int(0.2 * fps))
    still_start = len(xs) > k0 and np.hypot(xs[k0] - xs[0], ys[k0] - ys[0]) < 2 * params["still_px"]
    start_reason = "serve" if still_start else "joined mid-rally" if joined else "shuttle appeared"

    # The same side can't play twice within DOUBLE_GAP: that's one contact seen twice.
    # Drop the weaker, re-label, and repeat until none remain.
    DOUBLE_GAP = int(0.35 * fps)
    while True:
        sides = _assign_sides(kept, xs, ys, court, players, s)
        dup = [t for t in range(1, len(kept))
               if sides[t] == sides[t - 1] and kept[t]["i"] - kept[t - 1]["i"] <= DOUBLE_GAP]
        if not dup:
            break
        t = dup[0]
        loser = t if kept[t]["strength"] <= kept[t - 1]["strength"] else t - 1
        merged.append({"f": kept[loser]["f"], "side": sides[loser], "strength": kept[loser]["strength"],
                       "reason": "same side twice within 0.35 s"})
        del kept[loser]
    hits = []
    for n_, hrec in enumerate(kept):
        i = hrec["i"]
        side = sides[n_]
        if hrec["pl"] is not None and hrec["pl"]["side"] != side:
            # The nearest hand belonged to the other team (they overlap in the picture):
            # credit the closest player on the side that actually played it.
            ratio, _, pl, d_px = _hand_ratio({k_: [q for q in v_ if q["side"] == side] for k_, v_ in
                                               ((g, players.get(g, [])) for g in range(hrec["f"] - 1, hrec["f"] + 2))},
                                              hrec["f"], float(xs[i]), float(ys[i]))
            hrec = dict(hrec, pl=pl, hand_px=d_px, hand_ratio=_r(ratio if ratio < 9 else None))
        hits.append({"f": hrec["f"], "side": side, "px": [round(float(xs[i]), 1), round(float(ys[i]), 1)],
                     "strength": hrec["strength"], "hand_ratio": hrec["hand_ratio"],
                     "serve": n_ == 0 and start_reason == "serve",
                     "player": hrec["pl"]["id"] if hrec["pl"] else None,
                     "court": hrec["pl"]["court"] if hrec["pl"] else None,
                     "hand_dist_px": hrec["hand_px"]})
    # Same side twice in a row with a normal gap: the other side's shot in between was missed.
    missed = [{"f": (a["f"] + b["f"]) // 2, "after": a["f"], "before": b["f"], "side": OTHER[a["side"]]}
              for a, b in zip(hits, hits[1:]) if a["side"] == b["side"]]
    same_side = len(missed)
    below = [{"f": r_["f"], "strength": r_["strength"], "hand_ratio": r_["hand_ratio"], "reason": r_["reason"]}
             for r_ in rejected if r_["reason"].startswith("too weak")]
    wobbles = [{"f": r_["f"], "strength": r_["strength"], "hand_ratio": r_["hand_ratio"], "reason": r_["reason"]}
               for r_ in rejected if r_["reason"].startswith("no hand")]

    lx, ly = (x[land_f], y[land_f]) if not np.isnan(x[land_f]) else (x[e], y[e])
    cx, cy = court.to_court([[lx, ly]])[0]
    # The floor projection only means something if the shuttle was near the floor. A last
    # sighting high in the air (lights, out of frame, camera cut) projects far off the court.
    plausible = -2.0 <= cx <= COURT_W + 2.0 and -3.0 <= cy <= 16.4
    # If the camera cut away before the shuttle came to rest, it was still in the air:
    # its floor projection isn't where it landed.
    if cut_end and not settled:
        plausible = False
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
        "hits": hits, "shots": len(hits), "shots_estimated": len(hits) + len(missed), "missed": missed, "server_side": hits[0]["side"] if hits[0]["serve"] else None,
        "shot_metrics": shots, "start_reason": start_reason,
        "end_reason": "landed" if settled and plausible else "camera cut away" if cut_end else "shuttle lost from view",
        "landing": landing, "winner_side": winner, "how": how,
        "confidence": "high" if settled and plausible and len(hits) >= 2 else "low",
        "movement": _movement(players, s, e2, fps),
        "tracking": {"frames": int(e2 - s + 1), "detected": int(sh["raw_v"][s:e2 + 1].sum()),
                     "filled": int(sh["filled"][s:e2 + 1].sum()), "outliers": int(sh["outlier"][s:e2 + 1].sum())},
        "signal": {"y_smooth": [round(float(a), 1) for a in ysm[::step]],
                   "speed_px_s": [round(float(a)) for a in speed[::step]],
                   "snap": [round(float(a), 2) for a in snap[::step]],
                   "below_threshold": below, "merged": merged, "wobbles": wobbles,
                   "same_side_pairs": same_side},
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

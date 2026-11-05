#!/usr/bin/env python3
"""Routes between two neighbouring Valhalla packs by joining a route in each pack at a road both contain.

Usage: check_pack_join.py A.tar B.tar lat,lon lat,lon [...more trips]
Prints, per border point tried: the point, the gap between the two routes, length and time.
"""
import json
import math
import re
import sys
import tarfile
import urllib.request

from valhalla import Actor, get_config

TILE = re.compile(r"(?:^|/)2/((?:\d{3}/)*\d{3})\.gph$")
SIZE = 0.25
COLS = 1440


def tiles(path):
    with tarfile.open(path) as t:
        return {int(m.group(1).replace("/", "")) for m in (TILE.search(n) for n in t.getnames()) if m}


def centre(tile):
    row, col = divmod(tile, COLS)
    return (row * SIZE - 90 + SIZE / 2, col * SIZE - 180 + SIZE / 2)


def km(a, b):
    la, lb = math.radians(a[0]), math.radians(b[0])
    h = math.sin((lb - la) / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def candidates(a, b, start, end, count=8):
    """Tiles only in B that touch a tile of both (the nearest road of A to such a point lies at A's outer edge, inside B),
    and the shared tiles themselves: an outer tile can be open sea (Koper-Rijeka), a shared one has roads of both packs."""
    shared = a & b
    found = set(shared)
    for tile in shared:
        for d_row in (-1, 0, 1):
            for d_col in (-1, 0, 1):
                n = tile + d_row * COLS + d_col
                if n in b and n not in a:
                    found.add(n)
    points = sorted((centre(t) for t in found), key=lambda c: km(start, c) + km(c, end))
    kept = []
    for p in points:
        if all(km(p, k) >= 20 for k in kept):
            kept.append(p)
        if len(kept) == count:
            break
    return len(shared), kept


def route(actor, start, end):
    body = {"locations": [{"lat": start[0], "lon": start[1]}, {"lat": end[0], "lon": end[1]}], "costing": "auto",
            "format": "osrm", "shape_format": "geojson", "directions_type": "none"}
    try:
        answer = actor.route(json.dumps(body))
    except Exception as e:
        return None, str(e)[:90]
    r = json.loads(answer) if isinstance(answer, str) else answer
    if r.get("code") != "Ok":
        return None, str(r)[:90]
    best = r["routes"][0]
    return {"points": [(c[1], c[0]) for c in best["geometry"]["coordinates"]], "km": best["distance"] / 1000, "min": best["duration"] / 60}, None


def trimmed(a, b):
    """Metres of spur removed where the end of A and the start of B run over the same road."""
    lengths_a, lengths_b = [0.0], [0.0]
    for p, q in zip(a[::-1], a[::-1][1:]):
        lengths_a.append(lengths_a[-1] + km(p, q))
    for p, q in zip(b, b[1:]):
        lengths_b.append(lengths_b[-1] + km(p, q))
    best = 0.0
    for i, p in enumerate(a[::-1]):
        if lengths_a[i] > 8:
            break
        for j, q in enumerate(b):
            if lengths_b[j] > 8:
                break
            if km(p, q) <= 0.015:
                best = max(best, lengths_a[i] + lengths_b[j])
    return best


def osrm_km(start, end):
    url = f"https://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=false"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pack-join-check"})
        with urllib.request.urlopen(req, timeout=30) as f:
            r = json.load(f)["routes"][0]
            return r["distance"] / 1000, r["duration"] / 60
    except Exception as e:
        print("  reference route failed:", e)
        return None


def actor(path):
    return Actor(get_config(tile_extract=path, verbose=False))


def main():
    path_a, path_b = sys.argv[1:3]
    tiles_a, tiles_b = tiles(path_a), tiles(path_b)
    actor_a, actor_b = actor(path_a), actor(path_b)
    print(f"{path_a}: {len(tiles_a)} tiles, {path_b}: {len(tiles_b)} tiles")
    args = sys.argv[3:]
    for s, e in zip(args[::2], args[1::2]):
        start = tuple(map(float, s.split(",")))
        end = tuple(map(float, e.split(",")))
        shared, points = candidates(tiles_a, tiles_b, start, end)
        print(f"TRIP {start} -> {end}: straight {km(start, end):.0f} km, {shared} shared tiles, {len(points)} border points")
        reference = osrm_km(start, end)
        if reference:
            print(f"  reference {reference[0]:.0f} km {reference[1]:.0f} min")
        for c in points:
            leg_a, error = route(actor_a, start, c)
            if not leg_a:
                print(f"  {c}: A failed: {error}")
                continue
            joint = leg_a["points"][-1]
            leg_b, error = route(actor_b, joint, end)
            if not leg_b:
                print(f"  {c}: A ends {joint} after {leg_a['km']:.0f} km, B failed: {error}")
                continue
            gap = km(joint, leg_b["points"][0]) * 1000
            spur = trimmed(leg_a["points"], leg_b["points"])
            print(f"  {c}: joint {joint} snapped {km(c, joint):.1f} km away, gap {gap:.0f} m, "
                  f"total {leg_a['km'] + leg_b['km']:.0f} km {leg_a['min'] + leg_b['min']:.0f} min, spur {spur:.1f} km")


if __name__ == "__main__":
    main()

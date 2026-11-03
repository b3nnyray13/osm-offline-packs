"""Vehicle restriction tiles for one country from a Geofabrik .osm.pbf (ODbL).

Selects ways and nodes with physical or legal limits for heavy vehicles (height, weight, width, length, axle load,
hgv/goods/hazmat access) and for all motor vehicles (no access, pedestrian zones), and writes Overpass-shaped JSON
tiles of 0.25 degrees: heavy/<s_w_n_e>.json and car/<s_w_n_e>.json.

Usage: python scripts/build_restriction_pack.py <country.osm.pbf> <ISO> <out_dir>
Output: <out_dir>/<ISO>-restrictions.zip plus <ISO>-restrictions.receipt.json
"""
import hashlib, json, math, os, re, sys, time, zipfile
import osmium

TILE = 0.25
MAX_KEY = re.compile(r"^max(height|weight|width|length|axleload)(:physical|:hgv)?$")
HAZMAT_KEY = re.compile(r"^hazmat(:[A-E]|:adr_tunnel_cat)?$")
CAR_ACCESS_ROADS = {"residential", "unclassified", "tertiary", "secondary", "living_street"}
KEEP = {"highway", "name", "ref", "maxweightrating:hgv", "hgv", "goods", "motor_vehicle", "motorcar", "access",
        "covered", "tunnel", "toll", "lanes"}


def car_part(t):
    return (t.get("motor_vehicle") in ("no", "private") or t.get("motorcar") in ("no", "private")
            or t.get("highway") == "pedestrian"
            or (t.get("highway") in CAR_ACCESS_ROADS and t.get("access") in ("no", "private")))


def heavy_part(t):
    return (any(MAX_KEY.match(k) and v for k, v in t.items()) or bool(t.get("maxweightrating:hgv"))
            or t.get("hgv") in ("no", "destination", "delivery") or t.get("goods") in ("no", "private")
            or any(HAZMAT_KEY.match(k) and v for k, v in t.items()))


def slim(t):
    return {k: v for k, v in t.items() if k in KEEP or MAX_KEY.match(k) or HAZMAT_KEY.match(k)}


class Collect(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.heavy, self.car = {}, {}

    def node(self, n):
        t = {k: v for k, v in n.tags}
        if any(t.get(k) for k in ("maxheight", "maxweight", "maxwidth")) and n.location.valid():
            el = {"type": "node", "id": n.id, "lat": round(n.location.lat, 6), "lon": round(n.location.lon, 6), "tags": slim(t)}
            self.heavy[("n", n.id)] = el

    def way(self, w):
        if "highway" not in w.tags:
            return
        t = {k: v for k, v in w.tags}
        car, heavy = car_part(t), heavy_part(t)
        if not (car or heavy):
            return
        geom = [{"lat": round(n.location.lat, 6), "lon": round(n.location.lon, 6)} for n in w.nodes if n.location.valid()]
        if len(geom) < 2:
            return
        el = {"type": "way", "id": w.id, "tags": slim(t), "geometry": geom}
        self.heavy[("w", w.id)] = el
        if car:
            self.car[("w", w.id)] = el


def tiles_of(el):
    pts = el["geometry"] if "geometry" in el else [el]
    la = [p["lat"] for p in pts]; lo = [p["lon"] for p in pts]
    out = set()
    for i in range(math.floor(min(la) / TILE), math.floor(max(la) / TILE) + 1):
        for j in range(math.floor(min(lo) / TILE), math.floor(max(lo) / TILE) + 1):
            out.add((i, j))
    return out


def write(zf, folder, elements):
    tiles = {}
    for el in elements.values():
        for key in tiles_of(el):
            tiles.setdefault(key, []).append(el)
    for (i, j), els in sorted(tiles.items()):
        s, w = i * TILE, j * TILE
        name = "%s/%.4f_%.4f_%.4f_%.4f.json" % (folder, s, w, s + TILE, w + TILE)
        zf.writestr(name, json.dumps({"elements": els}, ensure_ascii=False, separators=(",", ":")))
    return len(tiles)


def main():
    pbf, iso, out = sys.argv[1], sys.argv[2].upper(), sys.argv[3]
    os.makedirs(out, exist_ok=True)
    start = time.time()
    h = Collect()
    h.apply_file(pbf, locations=True, idx="flex_mem")
    path = os.path.join(out, "%s-restrictions.zip" % iso)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        th = write(zf, "heavy", h.heavy)
        tc = write(zf, "car", h.car)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    receipt = {"country": iso, "source": os.path.basename(pbf), "pbfModified": time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(pbf))),
               "heavyElements": len(h.heavy), "carElements": len(h.car), "heavyTiles": th, "carTiles": tc,
               "bytes": os.path.getsize(path), "sha256": digest, "seconds": round(time.time() - start),
               "license": "© OpenStreetMap contributors, ODbL 1.0 (Geofabrik extract)"}
    json.dump(receipt, open(os.path.join(out, "%s-restrictions.receipt.json" % iso), "w"), indent=1)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()

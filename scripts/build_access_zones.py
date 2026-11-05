"""Low-emission and limited-traffic zones of Europe from OpenStreetMap (boundary=low_emission_zone|limited_traffic_zone), one file.

Only perimeters that really close are kept, never invented across gaps. Community data: no legal validity; sticker or schedule rules are
not inferred from geometry. A zone missing here does not mean there is none.

Usage: python scripts/build_access_zones.py <out_dir>
Output: <out_dir>/access-zones-europe.geojson.gz and access-zones.receipt.json
"""
import gzip, hashlib, json, os, sys, time, urllib.parse, urllib.request
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import polygonize, unary_union

MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.openstreetmap.fr/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
QUERY = ('[out:json][timeout:600];(way["boundary"~"^(low_emission_zone|limited_traffic_zone)$"](34.5,-25,71.5,45);'
         'relation["boundary"~"^(low_emission_zone|limited_traffic_zone)$"](34.5,-25,71.5,45););out geom;')
HEADERS = {"User-Agent": "osm-offline-packs/1.0 (open data build)"}
KINDS = {"ES": "ZBE", "FR": "ZFE", "DE": "Umweltzone"}


def overpass():
    for attempt in range(3):
        for m in MIRRORS:
            try:
                req = urllib.request.Request(m, urllib.parse.urlencode({"data": QUERY}).encode(), HEADERS)
                d = json.load(urllib.request.urlopen(req, timeout=660))
                if "remark" in d and "error" in d["remark"].lower():
                    raise RuntimeError(d["remark"][:200])
                return d["elements"]
            except Exception as e:
                print("   ", m, str(e)[:120], file=sys.stderr)
        time.sleep(30)
    raise SystemExit("Overpass unavailable")


def geometry(e):
    if e["type"] == "way":
        pts = [(p["lon"], p["lat"]) for p in e.get("geometry", [])]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        if len(pts) >= 4 and Point(pts[0]).distance(Point(pts[-1])) * 111_000 <= 30:
            return Polygon(pts + [pts[0]])
        return None
    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in e.get("members", [])
             if m["type"] == "way" and m.get("role", "outer") in ("outer", "") and len(m.get("geometry", [])) >= 2]
    if not lines:
        return None
    faces = [f for f in polygonize(unary_union(lines)) if f.area * 111_000 * 78_000 >= 2_000]
    if not faces:
        return None
    g = unary_union(faces)
    return g if g.is_valid else g.buffer(0)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    here = os.path.join(os.path.dirname(__file__), "..", "data", "countries.geojson")
    outlines = [(c["properties"].get("iso", "").upper(), shape(c["geometry"])) for c in json.load(open(here, encoding="utf-8"))["features"]]
    features, seen = [], set()
    elements = overpass()
    for el in elements:
        key = "osm:%s:%s" % (el["type"], el["id"])
        if key in seen:
            continue
        t = el.get("tags", {})
        try:
            g = geometry(el)
        except Exception:
            g = None
        if g is None or g.is_empty:
            continue
        g = g.simplify(0.00005)
        c = g.representative_point()
        country = next((iso for iso, o in outlines if iso and o.contains(c)), "")
        seen.add(key)
        kind = KINDS.get(country, "LEZ") if t.get("boundary") == "low_emission_zone" else "ZTL"
        polys = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
        features.append({"type": "Feature", "id": key, "properties": {
            "id": key, "country": country, "kind": kind, "name": t.get("name") or t.get("name:en") or kind, "status": "mapped",
            "stickerConditions": [], "periods": [], "info": t.get("website", ""), "versionTime": today,
            "source": "https://www.openstreetmap.org/%s/%s" % (el["type"], el["id"]), "license": "© OpenStreetMap contributors · ODbL 1.0"},
            "geometry": mapping(polys[0]) if len(polys) == 1 else mapping(MultiPolygon(polys))})
    if len(features) < 150:
        raise SystemExit("Only %d zones: refusing to publish a broken list" % len(features))
    path = os.path.join(out, "access-zones-europe.geojson.gz")
    with gzip.GzipFile(path, "wb", mtime=0) as f:
        f.write(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")).encode())
    by = {}
    for x in features:
        by[x["properties"]["country"]] = by.get(x["properties"]["country"], 0) + 1
    receipt = {"date": today, "zones": len(features), "file": os.path.basename(path), "bytes": os.path.getsize(path),
               "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(), "license": "© OpenStreetMap contributors, ODbL 1.0", "byCountry": by}
    json.dump(receipt, open(os.path.join(out, "access-zones.receipt.json"), "w"), indent=1)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()

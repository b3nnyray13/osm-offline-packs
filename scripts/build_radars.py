"""Daily speed-camera list for Europe from OpenStreetMap (ODbL), as GeoJSON.

Source: every node tagged highway=speed_camera in the current OSM planet, read from the public QLever SPARQL
endpoint (updated from OSM continuously). A camera removed in OSM is absent from the next day's list, so a
consumer that replaces its copy each day drops cameras that no longer exist.

Usage: python scripts/build_radars.py <out_dir>
Output: <out_dir>/radars-europe.geojson.gz and <out_dir>/radars-europe.receipt.json
"""
import gzip, hashlib, json, os, sys, time, urllib.parse, urllib.request

ENDPOINT = "https://qlever.dev/api/osm-planet"
# Europe incl. Canary Islands, Iceland, Cyprus and Turkey's European side.
SOUTH, WEST, NORTH, EAST = 27.0, -32.0, 72.0, 45.0
PREFIXES = "PREFIX geo: <http://www.opengis.net/ont/geosparql#>\nPREFIX osmkey: <https://www.openstreetmap.org/wiki/Key:>\n"
# One small query per attribute: a single query with OPTIONALs takes minutes, these take seconds each.
POSITIONS = PREFIXES + 'SELECT ?n ?g WHERE { ?n osmkey:highway "speed_camera" . ?n geo:hasGeometry/geo:asWKT ?g . }'
ATTRIBUTE = PREFIXES + 'SELECT ?n ?v WHERE { ?n osmkey:highway "speed_camera" . ?n osmkey:%s ?v . }'


def fetch(query, tries=4):
    data = urllib.parse.urlencode({"query": query}).encode()
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(ENDPOINT, data=data, headers={
                "Accept": "application/qlever-results+json", "User-Agent": "osm-offline-packs/1.0 (daily speed cameras)"})
            return json.loads(urllib.request.urlopen(req, timeout=600).read())
        except Exception as e:  # network or server busy: retry later
            err = e
            time.sleep(60 * (i + 1))
    raise err


def literal(v):
    """QLever cells look like '"130"' or '"x"^^<type>' or '<iri>'."""
    if v is None:
        return None
    v = v.strip()
    if v.startswith('"'):
        return v[1:v.rfind('"')]
    return v.strip("<>")


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    features = {}
    for node, wkt in fetch(POSITIONS)["res"]:
        node, wkt = literal(node) or "", literal(wkt) or ""
        if "/node/" not in node or not wkt.upper().startswith("POINT("):
            continue
        lon, lat = (float(x) for x in wkt[6:-1].split()[:2])
        if not (SOUTH <= lat <= NORTH and WEST <= lon <= EAST):
            continue
        osm_id = node.rsplit("/", 1)[1]
        features[osm_id] = {"type": "Feature",
                            "properties": {"highway": "speed_camera", "owner_kind": "MAPPED_RADAR", "osm_id": "node/" + osm_id, "verified": today},
                            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}}
    for key in ("maxspeed", "direction", "check_date", "name", "enforcement"):
        for node, val in fetch(ATTRIBUTE % key)["res"]:
            f = features.get((literal(node) or "").rsplit("/", 1)[-1])
            if f is not None and literal(val):
                f["properties"][key] = literal(val)
    if len(features) < 10000:  # a broken answer must never replace the previous day's list
        raise SystemExit("only %d cameras; keeping the previous list" % len(features))
    body = json.dumps({"type": "FeatureCollection", "features": list(features.values())}, ensure_ascii=False, separators=(",", ":"))
    path = os.path.join(out, "radars-europe.geojson.gz")
    with gzip.GzipFile(path, "wb", mtime=0) as f:
        f.write(body.encode("utf-8"))
    raw = open(path, "rb").read()
    receipt = {"date": time.strftime("%Y-%m-%d", time.gmtime()), "cameras": len(features), "bytes": len(raw),
               "sha256": hashlib.sha256(raw).hexdigest(), "file": "radars-europe.geojson.gz",
               "license": "© OpenStreetMap contributors, ODbL 1.0"}
    json.dump(receipt, open(os.path.join(out, "radars-europe.receipt.json"), "w"), indent=1)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()

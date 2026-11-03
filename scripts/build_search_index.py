"""Offline search index (SQLite FTS4) from an OSM extract. Free data (ODbL), stdlib + osmium CLI.

Usage (Linux/WSL):  python3 scripts/build_search_index.py region.osm.pbf out.search.sqlite
Indexes named places, POIs, streets and address points; streets are de-duplicated per town.
"""
import json, os, sqlite3, subprocess, sys, tempfile

KEEP = ["n/place", "n/amenity", "n/shop", "n/tourism", "n/leisure", "n/historic", "n/railway=station", "n/aeroway=aerodrome",
        "w/amenity", "w/shop", "w/tourism", "w/leisure", "w/highway", "n/addr:housenumber", "w/addr:housenumber", "a/building"]


def centroid(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Point": return c[1], c[0]
    pts = c if t == "LineString" else (c[0] if t == "Polygon" else c[0][0])
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def main(pbf, out):
    with tempfile.TemporaryDirectory() as tmp:
        filtered = os.path.join(tmp, "f.osm.pbf"); seq = os.path.join(tmp, "f.geojsonseq")
        subprocess.run(["osmium", "tags-filter", "-o", filtered, "--overwrite", pbf, *KEEP], check=True)
        subprocess.run(["osmium", "export", "-f", "geojsonseq", "-o", seq, "--overwrite", "-x", "print_record_separator=false", filtered], check=True)
        if os.path.exists(out): os.remove(out)
        db = sqlite3.connect(out)
        db.execute("CREATE VIRTUAL TABLE places USING fts4(name, kind, city, street, number, lat UNINDEXED, lon UNINDEXED, tokenize=unicode61)")
        db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
        seen, rows = set(), 0
        with open(seq, encoding="utf-8") as f:
            for line in f:
                line = line.strip().lstrip("\x1e")
                if not line: continue
                feat = json.loads(line); p = feat.get("properties", {})
                try: lat, lon = centroid(feat["geometry"])
                except Exception: continue
                city = p.get("addr:city") or p.get("is_in:city") or ""
                street, number = p.get("addr:street", ""), p.get("addr:housenumber", "")
                if p.get("highway"):
                    if not p.get("name") or p["highway"] in ("footway", "path", "steps", "cycleway", "bus_stop", "crossing", "street_lamp"): continue
                    key = ("street", p["name"], round(lat, 2), round(lon, 2))
                    if key in seen: continue
                    seen.add(key); kind = "street"; name = p["name"]
                elif number and street:
                    kind = "address"; name = f"{street} {number}"
                elif p.get("name"):
                    kind = p.get("place") or p.get("amenity") or p.get("shop") or p.get("tourism") or p.get("leisure") or p.get("historic") or p.get("railway") or "poi"
                    name = p["name"]
                else:
                    continue
                db.execute("INSERT INTO places VALUES (?,?,?,?,?,?,?)", (name, kind, city, street, number, round(lat, 6), round(lon, 6)))
                rows += 1
        db.execute("INSERT INTO meta VALUES ('source', ?), ('license', '© OpenStreetMap contributors · ODbL 1.0'), ('rows', ?)",
                   (os.path.basename(pbf), str(rows)))
        db.execute("INSERT INTO places(places) VALUES('optimize')")
        db.commit(); db.execute("VACUUM"); db.close()
        print("rows", rows, "->", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

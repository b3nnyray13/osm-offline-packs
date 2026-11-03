"""Offline POI pack (SQLite) from an OSM extract. Free data (ODbL), stdlib + osmium CLI.

Usage (Linux/WSL):  python3 scripts/build_poi_pack.py region.osm.pbf out.pois.sqlite
Keeps the objects a navigator asks Overpass for online (fuel, charging, services and repair shops, health,
food, parking incl. HGV and motorhome places, rest areas, speed cameras, hazards, fords, level crossings).
Table elements(id, type, lat, lon, tags) with a lat/lon index; a bbox query gives back the Overpass JSON shape.
"""
import json, os, sqlite3, subprocess, sys, tempfile

KEEP = [
    "nwr/amenity=fuel,charging_station,car_repair,hospital,pharmacy,clinic,doctors,dentist,nursing_home,restaurant,cafe,fast_food,bar,pub,parking,parking_entrance,truck_stop,sanitary_dump_station",
    "nwr/highway=services,rest_area,ford", "nwr/shop=car_repair,truck,tyres", "nwr/craft=car_repair,mechanic",
    "nwr/healthcare", "nwr/tourism=caravan_site", "nwr/hazard", "nwr/ford", "n/railway=level_crossing", "n/highway=stop,give_way",
    "nwr/service:vehicle:paint", "nwr/service:vehicle:electrical", "nwr/service:vehicle:truck", "nwr/service:vehicle:truck:repair",
    "nwr/service:vehicle:tyres",
]


def centroid(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Point": return c[1], c[0]
    pts = c if t == "LineString" else (c[0] if t == "Polygon" else (c[0][0] if t == "MultiPolygon" else c[0]))
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def main(pbf, out):
    with tempfile.TemporaryDirectory() as tmp:
        filtered = os.path.join(tmp, "f.osm.pbf"); seq = os.path.join(tmp, "f.geojsonseq")
        subprocess.run(["osmium", "tags-filter", "-o", filtered, "--overwrite", pbf, *KEEP], check=True)
        subprocess.run(["osmium", "export", "-f", "geojsonseq", "-a", "type,id", "-o", seq, "--overwrite",
                        "-x", "print_record_separator=false", filtered], check=True)
        if os.path.exists(out): os.remove(out)
        db = sqlite3.connect(out)
        db.execute("CREATE TABLE elements(id INTEGER, type TEXT, lat REAL, lon REAL, tags TEXT)")
        db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
        rows, seen = 0, set()
        with open(seq, encoding="utf-8") as f:
            for line in f:
                line = line.strip().lstrip("\x1e")
                if not line: continue
                feat = json.loads(line); p = dict(feat.get("properties", {}))
                kind = {"n": "node", "w": "way", "r": "relation"}.get(str(p.pop("@type", "n"))[:1], "node")
                oid = int(p.pop("@id", 0))
                if (kind, oid) in seen: continue
                seen.add((kind, oid))
                try: lat, lon = centroid(feat["geometry"])
                except Exception: continue
                db.execute("INSERT INTO elements VALUES (?,?,?,?,?)", (oid, kind, round(lat, 7), round(lon, 7), json.dumps(p, ensure_ascii=False)))
                rows += 1
        db.execute("CREATE INDEX elements_pos ON elements(lat, lon)")
        db.execute("INSERT INTO meta VALUES ('source', ?), ('license', '© OpenStreetMap contributors · ODbL 1.0'), ('rows', ?)",
                   (os.path.basename(pbf), str(rows)))
        db.commit(); db.execute("VACUUM"); db.close()
        print("rows", rows, "->", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

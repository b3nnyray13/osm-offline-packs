"""Default legal speed limits by vehicle class for Europe, as a small TSV.

Source: the machine-readable form of https://wiki.openstreetmap.org/wiki/Default_speed_limits
(westnordost/osm-legal-default-speeds; data CC BY-SA 2.0 as the OSM wiki).

Usage: python scripts/build_legal_speeds.py <out_dir> [local_copy.json]
Output: <out_dir>/legal-speeds.tsv and <out_dir>/legal-speeds.receipt.json
Rows: country, road class (motorway, motorroad, rural, urban), tag, value.
"""
import hashlib, json, os, sys, urllib.request

URL = "https://raw.githubusercontent.com/westnordost/osm-legal-default-speeds/master/demo/distribution/legal_default_speeds.json"
EUROPE = ("AD AL AT BA BE-BRU BE-VLG BE-WAL BG BY CH CY CZ DE DK EE ES FI FR GB GB-SCT GR HR HU IE IS IT LI LT LU LV MC MD "
          "ME MK MT NL NO PL PT RO RS SE SI SK TR UA XK").split()
BASES = ("maxspeed", "maxspeed:hgv", "maxspeed:goods", "maxspeed:hazmat", "maxspeed:motorhome", "maxspeed:motorcycle")
KEEP = set(BASES) | {b + ":conditional" for b in BASES}
# Road types in order of preference for each class: the first one a country lists is used.
WANTED = {"motorway": ["motorway", "rural motorway"],
          "motorroad": ["motorroad", "rural motorroad", "motorroad with dual carriageway"],
          "rural": ["rural"], "urban": ["urban"]}


def find(entries, types, cls):
    named = {e.get("name"): e for e in entries}
    for n in WANTED[cls]:
        if n in named:
            return named[n]
    if cls in ("motorway", "motorroad"):  # country-specific names such as "Italy: Autostrada"
        needle = "motorway" if cls == "motorway" else "motorroad"
        for e in entries:
            n = e.get("name") or ""
            t = types.get(n, {})
            if ":" in n and needle in (t.get("filter", "") + t.get("fuzzyFilter", "")):
                return e
    if cls == "rural":
        return named.get(None)  # the unnamed entry is the country's general limit
    return None


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    if len(sys.argv) > 2:
        data = json.load(open(sys.argv[2], encoding="utf-8"))
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": "osm-offline-packs"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    limits, types = data["speedLimitsByCountryCode"], data["roadTypesByName"]
    rows = []
    for iso in EUROPE:
        for cls in WANTED:
            e = find(limits.get(iso, []), types, cls)
            for k, v in sorted((e or {}).get("tags", {}).items()):
                if k in KEEP:
                    rows.append("\t".join((iso, cls, k, " ".join(str(v).split()))))
    countries = {r.split("\t")[0] for r in rows}
    if len(countries) < 40:
        raise SystemExit("only %d countries; keeping the previous list" % len(countries))
    body = ("#source\t%s\trevision %s\t%s\n" % (data["meta"]["source"], data["meta"]["revisionId"], data["meta"]["timestamp"]) + "\n".join(rows) + "\n").encode("utf-8")
    path = os.path.join(out, "legal-speeds.tsv")
    open(path, "wb").write(body)
    json.dump({"date": data["meta"]["timestamp"][:10], "countries": len(countries), "file": "legal-speeds.tsv", "bytes": len(body),
               "sha256": hashlib.sha256(body).hexdigest(), "license": data["meta"]["license"]},
              open(os.path.join(out, "legal-speeds.receipt.json"), "w"), indent=1)
    print(len(rows), "rows,", len(countries), "countries,", len(body), "bytes")


if __name__ == "__main__":
    main()

"""Adds the newest radar list and restriction packs to catalog.json.

Usage: python scripts/update_catalog.py <receipts_dir>
Reads radars-europe.receipt.json and <ISO>-restrictions.receipt.json from <receipts_dir>. Each restriction pack is one
file per country, listed as the "restrictions" part of every pack (country or region) of that country.
"""
import glob, json, os, sys

REPO = os.environ.get("GITHUB_REPOSITORY", "b3nnyray13/osm-offline-packs")
BASE = "https://github.com/%s/releases/download" % REPO


def main():
    receipts = sys.argv[1]
    catalog = json.load(open("catalog.json", encoding="utf-8"))
    radar = os.path.join(receipts, "radars-europe.receipt.json")
    if os.path.exists(radar):
        r = json.load(open(radar))
        catalog["radars"] = {"date": r["date"], "cameras": r["cameras"], "hazards": r.get("hazards", 0), "file": r["file"], "bytes": r["bytes"],
                             "sha256": r["sha256"], "url": "%s/radars/%s" % (BASE, r["file"]), "license": r["license"]}
    for path in glob.glob(os.path.join(receipts, "*-restrictions.receipt.json")):
        r = json.load(open(path))
        iso = r["country"]
        if r.get("bytes", 0) <= 0:
            continue
        part = {"kind": "restrictions", "file": "%s-restrictions.zip" % iso, "bytes": r["bytes"], "sha256": r["sha256"],
                "url": "%s/restrictions-%s/%s-restrictions.zip" % (BASE, iso, iso), "osmDate": r["pbfModified"]}
        # Every European country has its pack here, also those without an offline map.
        catalog.setdefault("restrictions", {})[iso] = part
        for key, entry in catalog["countries"].items():
            if (entry.get("country") or key[:2]) != iso:
                continue
            entry["parts"] = [p for p in entry["parts"] if p.get("kind") != "restrictions"] + [part]
    with open("catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()

"""Builds one offline pack (map + routing + address search + POIs) from OpenStreetMap extracts.

Usage (Linux):  python scripts/build_offline_pack.py <id> <work_dir> <extract> [<extract> ...]
  <extract> is a Geofabrik path such as europe/belgium; several are merged into one pack (e.g. German states).
Needs: Java 21 + planetiler.jar in <work_dir>, osmium-tool, pyvalhalla 3.6.3 (env VALHALLA_PY). Output in <work_dir>/dist:
  ID.map.mbtiles (Planetiler, OpenMapTiles schema), ID.valhalla.tar, ID.search.sqlite, ID.pois.sqlite,
  files over 2 GB split into numbered chunks, and entry.json (sha256, bytes, release URLs) for catalog.json.
"""
import hashlib, json, os, shutil, subprocess, sys

REPO = os.environ.get("GITHUB_REPOSITORY", "b3nnyray13/osm-offline-packs")
HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_LIMIT = 2 * 1024 ** 3
CHUNK = 1900 * 1024 ** 2


def run(*cmd, **kw):
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def fetch(extract, target):
    url = f"https://download.geofabrik.de/{extract}-latest.osm.pbf"
    run("curl", "-fsSL", "--retry", "5", "-o", target, url)
    want = subprocess.run(["curl", "-fsSL", "--retry", "5", url + ".md5"], capture_output=True, text=True, check=True).stdout.split()[0]
    got = subprocess.run(["md5sum", target], capture_output=True, text=True, check=True).stdout.split()[0]
    if want != got: sys.exit(f"MD5 mismatch for {url}")
    return url


def main():
    pack, work, extracts = sys.argv[1].upper(), os.path.abspath(sys.argv[2]), sys.argv[3:]
    os.makedirs(work, exist_ok=True)
    pbfs, sources = [], []
    for i, e in enumerate(extracts):
        p = os.path.join(work, f"src{i}.osm.pbf"); sources.append(fetch(e, p)); pbfs.append(p)
    osm_date = subprocess.run(["osmium", "fileinfo", "-g", "header.option.osmosis_replication_timestamp", pbfs[0]],
                              capture_output=True, text=True).stdout.strip()[:10] or "unknown"
    pbf = os.path.join(work, "pack.osm.pbf")
    if len(pbfs) == 1: os.replace(pbfs[0], pbf)
    else:
        run("osmium", "merge", "-o", pbf, "--overwrite", *pbfs)
        for p in pbfs: os.remove(p)
    out = {k: os.path.join(work, f"{pack}.{k}") for k in ("map.mbtiles", "valhalla.tar", "search.sqlite", "pois.sqlite")}

    run("java", f"-Xmx{os.environ.get('PLANETILER_HEAP', '10g')}", "-jar", "planetiler.jar", "--osm-path=pack.osm.pbf",
        f"--output={pack}.map.mbtiles", "--download", "--download_dir=sources", "--force", "--nodemap-type=array", "--storage=mmap", cwd=work)
    shutil.rmtree(os.path.join(work, "data"), ignore_errors=True)

    py = os.environ.get("VALHALLA_PY", sys.executable)
    tiles = os.path.join(work, "tiles"); os.makedirs(tiles, exist_ok=True)
    cfg = subprocess.run([py, "-m", "valhalla.valhalla_build_config", "--mjolnir-tile-dir", tiles, "--mjolnir-tile-extract", out["valhalla.tar"],
                          "--mjolnir-admin", os.path.join(work, "admins.sqlite")], capture_output=True, text=True, check=True).stdout
    open(os.path.join(work, "valhalla.json"), "w").write(cfg)
    # The pyvalhalla 3.6.3 CLI wrapper does not find its executables: call them directly.
    bin_dir = subprocess.run([py, "-m", "valhalla", "print_bin_path"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
    run(os.path.join(bin_dir, "valhalla_build_admins"), "-c", "valhalla.json", pbf, cwd=work)
    run(os.path.join(bin_dir, "valhalla_build_tiles"), "-c", "valhalla.json", pbf, cwd=work)
    run("tar", "-cf", out["valhalla.tar"], "-C", tiles, ".")
    shutil.rmtree(tiles)

    run(sys.executable, os.path.join(HERE, "build_search_index.py"), pbf, out["search.sqlite"])
    run(sys.executable, os.path.join(HERE, "build_poi_pack.py"), pbf, out["pois.sqlite"])
    os.remove(pbf)

    tag = f"{pack}-{osm_date}"; base = f"https://github.com/{REPO}/releases/download/{tag}"
    dist = os.path.join(work, "dist"); os.makedirs(dist, exist_ok=True)
    parts = []
    for kind, k in (("map", "map.mbtiles"), ("routing", "valhalla.tar"), ("search", "search.sqlite"), ("pois", "pois.sqlite")):
        size, name = os.path.getsize(out[k]), f"{pack}.{k}"
        part = {"kind": kind, "file": name, "bytes": size, "sha256": sha256(out[k])}
        if size > ASSET_LIMIT:
            # One release asset is at most 2 GB: numbered chunks, the full SHA-256 checks the joined file.
            chunks = []
            with open(out[k], "rb") as f:
                for n, data in enumerate(iter(lambda: f.read(CHUNK), b"")):
                    cname = f"{name}.{n:03d}"; open(os.path.join(dist, cname), "wb").write(data)
                    chunks.append({"url": f"{base}/{cname}", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "file": cname})
            os.remove(out[k]); part["url"] = chunks[0]["url"]; part["chunks"] = chunks
        else:
            os.replace(out[k], os.path.join(dist, name)); part["url"] = f"{base}/{name}"
        parts.append(part)
    entry = {"id": pack, "version": tag, "osmDate": osm_date, "country": pack[:2], "title": os.environ.get("PACK_TITLE") or pack,
             "source": " ".join(sources), "license": "© OpenStreetMap contributors · ODbL 1.0", "parts": parts}
    json.dump(entry, open(os.path.join(work, "entry.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o: o.write(f"tag={tag}\n")
    print(f"OK {pack} {tag}: {sum(p['bytes'] for p in parts) / 1048576:.1f} MB")


if __name__ == "__main__":
    main()

# Offline OSM packs

Offline packs built from OpenStreetMap data, one per country or region. Each pack contains:

| File | Content | Built with |
|---|---|---|
| `ID.map.mbtiles` | Vector map, OpenMapTiles schema, zoom 0–14 | Planetiler 0.10.2 |
| `ID.valhalla.tar` | Routing graph (car, truck, bicycle, foot) | Valhalla 3.6.3 |
| `ID.search.sqlite` | Places, streets and addresses (FTS4) | osmium + SQLite |
| `ID.pois.sqlite` | Fuel, charging, parking, services, health, food, speed cameras, hazards | osmium + SQLite |

`catalog.json` lists every published pack with its release URL, size and SHA-256. Files larger than
2 GB are split into numbered parts (`.000`, `.001`, …) to be joined in order.

## Data and license

All data comes from [OpenStreetMap](https://www.openstreetmap.org/copyright) extracts by
[Geofabrik](https://download.geofabrik.de/).

© OpenStreetMap contributors. The data is available under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). The packs
are derived databases under the same license.

The data has not been verified on the ground.

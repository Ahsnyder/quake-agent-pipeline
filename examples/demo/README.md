# Example snapshot

This directory contains output from a successful **live USGS API + local ADK workflow** run during project preparation. It is a saved snapshot, not a live dashboard or proof of cloud storage.

- Input records: 1,789
- Retained earthquake records at magnitude 2.5+: 286
- All four ADK agents completed in the required order.
- `manifest.json` explicitly records `local_preview` and `cloud_storage_used: false`.
- Exact retrieval time, source feed timestamp and raw SHA-256 appear in the provenance fields.

Open `index.html` directly in a browser. Replay the raw snapshot from the project root with:

```bash
python -m quake_pipeline.cli --local --fixture examples/demo/raw.geojson
```

USGS documentation: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php

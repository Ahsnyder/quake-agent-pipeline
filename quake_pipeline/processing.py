"""Pure validation and aggregation functions called by the processing agent."""

from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from statistics import mean


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number")
    if not isfinite(value):
        raise ValueError("Expected a finite number")
    return float(value)


def process_feed(raw: dict, minimum_magnitude: float = 2.5) -> dict:
    """Deduplicate valid earthquake records, filter by magnitude, aggregate in UTC.

    For duplicate IDs, retain the valid record with the greatest updated timestamp.
    Missing magnitude/depth/time/coordinates are rejected, never imputed as zero.
    Negative depths are preserved because USGS may report above-datum depths.
    """
    number(minimum_magnitude)
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        raise ValueError("USGS response must be a GeoJSON FeatureCollection")
    features = raw.get("features")
    if not isinstance(features, list):
        raise ValueError("USGS response must contain a features array")

    counts = Counter(input_records=len(features), invalid=0, non_earthquake=0,
                     duplicates=0, below_threshold=0, retained=0)
    unique = {}
    for feature in features:
        try:
            if not isinstance(feature, dict):
                raise ValueError("Invalid feature")
            props = feature["properties"]
            if not isinstance(props, dict):
                raise ValueError("Invalid properties")
            if props.get("type") != "earthquake":
                counts["non_earthquake"] += 1
                continue
            event_id = feature["id"]
            if not isinstance(event_id, str) or not event_id:
                raise ValueError("Missing event ID")
            magnitude = number(props["mag"])
            time_ms = number(props["time"])
            updated_ms = number(props.get("updated", props["time"]))
            time = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
            geometry = feature["geometry"]
            if geometry.get("type") != "Point":
                raise ValueError("Expected point geometry")
            lon, lat, depth = map(number, geometry["coordinates"])
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Coordinates out of range")
            place = props.get("place")
            row = {"id": event_id, "magnitude": magnitude,
                   "time_utc": time.isoformat(), "date_utc": time.date().isoformat(),
                   "updated_ms": updated_ms, "longitude": lon, "latitude": lat,
                   "depth_km": depth, "place": place if isinstance(place, str) else "Unknown location"}
            if event_id in unique:
                counts["duplicates"] += 1
                if updated_ms <= unique[event_id]["updated_ms"]:
                    continue
            unique[event_id] = row
        except (KeyError, TypeError, ValueError, OverflowError, OSError, AttributeError):
            counts["invalid"] += 1

    rows = sorted((r for r in unique.values() if r["magnitude"] >= minimum_magnitude),
                  key=lambda r: (-r["magnitude"], r["id"]))
    counts["below_threshold"] = len(unique) - len(rows)
    counts["retained"] = len(rows)
    daily = Counter(r["date_utc"] for r in rows)
    bins = {"< 2.5": 0, "2.5 - 3.9": 0, "4.0 - 4.9": 0, "5.0 - 5.9": 0, "6.0+": 0}
    depths = {"Shallow (<70 km)": 0, "Intermediate (70-299 km)": 0, "Deep (300+ km)": 0}
    for row in rows:
        m = row["magnitude"]
        label = "< 2.5" if m < 2.5 else "2.5 - 3.9" if m < 4 else "4.0 - 4.9" if m < 5 else "5.0 - 5.9" if m < 6 else "6.0+"
        bins[label] += 1
        depth = row["depth_km"]
        depths["Shallow (<70 km)" if depth < 70 else "Intermediate (70-299 km)" if depth < 300 else "Deep (300+ km)"] += 1

    return {"schema_version": 1, "minimum_magnitude": minimum_magnitude,
            "quality": dict(counts), "summary": {
                "count": len(rows),
                "mean_magnitude": round(mean(r["magnitude"] for r in rows), 2) if rows else None,
                "max_magnitude": max((r["magnitude"] for r in rows), default=None),
                "mean_depth_km": round(mean(r["depth_km"] for r in rows), 2) if rows else None},
            "daily_counts": dict(sorted(daily.items())), "magnitude_counts": bins,
            "depth_counts": depths, "events": rows}

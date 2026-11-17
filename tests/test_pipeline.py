import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from quake_pipeline import agents
from quake_pipeline.agents import upload_artifacts
from quake_pipeline.cli import parse_config, run_pipeline
from quake_pipeline.dashboard import render_dashboard
from quake_pipeline.processing import process_feed


def feature(event_id="a", mag=3.0, updated=2000, depth=10, **props):
    return {"type": "Feature", "id": event_id,
            "properties": {"type": "earthquake", "mag": mag, "time": 1794787200000,
                           "updated": updated, "place": "Test location", **props},
            "geometry": {"type": "Point", "coordinates": [-86.1, 39.7, depth]}}


def feed(*features):
    return {"type": "FeatureCollection", "metadata": {}, "features": list(features)}


def test_quality_ledger_and_latest_revision():
    raw = feed(feature("a", 4.0, 2000), feature("a", 2.0, 3000),
               feature("b", 2.5, depth=70), feature("c", 6, depth=300),
               feature("d", None), feature("e", type="quarry blast"), None)
    result = process_feed(raw)
    assert result["quality"] == {"input_records": 7, "invalid": 2, "non_earthquake": 1,
                                 "duplicates": 1, "below_threshold": 1, "retained": 2}
    assert result["summary"] == {"count": 2, "mean_magnitude": 4.25,
                                 "max_magnitude": 6.0, "mean_depth_km": 185.0}
    assert [x["id"] for x in result["events"]] == ["c", "b"]
    assert sum(result["daily_counts"].values()) == 2
    assert sum(result["magnitude_counts"].values()) == 2
    assert result["depth_counts"]["Intermediate (70-299 km)"] == 1
    assert result["depth_counts"]["Deep (300+ km)"] == 1


@pytest.mark.parametrize("value", [None, "3.5", True, float("nan"), float("inf")])
def test_invalid_magnitude_is_not_zero(value):
    assert process_feed(feed(feature(mag=value)))["quality"]["invalid"] == 1


def test_invalid_coordinates_and_timestamp():
    bad = feature()
    bad["geometry"]["coordinates"][0] = 181
    assert process_feed(feed(bad, feature("b", time=1e30)))["quality"]["invalid"] == 2


def test_negative_depth_is_preserved_and_boundary_is_inclusive():
    result = process_feed(feed(feature(mag=2.5, depth=-1)))
    assert result["summary"]["count"] == 1
    assert result["events"][0]["depth_km"] == -1


def test_empty_feed_has_no_invented_statistics():
    result = process_feed(feed())
    assert result["summary"] == {"count": 0, "mean_magnitude": None, "max_magnitude": None, "mean_depth_km": None}


@pytest.mark.parametrize("raw", [{}, {"type": "FeatureCollection", "features": None}, []])
def test_schema_rejection(raw):
    with pytest.raises(ValueError):
        process_feed(raw)


def test_html_escapes_untrusted_locations():
    result = process_feed(feed(feature(place='<script>alert("x")</script>')))
    html = render_dashboard(result, {"source_kind": "Fixture", "retrieved_at_utc": "now",
                                   "run_id": "test", "raw_sha256": "abc"}, local=True)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "cloud storage not used" in html


def test_real_adk_orchestrates_all_stages(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(feed(feature())), encoding="utf-8")
    config = parse_config(["--local", "--fixture", str(fixture), "--output", str(tmp_path / "out")])
    manifest = asyncio.run(run_pipeline(config))
    output = Path(config["run_dir"])
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    assert [e["author"] for e in events] == ["IngestAgent", "TransformAgent", "VisualizeAgent", "StoreAgent"]
    assert manifest["status"] == "local_preview"
    assert manifest["cloud_storage_used"] is False
    assert (output / "raw.geojson").read_bytes() == fixture.read_bytes()
    for entry in manifest["artifacts"]:
        assert entry["sha256"] == hashlib.sha256((output / entry["file"]).read_bytes()).hexdigest()


def test_bad_data_stops_downstream_agents(tmp_path):
    fixture = tmp_path / "bad.json"
    fixture.write_text(json.dumps(feed(feature(mag=None))))
    config = parse_config(["--local", "--fixture", str(fixture), "--output", str(tmp_path / "out")])
    with pytest.raises(ValueError, match="Every source record"):
        asyncio.run(run_pipeline(config))
    output = Path(config["run_dir"])
    assert (output / "failure.json").exists()
    assert not (output / "index.html").exists()
    assert not (output / "manifest.json").exists()


def test_cloud_upload_preconditions_content_types_and_manifest_last(tmp_path):
    names = ["raw.geojson", "processed.json", "index.html"]
    for name in names:
        (tmp_path / name).write_bytes(b"test")
    config = {"local": False, "run_dir": str(tmp_path), "bucket": "test-bucket",
              "prefix": "pipeline", "run_id": "run-1"}
    client = MagicMock()
    bucket = client.bucket.return_value
    blobs = {}
    calls = []
    def new_blob(key):
        blob = MagicMock(size=4, generation=123)
        blob.upload_from_filename.side_effect = lambda *a, **kw: calls.append((key, kw))
        blob.upload_from_string.side_effect = lambda *a, **kw: calls.append((key, kw))
        blobs[key] = blob
        return blob
    bucket.blob.side_effect = new_blob
    manifest = upload_artifacts(config, {}, {}, client)
    assert manifest["status"] == "cloud_complete"
    assert [key.rsplit("/", 1)[1] for key, _ in calls] == names + ["manifest.json"]
    assert all(kwargs["if_generation_match"] == 0 for _, kwargs in calls)
    assert calls[2][1]["content_type"] == "text/html; charset=utf-8"
    assert all(entry["generation"] == "123" for entry in manifest["artifacts"])


def test_failed_upload_never_writes_completion_manifest(tmp_path):
    for name in ["raw.geojson", "processed.json", "index.html"]:
        (tmp_path / name).write_bytes(b"test")
    config = {"local": False, "run_dir": str(tmp_path), "bucket": "test-bucket",
              "prefix": "pipeline", "run_id": "run-1"}
    client = MagicMock()
    client.bucket.return_value.blob.return_value.upload_from_filename.side_effect = RuntimeError("Upload failed")
    with pytest.raises(RuntimeError, match="Upload failed"):
        upload_artifacts(config, {}, {}, client)
    assert not (tmp_path / "manifest.json").exists()
    client.bucket.return_value.blob.return_value.upload_from_string.assert_not_called()


def test_live_feed_retries_only_transient_errors(monkeypatch):
    attempts = []
    def handler(request):
        attempts.append(request)
        return httpx.Response(503 if len(attempts) < 3 else 200, content=b'{}')
    original = httpx.AsyncClient
    monkeypatch.setattr(agents.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    async def no_wait(_):
        pass
    monkeypatch.setattr(agents.asyncio, "sleep", no_wait)
    assert asyncio.run(agents.fetch_feed()) == b'{}'
    assert len(attempts) == 3


@pytest.mark.parametrize("args", [["--local", "--min-magnitude", "nan"], ["--bucket", "gs://bad"], ["--local", "--prefix", "../bad"]])
def test_bad_configuration_rejected(args):
    with pytest.raises(SystemExit):
        parse_config(args)

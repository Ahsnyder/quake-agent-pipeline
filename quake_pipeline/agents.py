"""Each stage is an ADK agent. SequentialAgent owns stage orchestration."""

import asyncio
import hashlib
import json
import ssl
from datetime import datetime, timezone
from pathlib import Path

import httpx
from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.events import Event, EventActions
from google.genai import types

from .dashboard import render_dashboard
from .processing import process_feed

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def stage_event(name: str, message: str, **state) -> Event:
    return Event(author=name, content=types.Content(role="model", parts=[types.Part(text=message)]),
                 actions=EventActions(state_delta=state))


async def fetch_feed() -> bytes:
    """Three bounded attempts; retry transport failures, 429, and server errors."""
    # Use the platform trust store (including managed Windows roots) and keep TLS verification enabled.
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=ssl.create_default_context()) as client:
        for attempt in range(3):
            try:
                response = await client.get(FEED_URL, headers={"User-Agent": "quake-agent-pipeline/1.0 (educational)"})
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 and exc.response.status_code < 500:
                    raise
                if attempt == 2:
                    raise
            except httpx.TransportError:
                if attempt == 2:
                    raise
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError("Feed retrieval did not complete")


class IngestAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        config = ctx.session.state["config"]
        output = Path(config["run_dir"])
        fixture = config.get("fixture")
        raw_bytes = Path(fixture).read_bytes() if fixture else await fetch_feed()
        raw = json.loads(raw_bytes)
        if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection" or not isinstance(raw.get("features"), list):
            raise ValueError("Source must be a GeoJSON FeatureCollection with a features array")
        (output / "raw.geojson").write_bytes(raw_bytes)
        provenance = {"run_id": config["run_id"], "source_url": FEED_URL,
                      "source_kind": "Fixture (offline)" if fixture else "Live API",
                      "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                      "feed_generated_ms": raw.get("metadata", {}).get("generated"),
                      "raw_sha256": hashlib.sha256(raw_bytes).hexdigest()}
        yield stage_event(self.name, f"Ingested {len(raw['features'])} records.",
                          raw_path=str(output / "raw.geojson"), provenance=provenance)


class TransformAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        state = ctx.session.state
        config = state["config"]
        raw = json.loads(Path(state["raw_path"]).read_bytes())
        processed = process_feed(raw, config["minimum_magnitude"])
        # A nonempty feed that yields only invalid records is a hard failure.
        q = processed["quality"]
        if q["input_records"] and q["invalid"] == q["input_records"]:
            raise ValueError("Every source record is invalid; refusing to publish a misleading empty report")
        path = Path(config["run_dir"]) / "processed.json"
        processed["provenance"] = dict(state["provenance"])
        write_json(path, processed)
        yield stage_event(self.name, f"Retained {q['retained']} events; excluded {q['invalid']} invalid records.",
                          processed_path=str(path), quality=q)


class VisualizeAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        state = ctx.session.state
        processed = json.loads(Path(state["processed_path"]).read_text(encoding="utf-8"))
        path = Path(state["config"]["run_dir"]) / "index.html"
        path.write_text(render_dashboard(processed, state["provenance"], state["config"]["local"]), encoding="utf-8")
        yield stage_event(self.name, "Built a self-contained HTML dashboard.", dashboard_path=str(path))


def upload_artifacts(config: dict, provenance: dict, quality: dict, client=None) -> dict:
    """Upload immutable objects and a manifest last. No public bucket ACL changes."""
    output = Path(config["run_dir"])
    artifact_types = {"raw.geojson": "application/geo+json", "processed.json": "application/json",
                      "index.html": "text/html; charset=utf-8"}
    manifest = {"status": "local_preview" if config["local"] else "cloud_complete",
                "cloud_storage_used": not config["local"], "provenance": provenance,
                "quality": quality, "artifacts": []}
    bucket = None
    if not config["local"]:
        if client is None:
            from google.cloud import storage
            client = storage.Client(project=config.get("project") or None)
        bucket = client.bucket(config["bucket"])
    for filename, content_type in artifact_types.items():
        path = output / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entry = {"file": filename, "sha256": digest, "bytes": path.stat().st_size,
                 "content_type": content_type}
        if bucket is not None:
            key = f"{config['prefix']}/{config['run_id']}/{filename}"
            blob = bucket.blob(key)
            blob.metadata = {"sha256": digest, "run_id": config["run_id"]}
            blob.upload_from_filename(str(path), content_type=content_type,
                                      if_generation_match=0, checksum="auto", timeout=60)
            blob.reload(timeout=30)
            if blob.size != entry["bytes"]:
                raise RuntimeError(f"Size verification failed for {filename}")
            entry.update(uri=f"gs://{config['bucket']}/{key}", generation=str(blob.generation))
        manifest["artifacts"].append(entry)
    if bucket is not None:
        # This object is the completion marker: partial runs never receive it.
        key = f"{config['prefix']}/{config['run_id']}/manifest.json"
        manifest["manifest_uri"] = f"gs://{config['bucket']}/{key}"
        bucket.blob(key).upload_from_string(json.dumps(manifest, indent=2), content_type="application/json",
                                           if_generation_match=0, checksum="auto", timeout=60)
    write_json(output / "manifest.json", manifest)
    return manifest


class StoreAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        state = ctx.session.state
        manifest = await asyncio.to_thread(upload_artifacts, state["config"], dict(state["provenance"]), dict(state["quality"]))
        message = "Local preview saved; no cloud upload performed." if state["config"]["local"] else "Cloud uploads verified; completion manifest saved."
        yield stage_event(self.name, message, manifest=manifest)


def build_pipeline() -> SequentialAgent:
    # ADK, rather than the CLI, schedules these agents and propagates their events.
    return SequentialAgent(name="EarthquakePipeline", sub_agents=[
        IngestAgent(name="IngestAgent", description="Fetch and validate the source snapshot."),
        TransformAgent(name="TransformAgent", description="Clean, deduplicate, filter and aggregate."),
        VisualizeAgent(name="VisualizeAgent", description="Create the standalone report."),
        StoreAgent(name="StoreAgent", description="Persist and verify cloud objects, or label a local preview."),
    ])

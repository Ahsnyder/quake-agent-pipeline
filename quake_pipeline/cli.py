"""Configure and invoke the ADK runner; no pipeline stages run here directly."""

import argparse
import asyncio
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agents import build_pipeline, write_json


async def run_pipeline(config: dict) -> dict:
    output = Path(config["run_dir"])
    output.mkdir(parents=True, exist_ok=False)
    sessions = InMemorySessionService()
    await sessions.create_session(app_name="quake_pipeline", user_id="student",
                                  session_id=config["run_id"], state={"config": config})
    runner = Runner(agent=build_pipeline(), app_name="quake_pipeline", session_service=sessions)
    try:
        with (output / "events.jsonl").open("w", encoding="utf-8") as log:
            async for event in runner.run_async(user_id="student", session_id=config["run_id"],
                new_message=types.Content(role="user", parts=[types.Part(text="Run the earthquake pipeline.")])):
                if event.error_code:
                    raise RuntimeError(f"ADK event failed: {event.error_code}: {event.error_message}")
                # Log summaries and changed key names, not the complete source data.
                text = " ".join(p.text for p in event.content.parts if p.text) if event.content else ""
                item = {"author": event.author, "timestamp": event.timestamp, "message": text,
                        "state_keys": sorted(event.actions.state_delta)}
                log.write(json.dumps(item) + "\n")
                log.flush()
                print(f"[{event.author}] {text}")
        session = await sessions.get_session(app_name="quake_pipeline", user_id="student", session_id=config["run_id"])
        if session is None or "manifest" not in session.state:
            raise RuntimeError("Workflow stopped before the storage agent completed")
        return dict(session.state["manifest"])
    except Exception as exc:
        write_json(output / "failure.json", {"status": "failed", "error_type": type(exc).__name__,
                   "message": str(exc), "run_id": config["run_id"]})
        raise


def parse_config(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Run a four-agent Google ADK earthquake pipeline.")
    parser.add_argument("--local", action="store_true", help="Explicit local preview; does not satisfy cloud storage requirement")
    parser.add_argument("--fixture", type=Path, help="Offline GeoJSON input instead of calling the live API")
    parser.add_argument("--bucket", default=os.getenv("GCS_BUCKET"), help="Existing private GCS bucket name")
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--prefix", default="earthquake-pipeline", help="Object key prefix within the bucket")
    parser.add_argument("--min-magnitude", type=float, default=2.5)
    parser.add_argument("--output", type=Path, default=Path("out"), help="Parent folder for unique run directories")
    args = parser.parse_args(argv)
    if not math.isfinite(args.min_magnitude) or not -2 <= args.min_magnitude <= 10:
        parser.error("--min-magnitude must be a finite number between -2 and 10")
    if not args.local and not args.bucket:
        parser.error("Cloud mode requires --bucket or GCS_BUCKET. Use --local only for a preview.")
    if args.local and args.bucket:
        parser.error("Use either --local or a cloud bucket; clear GCS_BUCKET for a local preview.")
    if args.bucket and (args.bucket.startswith("gs://") or "/" in args.bucket):
        parser.error("--bucket expects only a bucket name, without gs:// or a path")
    prefix = args.prefix.strip("/")
    if not prefix or any(p in (".", "..") for p in prefix.split("/")):
        parser.error("--prefix must be a nonempty object prefix without dot path segments")
    if args.fixture and not args.fixture.is_file():
        parser.error("--fixture does not name an existing file")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    return {"run_id": run_id, "run_dir": str((args.output / run_id).resolve()),
            "local": args.local, "bucket": args.bucket, "project": args.project,
            "prefix": prefix, "minimum_magnitude": args.min_magnitude,
            "fixture": str(args.fixture.resolve()) if args.fixture else None}


def main(argv=None):
    config = parse_config(argv)
    try:
        manifest = asyncio.run(run_pipeline(config))
    except Exception as exc:
        print(f"FAILED: {exc}\nDiagnostic files: {config['run_dir']}", file=sys.stderr)
        return 1
    print(f"Status: {manifest['status']}\nDashboard: {Path(config['run_dir']) / 'index.html'}")
    if manifest.get("manifest_uri"):
        print(f"Cloud completion marker: {manifest['manifest_uri']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

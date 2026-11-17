Public repository: https://github.com/Ahsnyder/quake-agent-pipeline

# Future improvements

## Current pipeline

Four Google ADK agents ingest the public USGS feed, validate and aggregate earthquake records, generate a standalone HTML dashboard, and upload raw data, processed data and HTML to Google Cloud Storage. The deterministic workflow uses no LLM API key. The code includes cloud upload verification, immutable run prefixes, provenance and offline tests.

The live API/local ADK workflow and 21 automated tests were verified. The public repository URL appears above. A real GCS run remains incomplete: the configured Google Cloud project reports billing disabled. Local preview files are not evidence of cloud storage.

## 1. Recovery and error handling

The pipeline already retries transient API failures, stops downstream agents on errors, and uploads the completion manifest last. Add resumable stage checkpoints, jitter and Retry-After handling, plus a cleanup policy for incomplete cloud runs. Test recovery after each upload boundary so retries do not create duplicate datasets.

## 2. Scalability and storage

The current weekly snapshot is processed in memory. For larger catalogs, ingest incremental time windows, partition objects by event date, and store typed Parquet files. Pass artifact references between agents and use a warehouse for long-term analysis. Reprocess updated USGS event IDs to capture revisions.

## 3. Monitoring and data quality

Build on the existing run IDs, hashes, exclusion counts and event logs. Publish stage latency, record counts, invalid-record rate and last-success time to Cloud Monitoring. Alert on stale feed timestamps, unexpected empty feeds and volume changes; use thresholds appropriate to each feed rather than assuming uniform global coverage.

## 4. Scheduling and reproducible operation

Package the application as a Cloud Run Job triggered by Cloud Scheduler, using UTC schedules and an attached service identity. Prevent overlapping runs, track deployment versions in manifests, and retain a last-success pointer. Add a scheduled end-to-end check that verifies the live API and private bucket together.

## 5. Testing and dependency maintenance

The included offline tests cover processing, ADK handoffs, retries and simulated cloud writes. Add real GCS integration tests in a dedicated test project, especially IAM denial, checksum failures and interrupted uploads. Keep pinned dependencies under automated review and verify upgrades on every supported Python version.

## 6. Security and cost control

Continue using Application Default Credentials and private buckets. In production, use workload identity and a narrowly scoped custom role for object creation and verification. Add secret scanning, budget alerts and lifecycle rules to expire raw snapshots and abandoned runs. Set retention deliberately before adding archival storage classes.

## 7. Agent workflow and report usability

ADK 2.14.1 still provides SequentialAgent, but marks it deprecated. Migrate to the newer Workflow graph interface with explicit validation and recovery branches, preserving event-level auditability. Add date and magnitude controls, accessible chart alternatives, and a map. An optional LLM agent could explain results, grounded only in verified aggregates.

## References

- [USGS GeoJSON feed](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)
- [ADK workflow agents](https://adk.dev/agents/workflow-agents/sequential-agents/)
- [Cloud Storage uploads](https://docs.cloud.google.com/storage/docs/uploading-objects-from-memory)

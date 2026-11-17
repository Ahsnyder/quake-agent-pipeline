"""Build the short submission PDF and its Markdown source; no cloud credentials."""

import argparse
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parents[1]

IMPROVEMENTS = [
    ("1. Recovery and error handling", "The pipeline already retries transient API failures, stops downstream agents on errors, and uploads the completion manifest last. Add resumable stage checkpoints, jitter and Retry-After handling, plus a cleanup policy for incomplete cloud runs. Test recovery after each upload boundary so retries do not create duplicate datasets."),
    ("2. Scalability and storage", "The current weekly snapshot is processed in memory. For larger catalogs, ingest incremental time windows, partition objects by event date, and store typed Parquet files. Pass artifact references between agents and use a warehouse for long-term analysis. Reprocess updated USGS event IDs to capture revisions."),
    ("3. Monitoring and data quality", "Build on the existing run IDs, hashes, exclusion counts and event logs. Publish stage latency, record counts, invalid-record rate and last-success time to Cloud Monitoring. Alert on stale feed timestamps, unexpected empty feeds and volume changes; use thresholds appropriate to each feed rather than assuming uniform global coverage."),
    ("4. Scheduling and reproducible operation", "Package the application as a Cloud Run Job triggered by Cloud Scheduler, using UTC schedules and an attached service identity. Prevent overlapping runs, track deployment versions in manifests, and retain a last-success pointer. Add a scheduled end-to-end check that verifies the live API and private bucket together."),
    ("5. Testing and dependency maintenance", "The included offline tests cover processing, ADK handoffs, retries and simulated cloud writes. Add real GCS integration tests in a dedicated test project, especially IAM denial, checksum failures and interrupted uploads. Keep pinned dependencies under automated review and verify upgrades on every supported Python version."),
    ("6. Security and cost control", "Continue using Application Default Credentials and private buckets. In production, use workload identity and a narrowly scoped custom role for object creation and verification. Add secret scanning, budget alerts and lifecycle rules to expire raw snapshots and abandoned runs. Set retention deliberately before adding archival storage classes."),
    ("7. Agent workflow and report usability", "ADK 2.14.1 still provides SequentialAgent, but marks it deprecated. Migrate to the newer Workflow graph interface with explicit validation and recovery branches, preserving event-level auditability. Add date and magnitude controls, accessible chart alternatives, and a map. An optional LLM agent could explain results, grounded only in verified aggregates."),
]

CURRENT = ("Four Google ADK agents ingest the public USGS feed, validate and aggregate earthquake records, "
           "generate a standalone HTML dashboard, and upload raw data, processed data and HTML to Google Cloud Storage. "
           "The deterministic workflow uses no LLM API key. The code includes cloud upload verification, "
           "immutable run prefixes, provenance and offline tests.")
STATUS = ("Prepared locally at the user's request. The live API/local workflow and 21 automated tests were verified. "
          "A real GCS upload and public repository publication remain required before final submission. "
          "The included local preview is not evidence of cloud storage.")
SOURCES = [
    ("USGS GeoJSON feed", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php"),
    ("ADK workflow agents", "https://adk.dev/agents/workflow-agents/sequential-agents/"),
    ("Cloud Storage uploads", "https://docs.cloud.google.com/storage/docs/uploading-objects-from-memory"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-url", help="Actual public HTTPS repository URL, after publication")
    args = parser.parse_args()
    url = args.repo_url
    if url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or not parsed.path.strip("/"):
            parser.error("Use the actual public HTTPS repository URL, without credentials")
        if "YOUR_" in url.upper() or "example.com" in url.lower():
            parser.error("Replace placeholder text with the actual public repository URL")
    repo_text = url or "Pending publication - local preparation requested"
    status = STATUS if not url else (
        "The live API/local ADK workflow and 21 automated tests were verified. "
        "The public repository URL appears above. A real GCS run remains incomplete: "
        "the configured Google Cloud project reports billing disabled. Local preview files "
        "are not evidence of cloud storage.")
    md = [f"Public repository: {repo_text}", "", "# Future improvements", "", "## Current pipeline", "", CURRENT, "", status, ""]
    for title, body in IMPROVEMENTS:
        md.extend([f"## {title}", "", body, ""])
    md.extend(["## References", ""] + [f"- [{name}]({link})" for name, link in SOURCES])
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "future_improvements.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    output = ROOT / "output" / "pdf" / "future_improvements.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)

    ink, teal, muted = colors.HexColor("#132a30"), colors.HexColor("#087f75"), colors.HexColor("#526970")
    normal = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.3, leading=12.1, textColor=ink, spaceAfter=7)
    heading = ParagraphStyle("Heading", parent=normal, fontName="Helvetica-Bold", fontSize=10.1, leading=13, spaceBefore=4, spaceAfter=3)
    title_style = ParagraphStyle("Title", parent=normal, fontName="Helvetica-Bold", fontSize=25, leading=29, spaceAfter=5)
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=10.5, textColor=muted)
    label = ParagraphStyle("Label", parent=small, fontName="Helvetica-Bold", textColor=teal, spaceAfter=10)
    doc = SimpleDocTemplate(str(output), pagesize=(8.5*inch, 11*inch), rightMargin=45, leftMargin=45,
                            topMargin=33, bottomMargin=34, title="Seismic - Future Improvements", author="Quake Agent Pipeline")
    repo_line = f'PUBLIC REPOSITORY: <link href="{escape(url, quote=True)}" color="#087f75">{escape(url)}</link>' if url else f"PUBLIC REPOSITORY: {repo_text}"
    story = [Paragraph(repo_line, label), Paragraph("Future improvements", title_style),
             Paragraph("SEISMIC / AN ADK EARTHQUAKE PIPELINE", label),
             Paragraph(CURRENT, normal), Paragraph(status, small), Spacer(1, 7)]
    for title, body in IMPROVEMENTS:
        story.extend([Paragraph(title, heading), Paragraph(escape(body), normal)])
    story.append(Paragraph("References: " + " | ".join(f'<link href="{link}" color="#087f75">{name}</link>' for name, link in SOURCES), small))

    def footer(canvas, document):
        canvas.setStrokeColor(colors.HexColor("#dce6e2"))
        canvas.line(45, 28, 567, 28)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(muted)
        canvas.drawString(45, 17, "SEISMIC  /  Project improvement roadmap")
        canvas.drawRightString(567, 17, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == "__main__":
    main()

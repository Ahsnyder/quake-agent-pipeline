# Local validation record

Verified on November 17, 2026 with Python 3.12.14 on Windows.

- Installed every dependency from `requirements.lock` into a fresh environment, then installed the project with `--no-deps --no-build-isolation -e .`.
- Ran the full test suite in that fresh environment: **21 passed**. Two expected warnings identify ADK's deprecated SequentialAgent interface; its migration is covered in the future improvements document. An optional CI template covers Python 3.11 and 3.12, but CI is not active and Python 3.11/Linux were not checked locally.
- Ran the actual ADK workflow against the live public USGS API. Ingested 1,789 records; retained 286 magnitude-2.5+ earthquakes. All four agents completed, in order. The example report and source snapshot are preserved in `examples/demo/`.
- Replayed that snapshot offline in the fresh environment and reproduced the 286-event processed dataset through the ADK agents.
- Rendered the HTML in headless Edge at 1440-pixel desktop and 390-pixel phone widths. Visually reviewed both layouts and confirmed no page-level horizontal overflow. The events table scrolls within its own panel on small screens.
- Generated the one-page future improvements PDF, rendered it to a PNG, and visually reviewed its text and layout.
- Cloud upload tests used SDK test doubles to check content types, create-only preconditions, object generations, and absence of a completion marker after upload failure. **No real GCS upload was performed.**
- Created the public repository at https://github.com/Ahsnyder/quake-agent-pipeline and added its URL to the future improvements document.
- Verified anonymous access through GitHub's API (`private: false`) and cloned the repository without a credential helper. Ran the test suite from that published clone: **21 passed**. Verified that its raw snapshot hash matches the manifest and its PDF contains the actual repository URL.
- Verified that Google Cloud project `earthquake-class-project` is active and the Cloud Storage API is enabled. Google reports `billingEnabled: false`. Application Default Credentials were configured outside the repository; no credentials are included in the source or ZIP.
- A bucket-creation test was rejected by automatic approval review because it is potentially billable and the latest user instruction did not clearly authorize that test. No bucket was created and no real cloud run was completed. This requirement remains incomplete.
- GitHub's existing OAuth authorization did not include the workflow scope, and automatic approval review rejected expanding that persistent access. The optional CI configuration is published as `docs/ci-template.yml`, which needs no expanded permissions and does not run automatically.

The dashboard is a saved snapshot. Its exact retrieval time, feed generation timestamp and input hash appear in the generated provenance fields.

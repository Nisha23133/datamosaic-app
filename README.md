# Data Mosaic

AI-powered data mesh demo: upload CSV/JSON/XLSX attribute lists, match
them against your Knowledge Catalog, get AI-suggested metadata for
anything unmatched, approve/reject/correct with feedback logged for
future improvement, then register approved attributes as governed
Data Products.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Authenticate to GCP** (if not already done this week):
   ```bash
   gcloud auth application-default login
   gcloud config set project data-mosaic-506420
   ```

3. **Copy the env template:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` if your project/location differ from the defaults in `config.py`.
   **Also set a real API key** — add `DATAMOSAIC_API_KEY=your-secret-here` to `.env`.
   Every API call now requires this key (see `api/auth.py`); the browser
   will prompt for it once per page load. This is a lightweight demo-only
   protection — before any real deployment, replace it with proper
   identity-based auth (IAP/OAuth), since a shared static key can't
   distinguish who did what.

## Run locally

```bash
uvicorn api.main:app --reload --port 8080
```

Then open:
- **App UI:** http://127.0.0.1:8080
- **API docs (interactive):** http://127.0.0.1:8080/docs

## Project layout

```
config.py              - all project/dataset/model settings
tools/                  - reusable functions that call GCP APIs
agents/                 - ADK agent definitions built on top of tools/
api/                    - FastAPI app exposing everything to the browser
frontend/index.html     - minimal UI for upload/search/approve flow
```

## Known placeholders

`tools/catalog_client.py` has two functions (`create_data_domain`,
`register_data_product`) marked as placeholders — Knowledge Catalog's
newer Domain/Data Product resources aren't yet in the stable
`google-cloud-dataplex` client library surface as of this build. Two
options:
1. Keep creating domains/data products manually in the Console (as done
   this week), and use this app for the matching/recommendation flow only.
2. Replace the placeholder bodies with direct REST calls to the
   Dataplex Universal Catalog API using an access token from
   `google.auth.default()`.

## Troubleshooting

- **403/permission errors:** re-run `gcloud auth application-default login`.
- **BigQuery location errors:** all datasets used here should be in
  `us-central1` — same fix as the region issues hit earlier this week.
- **Vertex AI quota errors:** if using a Vertex AI-routed tool and you
  hit a 429, confirm the project is on a paid (not trial) billing account.

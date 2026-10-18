# RegMesh AI - Financial Regulatory Reporting Governance & Data Product Mesh

[![Cloud Run Deployment](https://img.shields.io/badge/Google%20Cloud-Cloud%20Run%20Deployed-success?logo=googlecloud)](https://datamosaic-app-929907480079.us-central1.run.app)
[![BigQuery Powered](https://img.shields.io/badge/BigQuery-Governance%20%26%20Lineage-blue?logo=googlebigquery)](https://cloud.google.com/bigquery)
[![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Gemini%202.5%20Flash-orange?logo=google)](https://cloud.google.com/vertex-ai)

RegMesh AI is an enterprise financial regulatory governance and data product mesh engineered for global financial institutions (G-SIBs, commercial banks, asset managers, and fintechs). It transforms complex compliance mandates into automated, mathematically verifiable data contracts that mitigate supervisory fines and penalties under:

- **BCBS 239** (Risk Data Aggregation & Risk Reporting)
- **CCAR / DFAST** (Comprehensive Capital Analysis & Review / Stress Testing)
- **MiFID II / MiFIR** (Transaction Reporting & Trade Transparency)
- **Dodd-Frank** (Swap Data & Systemic Concentration)
- **DORA** (Digital Operational Resilience Act)
- **AML / KYC** (Financial Crime, Sanctions & Legal Entity Graphs)

---

## 🏛️ 3-Persona Data Mesh Governance Model

1. **👤 Data Consumer (Risk & Compliance Analysts)**
   - **Conversational Intake Studio**: Chat with the Vertex AI Gemini agent to state business objectives in plain English.
   - **Automated 6-Dimension Extraction**: Automatically structures requirements across Description, Business Objective, Expected Penalties Avoided, Data Components (Master IDs), Compliance Rules, and Cryptographic Audit Trail.
   - **Self-Serve Regulatory Query Hub**: Natural language queries grounded in physical BigQuery schemas with interactive term suggestions.

2. **🛠️ Data Producer (Domain Data Engineers)**
   - **Review & Approval Gate**: Strict separation of duties — only Data Producers hold authority to approve use cases and publish semantic models.
   - **Semantic Contract Studio (Edit Mode)**: Review and customize dimensions, risk metrics (`SUM`, `AVG`), and Google Cloud Dataform SQLX pipelines before approving.
   - **Physical Data Product Materialization**: One-click provisioning of BigQuery analytical marts in the `curated` dataset with automatic schema alignment and dynamic compliance records.

3. **🛡️ Platform Owner (Super Admin / Chief Data Officer)**
   - **Super-Admin Governance Deck**: Audit overview, policy lifecycle enforcement, and decommissioning authority for use cases and physical data products.

---

## ☁️ Google Cloud Architecture

```
                                      ┌───────────────────────────────────────────────────────────┐
                                      │              GOOGLE CLOUD VERTEX AI                       │
                                      │  • Gemini 2.5 Flash: Autonomous Regulatory Chatbot Agent  │
                                      │  • Text Embedding 005: Vector Attribute Matching          │
                                      └─────────────────────────────┬─────────────────────────────┘
                                                                    │
┌───────────────────────────────┐                                   ▼                                   ┌───────────────────────────────┐
│     DATAPLEX CATALOG          │                         REGMESH AI APPLICATION                        │        GOOGLE CLOUD           │
│   (Knowledge Catalog)         │◄─────────────────────►    FastAPI + Mesh UI    ◄──────────────────────►│           DATAFORM            │
│ • Schema & Aspect discovery   │                           (Role-Based Access)                         │ • Standardized SQLX templates │
│ • Business glossary metadata  │                                   │                                   │ • Audit hashes & transforms   │
│ • Data classification & tags  │                                   ▼                                   └───────────────────────────────┘
└───────────────────────────────┘                     ┌───────────────────────────┐
                                                      │     GOOGLE BIGQUERY       │
                                                      │ • raw_banking (Sources)   │
                                                      │ • curated (Curated Marts) │
                                                      │ • governance (Audit Logs) │
                                                      └───────────────────────────┘
```

---

## 📁 Repository Structure

```
├── agents/
│   ├── orchestrator.py           # Front door routing agent
│   ├── regulatory_agents.py       # Gemini 2.5 Flash agents for 6-dimension intake & SQL generation
│   ├── semantic_agent.py         # Catalog matching & metadata suggestions
│   └── discovery_agent.py        # Dataset discovery
├── api/
│   ├── main.py                   # FastAPI application initialization & routing
│   ├── regulatory_routes.py      # Mesh endpoints (intake, approve, materialize, query, delete)
│   ├── routes.py                 # Core upload and attribute endpoints
│   └── auth.py                   # Role and identity helpers
├── tools/
│   ├── bigquery_client.py        # Physical DDL execution & table provisioning
│   ├── regulatory_store.py       # BigQuery governance CRUD (use cases, products, query audits)
│   ├── catalog_client.py         # Google Cloud Dataplex (Knowledge Catalog) API integration
│   ├── embeddings.py             # Vertex AI text-embedding-005 vector tools
│   └── file_parser.py            # CSV/JSON/XLSX attribute ingestion
├── frontend/
│   └── index.html                # Responsive web mesh portal (Vanilla CSS/JS, 3 Personas)
├── config.py                     # Central GCP project, dataset, and framework configurations
├── requirements.txt              # Production Python dependencies
├── Dockerfile                    # Container definition for Google Cloud Run
└── README.md                     # Technical architecture & deployment guide
```

---

## 🚀 Local Quickstart

### 1. Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure GCP Authentication
```bash
gcloud auth application-default login
gcloud config set project data-mosaic-506420
```

### 3. Launch Local Server
```bash
uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload
```
Navigate to:
- **Web Mesh Application**: [http://127.0.0.1:8080](http://127.0.0.1:8080)
- **Interactive Swagger Docs**: [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)

---

## 🌐 Google Cloud Run Deployment

Deploy directly from source using the Cloud SDK:

```bash
gcloud run deploy datamosaic-app \
  --source . \
  --region us-central1 \
  --project data-mosaic-506420 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=data-mosaic-506420,GOOGLE_CLOUD_LOCATION=us-central1
```

**Live Production URL:**
👉 https://datamosaic-app-929907480079.us-central1.run.app

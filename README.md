# SPARROW Installation Tracker

Flask-based tracking app for SPARROW deployments and development tracks. This version uses server-rendered Jinja templates in `templates/` and shared styling/assets in `static/`, replacing the earlier Streamlit UI.

The app tracks deployment status, health, deadlines, history, contacts, timeline phases, nudges, and Azure DevOps work items. It also supports optional Azure OpenAI-powered parsing for free-form updates and Q&A.

## Current Architecture

- `app.py` — Flask entry point and route definitions
- `templates/` — server-rendered HTML views
- `static/css/style.css` — shared UI styles
- `db.py` — SQLite schema and data access layer used by the running app
- `db_azure.py` — Azure SQL implementation kept alongside the SQLite layer
- `llm.py` — Azure OpenAI parsing and question-answering helpers
- `devops_sync.py` — Azure DevOps work item sync
- `monitor.py` — stale-project and deadline alert logic
- `notifications.py` — optional SMTP notification support
- `migrate_to_azure.py` — one-time SQLite to Azure SQL migration script

## Features

- Dashboard with portfolio counts, attention items, and recent activity
- Project detail pages with history, contacts, nudges, and target-date context
- Submit Update workflow for free-form text ingestion with optional LLM parsing
- Ask SPARROW endpoint for natural-language questions against current tracker data
- Timeline view for deployment and dev-track phases
- Reports and settings pages for monitoring and operational context
- Azure DevOps sync support for sprint and work item visibility

## Requirements

- Python 3.10+
- SQLite for the default local runtime
- Optional Azure OpenAI credentials for AI-assisted parsing and Q&A
- Optional Azure DevOps auth for sync features
- Optional Azure SQL credentials if you plan to migrate off SQLite

## Installation

```bash
git clone https://github.com/rmdodhia/sparrow-tracker.git
cd sparrow-tracker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root if you want any external integrations enabled.

## Environment Variables

### Optional Azure OpenAI

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-10-21
```

Without these values, the app still runs, but AI parsing and Ask SPARROW responses are disabled.

### Optional Azure DevOps

```env
AZURE_DEVOPS_ORG=onecela
AZURE_DEVOPS_PROJECT=AI For Good Lab
AZURE_DEVOPS_PAT=
DEVOPS_SPRINT_QUERY_ID=
```

If `AZURE_DEVOPS_PAT` is not set, the sync code attempts Azure AD authentication via `az login`.

### Optional Azure SQL

```env
AZURE_SQL_SERVER=
AZURE_SQL_DATABASE=
AZURE_SQL_USER=
AZURE_SQL_PASSWORD=
```

Note: the checked-in Flask app currently uses [db.py](/home/radodhia/sparrow-tracker-v2/db.py), which is SQLite-backed by default. The Azure SQL files are present for migration and parallel development work.

### Optional Email and SMTP

```env
IMAP_HOST=
IMAP_PORT=993
IMAP_USER=
IMAP_PASS=
IMAP_FOLDER=INBOX
IMAP_DONE_FOLDER=

SPARROW_SMTP_HOST=
SPARROW_SMTP_PORT=587
SPARROW_SMTP_USER=
SPARROW_SMTP_PASS=
SPARROW_NOTIFY_FROM=sparrow-tracker@noreply.local
```

## Running The App

Either of these works:

```bash
python app.py
```

or:

```bash
flask --app app run --debug --port 5001
```

Then open `http://127.0.0.1:5001`.

On startup, the app automatically initializes the SQLite schema in `sparrow_tracker.db` if it does not already exist.

## Data Initialization

This repository no longer includes the legacy Excel backlog workbook that `seed_data.py` expects. That means:

- The app can still start with an empty or existing SQLite database.
- `python seed_data.py` will only work if you supply the source workbook at the path the script expects.
- If you already have a populated `sparrow_tracker.db`, the app will use it directly.

## Azure SQL Migration

If you want to copy your existing SQLite data into Azure SQL:

```bash
python migrate_to_azure.py
```

Before running that script, set the Azure SQL credentials in `.env`.

## Repo Layout

```text
app.py
config.py
db.py
db_azure.py
devops_sync.py
email_ingest.py
llm.py
migrate_to_azure.py
monitor.py
notifications.py
seed_data.py
seed_dev_tracks.py
static/
templates/
```

## Notes

- The app secret key is currently hard-coded in `app.py` for local development.
- LLM-powered flows are runtime-optional and degrade to non-AI behavior when Azure OpenAI is not configured.
- DevOps, IMAP, SMTP, and Azure SQL integrations are optional and only needed if you use those features.
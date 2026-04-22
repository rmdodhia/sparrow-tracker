# SPARROW Installation Tracker

Flask-based tracking app for SPARROW deployments and development tracks. Uses server-rendered Jinja templates in `templates/` and shared styling in `static/`.

## Architecture

- `app.py` — Flask entry point and route definitions
- `templates/` — server-rendered HTML views
- `static/css/style.css` — shared UI styles
- `db.py` — Database layer (SQLite for local dev, Azure SQL for production — auto-selects via env var)
- `graph_email.py` — Microsoft Graph email client (production)
- `email_ingest.py` — Email ingestion router (Graph or IMAP)
- `llm.py` — Azure OpenAI parsing and question-answering helpers
- `devops_sync.py` — Azure DevOps work item sync
- `monitor.py` — stale-project and deadline alert logic
- `notifications.py` — optional SMTP notification support
- `infra/` — Bicep IaC templates and deployment script

## Running Locally

```bash
git clone <repo-url>
cd sparrow-tracker
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # edit with your credentials
python app.py
```

Open `http://127.0.0.1:5001`. The app uses SQLite locally by default — no database setup needed.

## Environment Variables

Create a `.env` file (gitignored). All integrations are optional:

| Var | Purpose |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Enables LLM update parsing + Ask SPARROW |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name |
| `AZURE_OPENAI_API_KEY` | API key for OpenAI |
| `AZURE_SQL_CONNECTION_STRING` | If set, uses Azure SQL instead of SQLite |
| `GRAPH_CLIENT_ID` | App registration for Graph email |
| `GRAPH_TENANT_ID` | Entra tenant ID |
| `GRAPH_USER_EMAIL` | Mailbox to read |
| `AZURE_DEVOPS_PAT` | Optional — if unset, uses `az login` |

Without any env vars, the app runs with SQLite and no AI features.

## Deploying to Azure

The production deployment uses Azure App Service with Azure SQL, Entra-only authentication, and managed identity. Infrastructure is defined in `infra/main.bicep`.

See the internal engineering wiki for deployment procedures, subscription details, and app registration configuration.

### Quick Deploy

```bash
# Provision infrastructure
./infra/deploy.sh

# Deploy code
az webapp up --resource-group <rg-name> --name <app-name> --runtime "PYTHON:3.11"

# Seed data (via SSH into the web app)
az webapp ssh --resource-group <rg-name> --name <app-name>
python seed_data.py
```

## Notes

- `*.db` files are gitignored — never commit database files
- LLM features degrade gracefully when Azure OpenAI is not configured
- Production access is restricted to the Microsoft tenant via EasyAuth
- The app secret key in `app.py` should be set via env var in production
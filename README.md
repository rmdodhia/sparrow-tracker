# SPARROW Installation Tracker

A lightweight tracker for the AI For Good Lab's SPARROW wildlife conservation
deployments. It keeps a running picture of ~40 global installations — status,
blockers, deadlines, sprint work — in one place, and uses an LLM to turn free-form
updates (emails, notes) into structured records.

**Quick start** (no credentials needed to browse):

```bash
git clone https://github.com/rmdodhia/sparrow-tracker
cd sparrow-tracker
pip install -r requirements.txt
cp .env.example .env
python seed_data.py
streamlit run app.py
```

See [Setup](#setup) below for Python version, virtualenv, and credential config.

---

## For users of the app

### What it does

- **Dashboard** — summary of every installation: who's active, who's blocked,
  what's at risk, what's coming up.
- **Submit Update** — paste an email, a meeting note, or a quick sentence.
  The app parses it with an LLM, extracts the project, status change, blocker,
  dates, and contacts, and asks you to confirm before saving.
- **Project Details** — full history for one installation, editable fields,
  contacts, linked DevOps work items.
- **Sprints** — Sprint Board and By Person views of Azure DevOps work items
  pulled from the "AI For Good Lab" project. Sprints are grouped by each
  item's `iteration_path` (monthly).
- **Reports** — status breakdowns, stale-project nudges, deadline alerts.
- **Settings** — DevOps sync, connection tests, team config.

### Status model

Every project has one of five statuses, plus an independent **At Risk** flag:

| Status | Meaning |
|---|---|
| Scoping | Still defining the work |
| Active — Waiting on Partner | Ball is in the partner's court |
| Active — Waiting on Us | Ball is in our court |
| Complete | Installed and handed off |
| Descoped | No longer proceeding |

Projects go "stale" (a nudge fires) based on status: 21 days for Scoping,
14 for Waiting-on-Partner, 7 for Waiting-on-Us.

### Ask SPARROW

The sidebar has a free-text question box — "What's blocked?", "FY26 deadlines",
"Recent changes". It answers against the current DB state.

### Getting help

Email Rahul (radodhia@microsoft.com) or file an issue on
[github.com/rmdodhia/sparrow-tracker](https://github.com/rmdodhia/sparrow-tracker).

---

## For developers

### Stack

- **Streamlit** for the UI (single-file `app.py` with a custom Fluent-style theme in `theme.py`).
- **SQLite** for storage (`sparrow_tracker.db`, schema in `db.py`).
- **Azure OpenAI** for update parsing and the Ask-SPARROW Q&A (`llm.py`).
- **Azure DevOps REST API** for sprint + work-item sync (`devops_sync.py`).
- **IMAP** for optional email ingestion (`email_ingest.py`).

### Layout

```
app.py              Streamlit entry point (all pages)
theme.py            CSS, HTML helpers, pill/badge/card renderers
config.py           Env vars, status enum, FY helpers, team list
db.py               SQLite schema + query functions
llm.py              Azure OpenAI client + update parsing prompt
devops_sync.py      Azure DevOps WIQL + iteration sync
email_ingest.py     IMAP poller that feeds Submit Update
monitor.py          Staleness + deadline nudge generator
notifications.py    SMTP sender for nudges
seed_data.py        Seeds the DB with the current installation list
mockups/            v2 HTML mockups — the app is expected to match these
```

Design constraint worth knowing up front: **the Streamlit UI must match the v2
HTML mockups in `mockups/`**. Divergence has been flagged in review. When you
change layout or styling, open the relevant `v2_*.html` side-by-side.

### Setup

Requires **Python 3.10+**.

```bash
# 1. Clone and install
git clone https://github.com/rmdodhia/sparrow-tracker
cd sparrow-tracker
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env
# Edit .env — see "Minimal run" vs "Full run" below for what to fill in

# 3. Seed the DB from the committed backlog (first time only)
python seed_data.py

# 4. Run
streamlit run app.py
```

Open http://localhost:8501 in a browser.

#### Minimal run (no credentials)

You can run the app with an empty `.env` — it will start, show the dashboard,
and let you browse the seeded projects. What you lose:

- **Submit Update** LLM parsing (sidebar shows "⚠️ LLM not configured")
- **Ask SPARROW** natural-language Q&A
- **Sprints** / DevOps sync
- **Email ingestion** and **nudge emails**

Everything else — browsing projects, editing fields by hand, reports, the
history timeline — works.

#### Full run (with credentials)

Fill in `.env`:

1. **Azure OpenAI** (required for LLM features): set `AZURE_OPENAI_ENDPOINT`,
   `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`. The example file points at
   the AI For Good Lab's EU2 deployment; swap in your own if you're outside
   the lab.
2. **Azure DevOps** (optional, for Sprints page): either set
   `AZURE_DEVOPS_PAT`, or leave it blank and run `az login` once so the app
   can use Entra ID via `DefaultAzureCredential`. Default org/project are
   `onecela` / `AI For Good Lab` — override with `AZURE_DEVOPS_ORG` /
   `AZURE_DEVOPS_PROJECT` if you're pointing elsewhere.
3. **IMAP** (optional, for email-forwarding ingestion): set `IMAP_HOST`,
   `IMAP_PORT`, `IMAP_USER`, `IMAP_PASS`. Microsoft 365 mailboxes now require
   Microsoft Graph instead — support is in progress.
4. **SMTP** (optional, for nudge emails): set the `SPARROW_SMTP_*` vars.

### Environment variables

| Var | Required | Purpose |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | yes | Enables update parsing + Ask SPARROW |
| `AZURE_OPENAI_DEPLOYMENT` | yes | e.g. `gpt-54` |
| `AZURE_OPENAI_API_KEY` | yes | |
| `AZURE_OPENAI_API_VERSION` | no | Defaults to `2024-10-21` |
| `AZURE_DEVOPS_ORG` | no | Defaults to `onecela` |
| `AZURE_DEVOPS_PROJECT` | no | Defaults to `AI For Good Lab` |
| `AZURE_DEVOPS_PAT` | no | Optional PAT override. If unset, auth uses Entra ID via `DefaultAzureCredential` (run `az login` once on dev machines). |
| `IMAP_HOST` / `_PORT` / `_USER` / `_PASS` | for email | Inbox that forwards updates |
| `SPARROW_SMTP_*` | for nudges | Outgoing mail for staleness alerts |

`.env` is gitignored. Never commit it.

### Database

SQLite file at the repo root. Tables:

- `projects` — one row per installation
- `history` — append-only log of every status change / note
- `contacts` — partner contacts per project
- `raw_inputs` — unparsed emails/notes before LLM extraction
- `nudges` — active staleness and deadline alerts
- `devops_work_items` — DevOps sync cache (sprint = `iteration_path` field on each row)

Schema lives in `db.py::init_db()`. It's idempotent — safe to re-run.

### Running DevOps sync

```python
from devops_sync import sync_all
sync_all()   # pulls iterations + work items matching DEVOPS_SEARCH_TERMS
```

Or hit the **Sync now** button on the Settings page. Search terms are
configured in `config.py::DEVOPS_SEARCH_TERMS`
(`sparrow`, `pytorch wildlife`, `condor`, `owl`).

### Known gaps

- Importing `SPARROW_BACKLOG_OF_PRIORITIES.xlsx` into the DB is not yet wired up.
- The Gantt / FY26-27 Roadmap view from the xlsx has no equivalent page yet.
- DevOps work items aren't linked back to projects (`linked_project_id`).
- `status_pill_html` callers don't all pass `is_at_risk`.

### Contributing

PRs welcome. Before opening one:

1. Re-run `streamlit run app.py` and click through every page.
2. If you touched layout, compare against the matching `mockups/v2_*.html`.
3. Keep `db.py` migrations additive — there's no migration framework.

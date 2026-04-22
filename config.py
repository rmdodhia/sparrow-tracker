"""
SPARROW Installation Tracker — Configuration
"""

import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

# --- LLM (Azure OpenAI) ---
# Set these in .env or as environment variables.
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

# --- Database ---
# SQLite (local dev) — used when AZURE_SQL_CONNECTION_STRING is not set.
DB_PATH = os.path.join(os.path.dirname(__file__), "sparrow_tracker.db")

# Azure SQL (production) — set this to use Azure SQL instead of SQLite.
AZURE_SQL_CONNECTION_STRING = os.environ.get("AZURE_SQL_CONNECTION_STRING", "")
DB_BACKEND = "azure_sql" if AZURE_SQL_CONNECTION_STRING else "sqlite"

# --- Status Enum ---
# Simplified statuses. "At Risk" is a flag (is_at_risk) that can be tacked onto any status.
VALID_STATUSES = [
    "Scoping",
    "Active - Waiting on Partner",
    "Active - Waiting on Us",
    "Complete",
    "Descoped",
]

# Statuses that are considered "closed" (no monitoring needed)
CLOSED_STATUSES = {"Complete", "Descoped"}

# --- Staleness Thresholds (days with no update before a nudge fires) ---
STALENESS_THRESHOLDS = {
    "Scoping":                       21,
    "Active - Waiting on Partner":   14,
    "Active - Waiting on Us":         7,
}

# --- Deadline Alert Windows (days before target_date) ---
DEADLINE_ALERTS = [
    {"days_before": 0,  "severity": "escalation"},   # overdue — check first
    {"days_before": 14, "severity": "warning"},
    {"days_before": 30, "severity": "info"},
]

# --- Team ---
TEAM_MEMBERS = ["Bruno", "Carl", "Miao", "Rahul", "Manolo"]

# --- Phase vocabularies (per item_type) ---
# Keyed off projects.item_type ('deployment' vs 'dev_track').
DEV_PHASE_KEYS    = ["Dev", "Testing", "Manual", "OpenSource", "Launch", "Rollout"]
DEPLOY_PHASE_KEYS = ["Scoping", "Approved", "OnTrack", "Installed", "Done"]
PHASE_STATUSES    = ["Planned", "In Progress", "Done", "Blocked", "At Risk", "On Hold", "Cancelled"]

# Muted professional palette (slates + ceruleans + amber) for the Gantt.
# Done is a dark slate (work complete, de-emphasized). In Progress is a
# saturated cerulean so active work pops. Planned is a pale slate.
# At Risk / Blocked use warm amber/crimson for immediate attention.
PHASE_STATUS_COLORS = {
    "Planned":     "#cbd5e1",   # slate-300
    "In Progress": "#1d4ed8",   # blue-700 (cerulean)
    "Done":        "#475569",   # slate-600
    "Blocked":     "#b91c1c",   # red-700
    "At Risk":     "#d97706",   # amber-600
    "On Hold":     "#e2e8f0",   # slate-200
    "Cancelled":   "#f1f5f9",   # slate-100
}

# Statuses whose bars are light enough to need dark text inside them.
PHASE_LIGHT_FILL_STATUSES = {"Planned", "On Hold", "Cancelled"}

# --- Microsoft Fiscal Year Helpers ---
def fy_end_date(fy_year: int) -> date:
    """Microsoft FY ends June 30. FY26 ends 2026-06-30."""
    return date(fy_year, 6, 30)

FY26_END = fy_end_date(26 + 2000)  # 2026-06-30

# --- Azure DevOps Integration ---
AZURE_DEVOPS_ORG = os.environ.get("AZURE_DEVOPS_ORG", "onecela")
AZURE_DEVOPS_PROJECT = os.environ.get("AZURE_DEVOPS_PROJECT", "AI For Good Lab")
AZURE_DEVOPS_PAT = os.environ.get("AZURE_DEVOPS_PAT", "")
DEVOPS_SEARCH_TERMS = ["sparrow", "pytorch wildlife", "condor", "robin"]

# Saved query in the DevOps "My Queries" folder that returns active user stories
# for the current sprint. Used for the sprint/board view.
DEVOPS_SPRINT_QUERY_ID = os.environ.get(
    "DEVOPS_SPRINT_QUERY_ID", "6f2ec623-1268-4b9e-9c13-996785b3961a"
)

# --- Email Ingestion (IMAP — legacy, used when GRAPH_CLIENT_ID is not set) ---
IMAP_HOST = os.environ.get("IMAP_HOST", "")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ.get("IMAP_USER", "")
IMAP_PASS = os.environ.get("IMAP_PASS", "")
IMAP_FOLDER = os.environ.get("IMAP_FOLDER", "INBOX")
IMAP_DONE_FOLDER = os.environ.get("IMAP_DONE_FOLDER", "")

# --- Email Ingestion (Microsoft Graph — production) ---
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", "")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", "")
GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID", "")
GRAPH_USER_EMAIL = os.environ.get("GRAPH_USER_EMAIL", "sparrow-tracker@microsoft.com")
EMAIL_BACKEND = "graph" if GRAPH_CLIENT_ID else ("imap" if IMAP_HOST else "")

# --- Notification / SMTP (optional) ---
SMTP_HOST = os.environ.get("SPARROW_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SPARROW_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SPARROW_SMTP_USER", "")
SMTP_PASS = os.environ.get("SPARROW_SMTP_PASS", "")
NOTIFY_FROM = os.environ.get("SPARROW_NOTIFY_FROM", "sparrow-tracker@noreply.local")

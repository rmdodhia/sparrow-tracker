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

# --- Database (Azure SQL) ---
AZURE_SQL_SERVER = os.environ.get("AZURE_SQL_SERVER", "")
AZURE_SQL_DATABASE = os.environ.get("AZURE_SQL_DATABASE", "")
AZURE_SQL_USER = os.environ.get("AZURE_SQL_USER", "")
AZURE_SQL_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")

# Legacy SQLite path (for migration script)
DB_PATH = os.path.join(os.path.dirname(__file__), "sparrow_tracker.db")

# --- Lifecycle (project stage) ---
VALID_STATUSES = [
    "Scoping",
    "Active",
    "Complete",
    "Descoped",
]

# --- Health (how it's going — applies to Scoping & Active) ---
VALID_HEALTH = [
    "On Track",
    "Waiting on Partner",
    "Waiting on Us",
    "Blocked",
]

# --- Priority ---
VALID_PRIORITIES = ["TOP", "MID", "LOW"]

# Statuses that are considered "closed" (no monitoring needed)
CLOSED_STATUSES = {"Complete", "Descoped"}

# --- Staleness Thresholds (days with no update before a nudge fires) ---
# Keyed off health. "Waiting on Us" gets the shortest leash; "Blocked" is flagged fast.
STALENESS_THRESHOLDS = {
    "On Track":            14,
    "Waiting on Partner":  21,
    "Waiting on Us":        7,
    "Blocked":              3,
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
PHASE_STATUSES    = ["Todo", "Doing", "Done"]

# Muted professional palette for the Gantt.
# Todo is a pale slate, Doing is saturated cerulean, Done is dark slate.
PHASE_STATUS_COLORS = {
    "Todo":  "#cbd5e1",   # slate-300
    "Doing": "#1d4ed8",   # blue-700 (cerulean)
    "Done":  "#475569",   # slate-600
}

# Statuses whose bars are light enough to need dark text inside them.
PHASE_LIGHT_FILL_STATUSES = {"Todo"}

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

# --- Email Ingestion (IMAP) ---
IMAP_HOST = os.environ.get("IMAP_HOST", "")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ.get("IMAP_USER", "")
IMAP_PASS = os.environ.get("IMAP_PASS", "")
IMAP_FOLDER = os.environ.get("IMAP_FOLDER", "INBOX")
IMAP_DONE_FOLDER = os.environ.get("IMAP_DONE_FOLDER", "")

# --- Notification / SMTP (optional) ---
SMTP_HOST = os.environ.get("SPARROW_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SPARROW_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SPARROW_SMTP_USER", "")
SMTP_PASS = os.environ.get("SPARROW_SMTP_PASS", "")
NOTIFY_FROM = os.environ.get("SPARROW_NOTIFY_FROM", "sparrow-tracker@noreply.local")

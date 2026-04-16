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
DB_PATH = os.path.join(os.path.dirname(__file__), "sparrow_tracker.db")

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

# --- Microsoft Fiscal Year Helpers ---
def fy_end_date(fy_year: int) -> date:
    """Microsoft FY ends June 30. FY26 ends 2026-06-30."""
    return date(fy_year, 6, 30)

FY26_END = fy_end_date(26 + 2000)  # 2026-06-30

# --- Azure DevOps Integration ---
AZURE_DEVOPS_ORG = os.environ.get("AZURE_DEVOPS_ORG", "onecela")
AZURE_DEVOPS_PROJECT = os.environ.get("AZURE_DEVOPS_PROJECT", "AI For Good Lab")
AZURE_DEVOPS_PAT = os.environ.get("AZURE_DEVOPS_PAT", "")
DEVOPS_SEARCH_TERMS = ["sparrow", "pytorch wildlife", "condor", "owl"]

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

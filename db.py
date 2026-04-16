"""
SPARROW Installation Tracker — Database Layer (SQLite)
"""

import json
import sqlite3
from datetime import datetime, date, timedelta
from contextlib import contextmanager

from config import DB_PATH, STALENESS_THRESHOLDS, DEADLINE_ALERTS, CLOSED_STATUSES


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id        TEXT PRIMARY KEY,
            continent         TEXT,
            country           TEXT,
            location          TEXT,
            partner_org       TEXT,
            status            TEXT NOT NULL DEFAULT 'Scoping',
            blocker           TEXT,
            deployment_type   TEXT,
            timeline_label    TEXT,          -- human-readable: "Before End FY26"
            target_date       TEXT,          -- ISO date or NULL
            target_confidence TEXT,          -- hard / committed / soft / aspirational
            hardware          TEXT,
            estimated_cost    REAL,
            team_owner        TEXT,
            devops_id         INTEGER,
            notes             TEXT,
            last_updated      TEXT NOT NULL,
            last_updated_by   TEXT,
            is_at_risk        INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            updated_by      TEXT,
            source_type     TEXT,            -- email / teams_paste / manual_note / system
            source_text     TEXT,            -- full original pasted text
            changes         TEXT NOT NULL,   -- JSON: {field: {old, new}}
            llm_summary     TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            organization    TEXT,
            role            TEXT,
            email           TEXT,
            phone           TEXT,
            linked_projects TEXT,            -- JSON array of project_ids
            notes           TEXT
        );

        CREATE TABLE IF NOT EXISTS raw_inputs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            submitted_by    TEXT,
            input_type      TEXT,            -- update / question / report_request
            full_text       TEXT NOT NULL,
            history_ids     TEXT             -- JSON array of history row ids created
        );

        CREATE TABLE IF NOT EXISTS nudges (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            nudge_type      TEXT NOT NULL,   -- stale / deadline
            severity        TEXT NOT NULL,   -- info / warning / escalation
            message         TEXT NOT NULL,
            sent_to         TEXT,
            resolved        INTEGER NOT NULL DEFAULT 0,
            resolved_by_history_id INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );

        CREATE INDEX IF NOT EXISTS idx_history_project ON history(project_id);
        CREATE INDEX IF NOT EXISTS idx_history_ts ON history(timestamp);
        CREATE INDEX IF NOT EXISTS idx_nudges_active ON nudges(resolved, project_id);

        -- DevOps integration tables
        CREATE TABLE IF NOT EXISTS devops_work_items (
            id              INTEGER PRIMARY KEY,
            title           TEXT NOT NULL,
            state           TEXT,
            assigned_to     TEXT,
            iteration_path  TEXT,
            work_item_type  TEXT,
            area_path       TEXT,
            tags            TEXT,
            linked_project_id TEXT,
            url             TEXT,
            last_synced     TEXT,
            FOREIGN KEY (linked_project_id) REFERENCES projects(project_id)
        );

        CREATE TABLE IF NOT EXISTS devops_iterations (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            path            TEXT,
            start_date      TEXT,
            end_date        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_wi_iteration ON devops_work_items(iteration_path);
        CREATE INDEX IF NOT EXISTS idx_wi_assigned ON devops_work_items(assigned_to);
        """)

        # ── Migrations for existing databases ────────────────────────────
        # Add is_at_risk column if missing (existing DBs)
        try:
            conn.execute("SELECT is_at_risk FROM projects LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE projects ADD COLUMN is_at_risk INTEGER NOT NULL DEFAULT 0")

        # Migrate old statuses to new simplified statuses
        _migrate_statuses(conn)


def _migrate_statuses(conn):
    """Map legacy statuses to the new simplified set. Idempotent."""
    status_map = {
        "Approved":     "Active - Waiting on Us",
        "Procurement":  "Active - Waiting on Us",
        "Shipping":     "Active - Waiting on Partner",
        "Deploying":    "Active - Waiting on Partner",
        "Installed":    "Active - Waiting on Partner",
        "Active":       "Active - Waiting on Partner",
        "On Hold":      "Active - Waiting on Partner",
        "Blocked":      "Active - Waiting on Us",
        "Waiting":      "Active - Waiting on Partner",
        "At Risk":      "Active - Waiting on Us",
    }
    risk_statuses = {"At Risk", "Blocked"}
    for old_status, new_status in status_map.items():
        is_risk = 1 if old_status in risk_statuses else 0
        conn.execute(
            "UPDATE projects SET status = ?, is_at_risk = MAX(is_at_risk, ?) WHERE status = ?",
            (new_status, is_risk, old_status),
        )


# ── Projects ──────────────────────────────────────────────────────────────────

def get_all_projects(include_closed=True):
    with get_conn() as conn:
        if include_closed:
            rows = conn.execute("SELECT * FROM projects ORDER BY continent, country, location").fetchall()
        else:
            placeholders = ",".join("?" for _ in CLOSED_STATUSES)
            rows = conn.execute(
                f"SELECT * FROM projects WHERE status NOT IN ({placeholders}) ORDER BY continent, country, location",
                list(CLOSED_STATUSES),
            ).fetchall()
        return [dict(r) for r in rows]


def get_project(project_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        return dict(row) if row else None


def update_project(project_id, updates: dict, updated_by: str = None):
    """Update project fields. Returns the dict of {field: {old, new}} that actually changed."""
    current = get_project(project_id)
    if not current:
        raise ValueError(f"Project {project_id} not found")

    changes = {}
    for field, new_val in updates.items():
        if field in ("project_id",):
            continue
        old_val = current.get(field)
        if str(old_val) != str(new_val):
            changes[field] = {"old": old_val, "new": new_val}

    if not changes:
        return changes

    set_parts = []
    params = []
    for field in changes:
        set_parts.append(f"{field} = ?")
        params.append(changes[field]["new"])
    set_parts.append("last_updated = ?")
    params.append(datetime.utcnow().isoformat(timespec="seconds"))
    if updated_by:
        set_parts.append("last_updated_by = ?")
        params.append(updated_by)
    params.append(project_id)

    with get_conn() as conn:
        conn.execute(
            f"UPDATE projects SET {', '.join(set_parts)} WHERE project_id = ?",
            params,
        )
    return changes


def create_project(data: dict):
    cols = list(data.keys())
    placeholders = ",".join("?" for _ in cols)
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO projects ({','.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )


# ── History ───────────────────────────────────────────────────────────────────

def add_history(project_id, changes: dict, source_text: str = None,
                source_type: str = None, updated_by: str = None,
                llm_summary: str = None):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO history
               (project_id, timestamp, updated_by, source_type, source_text, changes, llm_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, ts, updated_by, source_type, source_text,
             json.dumps(changes), llm_summary),
        )
        # Auto-resolve any active nudges for this project
        conn.execute(
            "UPDATE nudges SET resolved = 1, resolved_by_history_id = ? WHERE project_id = ? AND resolved = 0",
            (cur.lastrowid, project_id),
        )
        return cur.lastrowid


def get_project_history(project_id, limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM history WHERE project_id = ? ORDER BY timestamp DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["changes"] = json.loads(d["changes"])
            result.append(d)
        return result


def get_recent_history(days=14, limit=100):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM history WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["changes"] = json.loads(d["changes"])
            result.append(d)
        return result


# ── Contacts ──────────────────────────────────────────────────────────────────

def add_contact(name, organization=None, role=None, email=None, phone=None,
                linked_projects=None, notes=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO contacts (name, organization, role, email, phone, linked_projects, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, organization, role, email, phone,
             json.dumps(linked_projects or []), notes),
        )


def get_contacts(project_id=None):
    with get_conn() as conn:
        if project_id:
            rows = conn.execute("SELECT * FROM contacts").fetchall()
            return [dict(r) for r in rows
                    if project_id in json.loads(r["linked_projects"] or "[]")]
        return [dict(r) for r in conn.execute("SELECT * FROM contacts ORDER BY organization, name").fetchall()]


# ── Raw Inputs ────────────────────────────────────────────────────────────────

def add_raw_input(full_text, submitted_by=None, input_type="update", history_ids=None):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO raw_inputs (timestamp, submitted_by, input_type, full_text, history_ids) VALUES (?,?,?,?,?)",
            (ts, submitted_by, input_type, full_text, json.dumps(history_ids or [])),
        )


# ── Nudges ────────────────────────────────────────────────────────────────────

def add_nudge(project_id, nudge_type, severity, message, sent_to=None):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO nudges (project_id, timestamp, nudge_type, severity, message, sent_to) VALUES (?,?,?,?,?,?)",
            (project_id, ts, nudge_type, severity, message, sent_to),
        )


def get_active_nudges(project_id=None):
    with get_conn() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM nudges WHERE resolved = 0 AND project_id = ? ORDER BY timestamp DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM nudges WHERE resolved = 0 ORDER BY severity DESC, timestamp DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def resolve_nudge(nudge_id, history_id=None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE nudges SET resolved = 1, resolved_by_history_id = ? WHERE id = ?",
            (history_id, nudge_id),
        )


# ── Analytics Helpers ─────────────────────────────────────────────────────────

def get_stale_projects():
    """Return projects that have not been updated within their staleness threshold."""
    projects = get_all_projects(include_closed=False)
    stale = []
    now = datetime.utcnow()
    for p in projects:
        threshold = p.get("stale_threshold_days") or STALENESS_THRESHOLDS.get(p["status"])
        if threshold is None:
            continue
        last = datetime.fromisoformat(p["last_updated"])
        days_since = (now - last).days
        if days_since >= threshold:
            p["days_since_update"] = days_since
            p["threshold"] = threshold
            stale.append(p)
    return stale


def get_deadline_approaching():
    """Return projects with target_date approaching or overdue."""
    projects = get_all_projects(include_closed=False)
    flagged = []
    today = date.today()
    for p in projects:
        if not p.get("target_date"):
            continue
        try:
            target = date.fromisoformat(p["target_date"])
        except (ValueError, TypeError):
            continue
        days_until = (target - today).days
        for alert in DEADLINE_ALERTS:
            if days_until <= alert["days_before"]:
                p["days_until_deadline"] = days_until
                p["alert_severity"] = alert["severity"]
                flagged.append(p)
                break
    return flagged


def get_status_summary():
    """Return {status: count} dict."""
    with get_conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) as cnt FROM projects GROUP BY status").fetchall()
        return {r["status"]: r["cnt"] for r in rows}

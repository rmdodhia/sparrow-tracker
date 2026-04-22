"""
SPARROW Installation Tracker — Database Layer

Supports two backends:
  - SQLite  (local dev, default when AZURE_SQL_CONNECTION_STRING is unset)
  - Azure SQL via pyodbc (production)

The rest of the module uses standard DB-API parameterized queries (`?`),
which both sqlite3 and pyodbc accept.
"""

import json
import sqlite3
from datetime import datetime, date, timedelta
from contextlib import contextmanager

from config import (
    DB_PATH, AZURE_SQL_CONNECTION_STRING, DB_BACKEND,
    STALENESS_THRESHOLDS, DEADLINE_ALERTS, CLOSED_STATUSES,
)


class _DictRow:
    """Minimal wrapper so pyodbc rows behave like sqlite3.Row (dict-like)."""

    def __init__(self, cursor, row):
        self._data = {
            col[0]: row[i] for i, col in enumerate(cursor.description)
        }

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]

    def keys(self):
        return self._data.keys()


def _dict_from_row(row):
    """Convert a row (sqlite3.Row or _DictRow) to a plain dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(zip(row.keys(), (row[k] for k in row.keys())))


@contextmanager
def get_conn():
    """Yield a DB-API connection for the configured backend."""
    if DB_BACKEND == "azure_sql":
        import pyodbc
        conn = pyodbc.connect(AZURE_SQL_CONNECTION_STRING)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _fetchall_dicts(cursor):
    """Fetch all rows as list[dict], works with both backends."""
    if DB_BACKEND == "azure_sql":
        cols = [col[0] for col in cursor.description] if cursor.description else []
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    return [dict(r) for r in cursor.fetchall()]


def _fetchone_dict(cursor):
    """Fetch one row as dict or None, works with both backends."""
    row = cursor.fetchone()
    if row is None:
        return None
    if DB_BACKEND == "azure_sql":
        cols = [col[0] for col in cursor.description]
        return dict(zip(cols, row))
    return dict(row)


def _last_insert_id(cursor, conn):
    """Get the last inserted IDENTITY/AUTOINCREMENT ID, cross-backend."""
    if DB_BACKEND == "azure_sql":
        cursor.execute("SELECT SCOPE_IDENTITY()")
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None
    return cursor.lastrowid


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db():
    if DB_BACKEND == "azure_sql":
        _init_db_azure_sql()
    else:
        _init_db_sqlite()


def _init_db_sqlite():
    """SQLite schema — used for local development."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id        TEXT PRIMARY KEY,
            continent         TEXT,
            country           TEXT,
            location          TEXT,
            partner_org       TEXT,
            status            TEXT NOT NULL DEFAULT 'Scoping',
            health            TEXT NOT NULL DEFAULT 'On Track',
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
            is_at_risk        INTEGER NOT NULL DEFAULT 0,
            priority          TEXT,          -- TOP / MID / LOW
            sparrow           INTEGER NOT NULL DEFAULT 0,
            sparrow_go        INTEGER NOT NULL DEFAULT 0,
            robin             INTEGER NOT NULL DEFAULT 0
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

        CREATE INDEX IF NOT EXISTS idx_wi_iteration ON devops_work_items(iteration_path);
        CREATE INDEX IF NOT EXISTS idx_wi_assigned ON devops_work_items(assigned_to);

        CREATE TABLE IF NOT EXISTS phases (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id          TEXT NOT NULL,
            phase_key           TEXT NOT NULL,       -- enum from config.DEV_PHASE_KEYS / DEPLOY_PHASE_KEYS, or 'custom'
            name                TEXT NOT NULL,       -- display label (may override phase_key)
            ordering            INTEGER NOT NULL DEFAULT 0,
            start_date          TEXT,                -- ISO date
            end_date            TEXT,                -- ISO date
            status              TEXT NOT NULL DEFAULT 'Todo',
            depends_on_phase_id INTEGER,
            devops_id           INTEGER,
            notes               TEXT,
            last_updated        TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on_phase_id) REFERENCES phases(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_phases_project ON phases(project_id, ordering);
        CREATE INDEX IF NOT EXISTS idx_phases_end ON phases(end_date);
        """)

        # ── Migrations for existing databases ────────────────────────────
        # Add is_at_risk column if missing (existing DBs)
        try:
            conn.execute("SELECT is_at_risk FROM projects LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE projects ADD COLUMN is_at_risk INTEGER NOT NULL DEFAULT 0")

        # Add health column if missing (existing DBs)
        try:
            conn.execute("SELECT health FROM projects LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE projects ADD COLUMN health TEXT NOT NULL DEFAULT 'On Track'")

        # Add priority / hardware-boolean columns if missing
        for col, ddl in [
            ("priority",   "TEXT"),
            ("sparrow",    "INTEGER NOT NULL DEFAULT 0"),
            ("sparrow_go", "INTEGER NOT NULL DEFAULT 0"),
            ("robin",      "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM projects LIMIT 1")
            except Exception:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {ddl}")

        # Add phase-era columns to projects (item_type, track_name, start_date, parent_project_id)
        _migrate_phase_columns(conn)

        # Migrate old statuses to new simplified statuses
        _migrate_statuses(conn)

        # Migrate to lifecycle + health model (Active - Waiting on X → Active + health)
        _migrate_to_lifecycle_health(conn)

        # Migrate old phase statuses to Todo/Doing/Done
        _migrate_phase_statuses(conn)

        # Backfill one phase per deployment (idempotent — only runs when no phase exists yet)
        _backfill_phases(conn)


def _init_db_azure_sql():
    """Azure SQL schema — used in production. Idempotent via IF NOT EXISTS."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'projects')
        CREATE TABLE projects (
            project_id        NVARCHAR(200) PRIMARY KEY,
            continent         NVARCHAR(100),
            country           NVARCHAR(200),
            location          NVARCHAR(500),
            partner_org       NVARCHAR(500),
            status            NVARCHAR(100) NOT NULL DEFAULT 'Scoping',
            health            NVARCHAR(100) NOT NULL DEFAULT 'On Track',
            blocker           NVARCHAR(MAX),
            deployment_type   NVARCHAR(200),
            timeline_label    NVARCHAR(200),
            target_date       NVARCHAR(20),
            target_confidence NVARCHAR(50),
            hardware          NVARCHAR(500),
            estimated_cost    FLOAT,
            team_owner        NVARCHAR(200),
            devops_id         INT,
            notes             NVARCHAR(MAX),
            last_updated      NVARCHAR(30) NOT NULL,
            last_updated_by   NVARCHAR(200),
            is_at_risk        INT NOT NULL DEFAULT 0,
            priority          NVARCHAR(10),
            sparrow           INT NOT NULL DEFAULT 0,
            sparrow_go        INT NOT NULL DEFAULT 0,
            robin             INT NOT NULL DEFAULT 0,
            item_type         NVARCHAR(50) NOT NULL DEFAULT 'deployment',
            track_name        NVARCHAR(500),
            start_date        NVARCHAR(20),
            parent_project_id NVARCHAR(200)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'history')
        CREATE TABLE history (
            id              INT IDENTITY(1,1) PRIMARY KEY,
            project_id      NVARCHAR(200) NOT NULL,
            timestamp       NVARCHAR(30) NOT NULL,
            updated_by      NVARCHAR(200),
            source_type     NVARCHAR(50),
            source_text     NVARCHAR(MAX),
            changes         NVARCHAR(MAX) NOT NULL,
            llm_summary     NVARCHAR(MAX)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'contacts')
        CREATE TABLE contacts (
            id              INT IDENTITY(1,1) PRIMARY KEY,
            name            NVARCHAR(500) NOT NULL,
            organization    NVARCHAR(500),
            role            NVARCHAR(200),
            email           NVARCHAR(500),
            phone           NVARCHAR(100),
            linked_projects NVARCHAR(MAX),
            notes           NVARCHAR(MAX)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'raw_inputs')
        CREATE TABLE raw_inputs (
            id              INT IDENTITY(1,1) PRIMARY KEY,
            timestamp       NVARCHAR(30) NOT NULL,
            submitted_by    NVARCHAR(200),
            input_type      NVARCHAR(50),
            full_text       NVARCHAR(MAX) NOT NULL,
            history_ids     NVARCHAR(MAX)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'nudges')
        CREATE TABLE nudges (
            id              INT IDENTITY(1,1) PRIMARY KEY,
            project_id      NVARCHAR(200) NOT NULL,
            timestamp       NVARCHAR(30) NOT NULL,
            nudge_type      NVARCHAR(50) NOT NULL,
            severity        NVARCHAR(50) NOT NULL,
            message         NVARCHAR(MAX) NOT NULL,
            sent_to         NVARCHAR(200),
            resolved        INT NOT NULL DEFAULT 0,
            resolved_by_history_id INT
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'devops_work_items')
        CREATE TABLE devops_work_items (
            id              INT PRIMARY KEY,
            title           NVARCHAR(MAX) NOT NULL,
            state           NVARCHAR(100),
            assigned_to     NVARCHAR(500),
            iteration_path  NVARCHAR(500),
            work_item_type  NVARCHAR(100),
            area_path       NVARCHAR(500),
            tags            NVARCHAR(MAX),
            linked_project_id NVARCHAR(200),
            url             NVARCHAR(1000),
            last_synced     NVARCHAR(30)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'phases')
        CREATE TABLE phases (
            id                  INT IDENTITY(1,1) PRIMARY KEY,
            project_id          NVARCHAR(200) NOT NULL,
            phase_key           NVARCHAR(100) NOT NULL,
            name                NVARCHAR(500) NOT NULL,
            ordering            INT NOT NULL DEFAULT 0,
            start_date          NVARCHAR(20),
            end_date            NVARCHAR(20),
            status              NVARCHAR(100) NOT NULL DEFAULT 'Planned',
            depends_on_phase_id INT,
            devops_id           INT,
            notes               NVARCHAR(MAX),
            last_updated        NVARCHAR(30) NOT NULL
        )
        """)
        conn.commit()

        # Migrations for existing Azure SQL databases — add columns that may be missing
        _migrate_azure_sql_columns(cursor, conn)


def _migrate_azure_sql_columns(cursor, conn):
    """Add columns to Azure SQL projects table if missing. Idempotent."""
    migrations = [
        ("health",     "NVARCHAR(100) NOT NULL DEFAULT 'On Track'"),
        ("priority",   "NVARCHAR(10)"),
        ("sparrow",    "INT NOT NULL DEFAULT 0"),
        ("sparrow_go", "INT NOT NULL DEFAULT 0"),
        ("robin",      "INT NOT NULL DEFAULT 0"),
    ]
    for col, ddl in migrations:
        try:
            cursor.execute(f"SELECT {col} FROM projects WHERE 1=0")
        except Exception:
            cursor.execute(f"ALTER TABLE projects ADD {col} {ddl}")
            conn.commit()


def _migrate_phase_columns(conn):
    """Add item_type, track_name, start_date, parent_project_id to projects. Idempotent."""
    new_cols = [
        ("item_type",         "TEXT NOT NULL DEFAULT 'deployment'"),
        ("track_name",        "TEXT"),
        ("start_date",        "TEXT"),
        ("parent_project_id", "TEXT"),
    ]
    for col, ddl in new_cols:
        try:
            conn.execute(f"SELECT {col} FROM projects LIMIT 1")
        except Exception:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {ddl}")


_STATUS_TO_PHASE_STATUS = {
    "Scoping":  "Todo",
    "Active":   "Doing",
    "Complete": "Done",
    "Descoped": "Done",
}


def _backfill_phases(conn):
    """For any project with no phases yet, synthesize a single phase from its target_date + status."""
    rows = conn.execute("""
        SELECT p.project_id, p.status, p.target_date, p.timeline_label,
               p.start_date, p.last_updated
        FROM projects p
        LEFT JOIN phases ph ON ph.project_id = p.project_id
        WHERE ph.id IS NULL
        GROUP BY p.project_id
    """).fetchall()
    now = datetime.utcnow().isoformat(timespec="seconds")
    for r in rows:
        phase_status = _STATUS_TO_PHASE_STATUS.get(r["status"], "Todo")
        # Derive a plausible start so the Gantt bar has width.
        start = r["start_date"]
        end = r["target_date"]
        if not start:
            if end:
                try:
                    end_dt = datetime.fromisoformat(end).date()
                    start = (end_dt - timedelta(days=90)).isoformat()
                except (ValueError, TypeError):
                    start = None
            elif r["last_updated"]:
                try:
                    start = datetime.fromisoformat(r["last_updated"]).date().isoformat()
                except (ValueError, TypeError):
                    start = None
        name = r["timeline_label"] or "Deployment"
        conn.execute(
            """INSERT INTO phases
               (project_id, phase_key, name, ordering, start_date, end_date, status, last_updated)
               VALUES (?, 'custom', ?, 0, ?, ?, ?, ?)""",
            (r["project_id"], name, start, end, phase_status, now),
        )


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


def _migrate_to_lifecycle_health(conn):
    """Migrate 'Active - Waiting on X' statuses to lifecycle + health model. Idempotent."""
    # Only run if old-style statuses still exist
    old = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE status LIKE 'Active - %'"
    ).fetchone()[0]
    if old == 0:
        return

    # Active - Waiting on Partner  →  status=Active, health=Waiting on Partner
    conn.execute(
        "UPDATE projects SET health = 'Waiting on Partner', status = 'Active' "
        "WHERE status = 'Active - Waiting on Partner' AND is_at_risk = 0"
    )
    conn.execute(
        "UPDATE projects SET health = 'Blocked', status = 'Active' "
        "WHERE status = 'Active - Waiting on Partner' AND is_at_risk = 1"
    )
    # Active - Waiting on Us  →  status=Active, health=Waiting on Us
    conn.execute(
        "UPDATE projects SET health = 'Waiting on Us', status = 'Active' "
        "WHERE status = 'Active - Waiting on Us' AND is_at_risk = 0"
    )
    conn.execute(
        "UPDATE projects SET health = 'Blocked', status = 'Active' "
        "WHERE status = 'Active - Waiting on Us' AND is_at_risk = 1"
    )


def _migrate_phase_statuses(conn):
    """Migrate old 7-value phase statuses to Todo/Doing/Done. Idempotent."""
    phase_map = {
        "Planned":     "Todo",
        "In Progress": "Doing",
        "Blocked":     "Doing",
        "At Risk":     "Doing",
        "On Hold":     "Todo",
        "Cancelled":   "Done",
    }
    for old_ps, new_ps in phase_map.items():
        conn.execute(
            "UPDATE phases SET status = ? WHERE status = ?",
            (new_ps, old_ps),
        )


# ── Projects ──────────────────────────────────────────────────────────────────

def get_all_projects(include_closed=True):
    with get_conn() as conn:
        if include_closed:
            cur = conn.execute("SELECT * FROM projects ORDER BY continent, country, location")
        else:
            placeholders = ",".join("?" for _ in CLOSED_STATUSES)
            cur = conn.execute(
                f"SELECT * FROM projects WHERE status NOT IN ({placeholders}) ORDER BY continent, country, location",
                list(CLOSED_STATUSES),
            )
        return _fetchall_dicts(cur)


def get_project(project_id):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,))
        return _fetchone_dict(cur)


_UPDATABLE_PROJECT_FIELDS = {
    "continent", "country", "location", "partner_org", "status", "health",
    "blocker", "deployment_type", "timeline_label", "target_date",
    "target_confidence", "hardware", "estimated_cost", "team_owner",
    "devops_id", "notes", "is_at_risk", "item_type", "track_name",
    "start_date", "parent_project_id", "priority", "sparrow", "sparrow_go",
    "robin",
}


def update_project(project_id, updates: dict, updated_by: str = None):
    """Update project fields. Returns the dict of {field: {old, new}} that actually changed."""
    current = get_project(project_id)
    if not current:
        raise ValueError(f"Project {project_id} not found")

    changes = {}
    for field, new_val in updates.items():
        if field not in _UPDATABLE_PROJECT_FIELDS:
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
    allowed = _UPDATABLE_PROJECT_FIELDS | {"project_id", "last_updated", "last_updated_by"}
    cols = [k for k in data.keys() if k in allowed]
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
        new_id = _last_insert_id(cur, conn)
        # Auto-resolve any active nudges for this project
        conn.execute(
            "UPDATE nudges SET resolved = 1, resolved_by_history_id = ? WHERE project_id = ? AND resolved = 0",
            (new_id, project_id),
        )
        return new_id


def get_project_history(project_id, limit=50):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM history WHERE project_id = ? ORDER BY timestamp DESC",
            (project_id,),
        )
        rows = _fetchall_dicts(cur)
        # Limit in Python for cross-backend compat (pyodbc doesn't always support LIMIT)
        result = []
        for d in rows[:limit]:
            d["changes"] = json.loads(d["changes"])
            result.append(d)
        return result


def get_recent_history(days=14, limit=100):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM history WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff,),
        )
        rows = _fetchall_dicts(cur)
        result = []
        for d in rows[:limit]:
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
            rows = _fetchall_dicts(conn.execute("SELECT * FROM contacts"))
            return [r for r in rows
                    if project_id in json.loads(r["linked_projects"] or "[]")]
        return _fetchall_dicts(conn.execute("SELECT * FROM contacts ORDER BY organization, name"))


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
            cur = conn.execute(
                "SELECT * FROM nudges WHERE resolved = 0 AND project_id = ? ORDER BY timestamp DESC",
                (project_id,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM nudges WHERE resolved = 0 ORDER BY severity DESC, timestamp DESC"
            )
        return _fetchall_dicts(cur)


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
        threshold = p.get("stale_threshold_days") or STALENESS_THRESHOLDS.get(p.get("health", "On Track"))
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


def get_phases(project_id):
    """All phases for a project, in ordering order."""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM phases WHERE project_id = ? ORDER BY ordering, id",
            (project_id,),
        )
        return _fetchall_dicts(cur)


def upsert_phases(project_id: str, rows: list):
    """
    Replace a project's phases with the given list.

    Each input row may have an `id` (update existing) or not (create new).
    Rows present in DB but absent from input are deleted.
    Empty-looking rows (no name/start/end) are treated as "not a real phase"
    and skipped — lets the data_editor have blank trailing rows.

    Returns a dict: {"created": [...], "updated": [(id, changes), ...], "deleted": [...]}
    suitable for passing to add_history.
    """
    now = datetime.utcnow().isoformat(timespec="seconds")
    deltas = {"created": [], "updated": [], "deleted": []}

    with get_conn() as conn:
        existing = {r["id"]: r for r in _fetchall_dicts(
            conn.execute("SELECT * FROM phases WHERE project_id = ?", (project_id,))
        )}
        seen_ids = set()

        for i, row in enumerate(rows):
            if not (row.get("name") or row.get("start_date") or row.get("end_date")):
                continue

            payload = {
                "phase_key":          row.get("phase_key") or "custom",
                "name":               row.get("name") or "Untitled phase",
                "ordering":           int(row.get("ordering") if row.get("ordering") is not None else i),
                "start_date":         row.get("start_date") or None,
                "end_date":           row.get("end_date") or None,
                "status":             row.get("status") or "Todo",
                "depends_on_phase_id": row.get("depends_on_phase_id") or None,
                "notes":              row.get("notes") or None,
            }

            row_id = row.get("id")
            if row_id and row_id in existing:
                seen_ids.add(row_id)
                old = existing[row_id]
                changed = {
                    k: {"old": old.get(k), "new": v}
                    for k, v in payload.items()
                    if str(old.get(k) or "") != str(v or "")
                }
                if changed:
                    conn.execute(
                        """UPDATE phases
                           SET phase_key=?, name=?, ordering=?, start_date=?, end_date=?,
                               status=?, depends_on_phase_id=?, notes=?, last_updated=?
                           WHERE id=?""",
                        (payload["phase_key"], payload["name"], payload["ordering"],
                         payload["start_date"], payload["end_date"], payload["status"],
                         payload["depends_on_phase_id"], payload["notes"], now, row_id),
                    )
                    deltas["updated"].append((row_id, changed))
            else:
                cur = conn.execute(
                    """INSERT INTO phases
                       (project_id, phase_key, name, ordering, start_date, end_date,
                        status, depends_on_phase_id, notes, last_updated)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (project_id, payload["phase_key"], payload["name"], payload["ordering"],
                     payload["start_date"], payload["end_date"], payload["status"],
                     payload["depends_on_phase_id"], payload["notes"], now),
                )
                deltas["created"].append({"id": _last_insert_id(cur, conn), **payload})

        for row_id, row in existing.items():
            if row_id not in seen_ids:
                conn.execute("DELETE FROM phases WHERE id = ?", (row_id,))
                deltas["deleted"].append(row)

    return deltas


def apply_phase_change(project_id: str, change: dict):
    """
    Apply a single phase change (typically from the LLM).

    change shape:
      {"phase_id": int|None, "action": "create"|"update"|"delete",
       "field_updates": {name, start_date, end_date, status, ...}}

    Returns a summary dict describing what happened.
    """
    action = (change.get("action") or "update").lower()
    phase_id = change.get("phase_id")
    updates = change.get("field_updates") or {}
    now = datetime.utcnow().isoformat(timespec="seconds")

    with get_conn() as conn:
        if action == "delete":
            if phase_id:
                conn.execute("DELETE FROM phases WHERE id = ? AND project_id = ?",
                             (phase_id, project_id))
            return {"action": "delete", "phase_id": phase_id}

        if action == "create":
            cur = conn.execute(
                """INSERT INTO phases
                   (project_id, phase_key, name, ordering, start_date, end_date,
                    status, notes, last_updated)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (project_id,
                 updates.get("phase_key") or "custom",
                 updates.get("name") or "New phase",
                 int(updates.get("ordering") or 0),
                 updates.get("start_date"), updates.get("end_date"),
                 updates.get("status") or "Todo",
                 updates.get("notes"), now),
            )
            return {"action": "create", "phase_id": _last_insert_id(cur, conn), "field_updates": updates}

        # update
        if not phase_id:
            return {"action": "noop", "reason": "no phase_id given for update"}
        row = _fetchone_dict(conn.execute(
            "SELECT * FROM phases WHERE id = ? AND project_id = ?",
            (phase_id, project_id),
        ))
        if not row:
            return {"action": "noop", "reason": f"phase {phase_id} not found"}
        old = row
        sets, params, changed = [], [], {}
        for k in ("name", "start_date", "end_date", "status", "notes", "phase_key", "ordering"):
            if k in updates and updates[k] is not None:
                if str(old.get(k) or "") != str(updates[k] or ""):
                    sets.append(f"{k} = ?")
                    params.append(updates[k])
                    changed[k] = {"old": old.get(k), "new": updates[k]}
        if sets:
            sets.append("last_updated = ?")
            params.extend([now, phase_id])
            conn.execute(f"UPDATE phases SET {', '.join(sets)} WHERE id = ?", params)
        return {"action": "update", "phase_id": phase_id, "changed": changed}


def get_timeline_rows(include_closed=True):
    """
    Join phases to projects and return rows for the Timeline Gantt.
    One row per phase. Empty list if no phases exist.
    """
    with get_conn() as conn:
        sql = """
            SELECT
                ph.id             AS phase_id,
                ph.project_id     AS project_id,
                ph.phase_key      AS phase_key,
                ph.name           AS phase_name,
                ph.ordering       AS ordering,
                ph.start_date     AS start_date,
                ph.end_date       AS end_date,
                ph.status         AS phase_status,
                ph.depends_on_phase_id AS depends_on_phase_id,
                ph.notes          AS phase_notes,
                p.item_type       AS item_type,
                p.track_name      AS track_name,
                p.continent       AS continent,
                p.country         AS country,
                p.location        AS location,
                p.partner_org     AS partner_org,
                p.status          AS project_status,
                p.health          AS project_health,
                p.is_at_risk      AS is_at_risk,
                p.target_date     AS project_target_date,
                p.last_updated    AS project_last_updated
            FROM phases ph
            JOIN projects p ON p.project_id = ph.project_id
        """
        if not include_closed:
            placeholders = ",".join("?" for _ in CLOSED_STATUSES)
            sql += f" WHERE p.status NOT IN ({placeholders})"
            cur = conn.execute(sql + " ORDER BY p.item_type DESC, p.track_name, p.continent, p.country, ph.ordering", list(CLOSED_STATUSES))
        else:
            cur = conn.execute(sql + " ORDER BY p.item_type DESC, p.track_name, p.continent, p.country, ph.ordering")
        return _fetchall_dicts(cur)


def get_status_summary():
    """Return {status: count} dict."""
    with get_conn() as conn:
        cur = conn.execute("SELECT status, COUNT(*) as cnt FROM projects GROUP BY status")
        rows = _fetchall_dicts(cur)
        return {r["status"]: r["cnt"] for r in rows}

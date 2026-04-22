"""
SPARROW Installation Tracker — Database Layer (Azure SQL via pyodbc)
"""

import json
import pyodbc
from datetime import datetime, date, timedelta
from contextlib import contextmanager

from config import (
    AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USER, AZURE_SQL_PASSWORD,
    STALENESS_THRESHOLDS, DEADLINE_ALERTS, CLOSED_STATUSES,
)


def _conn_str():
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={AZURE_SQL_SERVER};"
        f"DATABASE={AZURE_SQL_DATABASE};"
        f"UID={AZURE_SQL_USER};"
        f"PWD={AZURE_SQL_PASSWORD};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )


def _row_to_dict(cursor, row):
    """Convert a pyodbc Row to a dict using cursor.description."""
    if row is None:
        return None
    return {col[0]: val for col, val in zip(cursor.description, row)}


def _rows_to_dicts(cursor, rows):
    return [_row_to_dict(cursor, r) for r in rows]


@contextmanager
def get_conn():
    conn = pyodbc.connect(_conn_str())
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute(conn, sql, params=None):
    """Execute and return cursor. Handles None params."""
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur


def _fetchall(conn, sql, params=None):
    cur = _execute(conn, sql, params)
    rows = cur.fetchall()
    return _rows_to_dicts(cur, rows)


def _fetchone(conn, sql, params=None):
    cur = _execute(conn, sql, params)
    row = cur.fetchone()
    return _row_to_dict(cur, row)


def _table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
        (table_name,),
    )
    return cur.fetchone()[0] > 0


def _column_exists(conn, table_name, column_name):
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
        (table_name, column_name),
    )
    return cur.fetchone()[0] > 0


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db():
    with get_conn() as conn:
        if not _table_exists(conn, "projects"):
            _execute(conn, """
                CREATE TABLE projects (
                    project_id        NVARCHAR(100) PRIMARY KEY,
                    continent         NVARCHAR(100),
                    country           NVARCHAR(200),
                    location          NVARCHAR(500),
                    partner_org       NVARCHAR(500),
                    status            NVARCHAR(50) NOT NULL DEFAULT 'Scoping',
                    health            NVARCHAR(50) NOT NULL DEFAULT 'On Track',
                    blocker           NVARCHAR(MAX),
                    deployment_type   NVARCHAR(200),
                    timeline_label    NVARCHAR(200),
                    target_date       NVARCHAR(20),
                    target_confidence NVARCHAR(50),
                    hardware          NVARCHAR(200),
                    estimated_cost    FLOAT,
                    team_owner        NVARCHAR(200),
                    devops_id         INT,
                    notes             NVARCHAR(MAX),
                    last_updated      NVARCHAR(30) NOT NULL,
                    last_updated_by   NVARCHAR(200),
                    is_at_risk        BIT NOT NULL DEFAULT 0,
                    priority          NVARCHAR(10),
                    sparrow           BIT NOT NULL DEFAULT 0,
                    sparrow_go        BIT NOT NULL DEFAULT 0,
                    robin             BIT NOT NULL DEFAULT 0,
                    item_type         NVARCHAR(50) NOT NULL DEFAULT 'deployment',
                    track_name        NVARCHAR(200),
                    start_date        NVARCHAR(20),
                    parent_project_id NVARCHAR(100)
                )
            """)

        if not _table_exists(conn, "history"):
            _execute(conn, """
                CREATE TABLE history (
                    id              INT IDENTITY(1,1) PRIMARY KEY,
                    project_id      NVARCHAR(100) NOT NULL,
                    timestamp       NVARCHAR(30) NOT NULL,
                    updated_by      NVARCHAR(200),
                    source_type     NVARCHAR(50),
                    source_text     NVARCHAR(MAX),
                    changes         NVARCHAR(MAX) NOT NULL,
                    llm_summary     NVARCHAR(MAX),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                )
            """)
            _execute(conn, "CREATE INDEX idx_history_project ON history(project_id)")
            _execute(conn, "CREATE INDEX idx_history_ts ON history(timestamp)")

        if not _table_exists(conn, "contacts"):
            _execute(conn, """
                CREATE TABLE contacts (
                    id              INT IDENTITY(1,1) PRIMARY KEY,
                    name            NVARCHAR(200) NOT NULL,
                    organization    NVARCHAR(200),
                    role            NVARCHAR(200),
                    email           NVARCHAR(200),
                    phone           NVARCHAR(50),
                    linked_projects NVARCHAR(MAX),
                    notes           NVARCHAR(MAX)
                )
            """)

        if not _table_exists(conn, "raw_inputs"):
            _execute(conn, """
                CREATE TABLE raw_inputs (
                    id              INT IDENTITY(1,1) PRIMARY KEY,
                    timestamp       NVARCHAR(30) NOT NULL,
                    submitted_by    NVARCHAR(200),
                    input_type      NVARCHAR(50),
                    full_text       NVARCHAR(MAX) NOT NULL,
                    history_ids     NVARCHAR(MAX)
                )
            """)

        if not _table_exists(conn, "nudges"):
            _execute(conn, """
                CREATE TABLE nudges (
                    id              INT IDENTITY(1,1) PRIMARY KEY,
                    project_id      NVARCHAR(100) NOT NULL,
                    timestamp       NVARCHAR(30) NOT NULL,
                    nudge_type      NVARCHAR(50) NOT NULL,
                    severity        NVARCHAR(50) NOT NULL,
                    message         NVARCHAR(MAX) NOT NULL,
                    sent_to         NVARCHAR(200),
                    resolved        BIT NOT NULL DEFAULT 0,
                    resolved_by_history_id INT,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                )
            """)
            _execute(conn, "CREATE INDEX idx_nudges_active ON nudges(resolved, project_id)")

        if not _table_exists(conn, "devops_work_items"):
            _execute(conn, """
                CREATE TABLE devops_work_items (
                    id              INT PRIMARY KEY,
                    title           NVARCHAR(500) NOT NULL,
                    state           NVARCHAR(50),
                    assigned_to     NVARCHAR(200),
                    iteration_path  NVARCHAR(500),
                    work_item_type  NVARCHAR(100),
                    area_path       NVARCHAR(500),
                    tags            NVARCHAR(MAX),
                    linked_project_id NVARCHAR(100),
                    url             NVARCHAR(500),
                    last_synced     NVARCHAR(30),
                    FOREIGN KEY (linked_project_id) REFERENCES projects(project_id)
                )
            """)
            _execute(conn, "CREATE INDEX idx_wi_iteration ON devops_work_items(iteration_path)")
            _execute(conn, "CREATE INDEX idx_wi_assigned ON devops_work_items(assigned_to)")

        if not _table_exists(conn, "phases"):
            _execute(conn, """
                CREATE TABLE phases (
                    id                  INT IDENTITY(1,1) PRIMARY KEY,
                    project_id          NVARCHAR(100) NOT NULL,
                    phase_key           NVARCHAR(50) NOT NULL,
                    name                NVARCHAR(200) NOT NULL,
                    ordering            INT NOT NULL DEFAULT 0,
                    start_date          NVARCHAR(20),
                    end_date            NVARCHAR(20),
                    status              NVARCHAR(50) NOT NULL DEFAULT 'Todo',
                    depends_on_phase_id INT,
                    devops_id           INT,
                    notes               NVARCHAR(MAX),
                    last_updated        NVARCHAR(30) NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id),
                    FOREIGN KEY (depends_on_phase_id) REFERENCES phases(id)
                )
            """)
            _execute(conn, "CREATE INDEX idx_phases_project ON phases(project_id, ordering)")
            _execute(conn, "CREATE INDEX idx_phases_end ON phases(end_date)")

        conn.commit()


# ── Projects ──────────────────────────────────────────────────────────────────

def get_all_projects(include_closed=True):
    with get_conn() as conn:
        if include_closed:
            return _fetchall(conn, "SELECT * FROM projects ORDER BY continent, country, location")
        else:
            placeholders = ",".join("?" for _ in CLOSED_STATUSES)
            return _fetchall(
                conn,
                f"SELECT * FROM projects WHERE status NOT IN ({placeholders}) ORDER BY continent, country, location",
                list(CLOSED_STATUSES),
            )


def get_project(project_id):
    with get_conn() as conn:
        return _fetchone(conn, "SELECT * FROM projects WHERE project_id = ?", (project_id,))


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
        _execute(conn, f"UPDATE projects SET {', '.join(set_parts)} WHERE project_id = ?", params)
    return changes


def create_project(data: dict):
    cols = list(data.keys())
    placeholders = ",".join("?" for _ in cols)
    with get_conn() as conn:
        _execute(
            conn,
            f"INSERT INTO projects ({','.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )


# ── History ───────────────────────────────────────────────────────────────────

def add_history(project_id, changes: dict, source_text: str = None,
                source_type: str = None, updated_by: str = None,
                llm_summary: str = None):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        _execute(
            conn,
            """INSERT INTO history
               (project_id, timestamp, updated_by, source_type, source_text, changes, llm_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, ts, updated_by, source_type, source_text,
             json.dumps(changes), llm_summary),
        )
        # Get the inserted ID
        row_id = _fetchone(conn, "SELECT SCOPE_IDENTITY() AS id")["id"]
        # Auto-resolve any active nudges for this project
        _execute(
            conn,
            "UPDATE nudges SET resolved = 1, resolved_by_history_id = ? WHERE project_id = ? AND resolved = 0",
            (row_id, project_id),
        )
        return int(row_id)


def get_project_history(project_id, limit=50):
    with get_conn() as conn:
        rows = _fetchall(
            conn,
            "SELECT TOP (?) * FROM history WHERE project_id = ? ORDER BY timestamp DESC",
            (limit, project_id),
        )
        for d in rows:
            d["changes"] = json.loads(d["changes"]) if d.get("changes") else {}
        return rows


def get_recent_history(days=14, limit=100):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_conn() as conn:
        rows = _fetchall(
            conn,
            "SELECT TOP (?) * FROM history WHERE timestamp >= ? ORDER BY timestamp DESC",
            (limit, cutoff),
        )
        for d in rows:
            d["changes"] = json.loads(d["changes"]) if d.get("changes") else {}
        return rows


# ── Contacts ──────────────────────────────────────────────────────────────────

def add_contact(name, organization=None, role=None, email=None, phone=None,
                linked_projects=None, notes=None):
    with get_conn() as conn:
        _execute(
            conn,
            """INSERT INTO contacts (name, organization, role, email, phone, linked_projects, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, organization, role, email, phone,
             json.dumps(linked_projects or []), notes),
        )


def get_contacts(project_id=None):
    with get_conn() as conn:
        if project_id:
            rows = _fetchall(conn, "SELECT * FROM contacts")
            return [r for r in rows
                    if project_id in json.loads(r.get("linked_projects") or "[]")]
        return _fetchall(conn, "SELECT * FROM contacts ORDER BY organization, name")


# ── Raw Inputs ────────────────────────────────────────────────────────────────

def add_raw_input(full_text, submitted_by=None, input_type="update", history_ids=None):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        _execute(
            conn,
            "INSERT INTO raw_inputs (timestamp, submitted_by, input_type, full_text, history_ids) VALUES (?,?,?,?,?)",
            (ts, submitted_by, input_type, full_text, json.dumps(history_ids or [])),
        )


# ── Nudges ────────────────────────────────────────────────────────────────────

def add_nudge(project_id, nudge_type, severity, message, sent_to=None):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        _execute(
            conn,
            "INSERT INTO nudges (project_id, timestamp, nudge_type, severity, message, sent_to) VALUES (?,?,?,?,?,?)",
            (project_id, ts, nudge_type, severity, message, sent_to),
        )


def get_active_nudges(project_id=None):
    with get_conn() as conn:
        if project_id:
            return _fetchall(
                conn,
                "SELECT * FROM nudges WHERE resolved = 0 AND project_id = ? ORDER BY timestamp DESC",
                (project_id,),
            )
        else:
            return _fetchall(
                conn,
                "SELECT * FROM nudges WHERE resolved = 0 ORDER BY severity DESC, timestamp DESC",
            )


def resolve_nudge(nudge_id, history_id=None):
    with get_conn() as conn:
        _execute(
            conn,
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
        threshold = STALENESS_THRESHOLDS.get(p.get("health", "On Track"))
        if threshold is None:
            continue
        try:
            last = datetime.fromisoformat(p["last_updated"])
        except (ValueError, TypeError):
            continue
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
        return _fetchall(
            conn,
            "SELECT * FROM phases WHERE project_id = ? ORDER BY ordering, id",
            (project_id,),
        )


def upsert_phases(project_id: str, rows: list):
    """Replace a project's phases with the given list."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    deltas = {"created": [], "updated": [], "deleted": []}

    with get_conn() as conn:
        existing = {
            r["id"]: r for r in _fetchall(
                conn, "SELECT * FROM phases WHERE project_id = ?", (project_id,)
            )
        }
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
                    _execute(conn,
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
                _execute(conn,
                    """INSERT INTO phases
                       (project_id, phase_key, name, ordering, start_date, end_date,
                        status, depends_on_phase_id, notes, last_updated)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (project_id, payload["phase_key"], payload["name"], payload["ordering"],
                     payload["start_date"], payload["end_date"], payload["status"],
                     payload["depends_on_phase_id"], payload["notes"], now),
                )
                new_id = _fetchone(conn, "SELECT SCOPE_IDENTITY() AS id")["id"]
                deltas["created"].append({"id": int(new_id), **payload})

        for row_id in existing:
            if row_id not in seen_ids:
                _execute(conn, "DELETE FROM phases WHERE id = ?", (row_id,))
                deltas["deleted"].append(existing[row_id])

    return deltas


def apply_phase_change(project_id: str, change: dict):
    """Apply a single phase change (typically from the LLM)."""
    action = (change.get("action") or "update").lower()
    phase_id = change.get("phase_id")
    updates = change.get("field_updates") or {}
    now = datetime.utcnow().isoformat(timespec="seconds")

    with get_conn() as conn:
        if action == "delete":
            if phase_id:
                _execute(conn, "DELETE FROM phases WHERE id = ? AND project_id = ?",
                         (phase_id, project_id))
            return {"action": "delete", "phase_id": phase_id}

        if action == "create":
            _execute(conn,
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
            new_id = _fetchone(conn, "SELECT SCOPE_IDENTITY() AS id")["id"]
            return {"action": "create", "phase_id": int(new_id), "field_updates": updates}

        # update
        if not phase_id:
            return {"action": "noop", "reason": "no phase_id given for update"}
        row = _fetchone(conn,
            "SELECT * FROM phases WHERE id = ? AND project_id = ?",
            (phase_id, project_id),
        )
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
            _execute(conn, f"UPDATE phases SET {', '.join(sets)} WHERE id = ?", params)
        return {"action": "update", "phase_id": phase_id, "changed": changed}


def get_timeline_rows(include_closed=True):
    """Join phases to projects for the Timeline Gantt."""
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
            return _fetchall(conn,
                sql + " ORDER BY p.item_type DESC, p.track_name, p.continent, p.country, ph.ordering",
                list(CLOSED_STATUSES))
        else:
            return _fetchall(conn,
                sql + " ORDER BY p.item_type DESC, p.track_name, p.continent, p.country, ph.ordering")


def get_status_summary():
    """Return {status: count} dict."""
    with get_conn() as conn:
        rows = _fetchall(conn, "SELECT status, COUNT(*) as cnt FROM projects GROUP BY status")
        return {r["status"]: r["cnt"] for r in rows}

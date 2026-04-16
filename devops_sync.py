"""
SPARROW Installation Tracker — Azure DevOps Sync

Pulls iterations (sprints) and work items from Azure DevOps REST API,
stores them locally in the devops_work_items / devops_iterations tables.
"""

import base64
import json
from datetime import datetime

import requests

from config import (
    AZURE_DEVOPS_ORG,
    AZURE_DEVOPS_PROJECT,
    AZURE_DEVOPS_PAT,
    DEVOPS_SEARCH_TERMS,
)
from db import get_conn


# ── Auth & URL helpers ───────────────────────────────────────────────────────

def _auth_headers():
    """Return HTTP headers with Basic auth using the PAT."""
    if not AZURE_DEVOPS_PAT:
        raise RuntimeError("AZURE_DEVOPS_PAT is not configured. Set it in .env.")
    token = base64.b64encode(f":{AZURE_DEVOPS_PAT}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _api_url(path: str) -> str:
    """Build a full Azure DevOps REST API URL.

    Supports both dev.azure.com and visualstudio.com style URLs.
    """
    org = AZURE_DEVOPS_ORG
    project = AZURE_DEVOPS_PROJECT
    base = f"https://dev.azure.com/{org}/{project}/_apis"
    return f"{base}/{path}"


# ── Iterations (Sprints) ────────────────────────────────────────────────────

def fetch_iterations() -> list[dict]:
    """Fetch all iterations (sprints) for the project from DevOps."""
    url = _api_url("work/teamsettings/iterations?api-version=7.1")
    resp = requests.get(url, headers=_auth_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def sync_iterations() -> int:
    """Fetch iterations from DevOps and upsert into the local DB. Returns count."""
    iterations = fetch_iterations()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        for it in iterations:
            attrs = it.get("attributes", {})
            conn.execute(
                """INSERT INTO devops_iterations (id, name, path, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       name = excluded.name,
                       path = excluded.path,
                       start_date = excluded.start_date,
                       end_date = excluded.end_date""",
                (
                    it["id"],
                    it["name"],
                    it.get("path", ""),
                    attrs.get("startDate"),
                    attrs.get("finishDate"),
                ),
            )
    return len(iterations)


# ── Work Items ───────────────────────────────────────────────────────────────

def _build_wiql(search_terms: list[str] = None) -> str:
    """Build a WIQL query that finds work items matching any search term."""
    terms = search_terms or DEVOPS_SEARCH_TERMS
    clauses = []
    for term in terms:
        t = term.replace("'", "''")
        clauses.append(f"[System.Title] CONTAINS '{t}'")
        clauses.append(f"[System.Tags] CONTAINS '{t}'")
        clauses.append(f"[System.AreaPath] CONTAINS '{t}'")
    where = " OR ".join(clauses)
    return (
        "SELECT [System.Id] FROM WorkItems "
        f"WHERE ({where}) "
        "AND [System.State] <> 'Removed' "
        "ORDER BY [System.ChangedDate] DESC"
    )


def fetch_work_item_ids(search_terms: list[str] = None) -> list[int]:
    """Run a WIQL query and return matching work item IDs."""
    url = _api_url("wit/wiql?api-version=7.1")
    wiql = _build_wiql(search_terms)
    resp = requests.post(url, headers=_auth_headers(), json={"query": wiql}, timeout=30)
    resp.raise_for_status()
    return [item["id"] for item in resp.json().get("workItems", [])]


def fetch_work_item_details(ids: list[int]) -> list[dict]:
    """Fetch full details for a batch of work item IDs (max 200 per call)."""
    if not ids:
        return []
    all_items = []
    # DevOps API allows max 200 IDs per batch
    for i in range(0, len(ids), 200):
        batch = ids[i:i + 200]
        id_str = ",".join(str(x) for x in batch)
        fields = (
            "System.Id,System.Title,System.State,System.AssignedTo,"
            "System.IterationPath,System.WorkItemType,System.AreaPath,"
            "System.Tags"
        )
        url = _api_url(f"wit/workitems?ids={id_str}&fields={fields}&api-version=7.1")
        resp = requests.get(url, headers=_auth_headers(), timeout=30)
        resp.raise_for_status()
        all_items.extend(resp.json().get("value", []))
    return all_items


def sync_work_items(search_terms: list[str] = None) -> int:
    """Fetch work items from DevOps and upsert into local DB. Returns count."""
    ids = fetch_work_item_ids(search_terms)
    items = fetch_work_item_details(ids)
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        for item in items:
            fields = item.get("fields", {})
            assigned = fields.get("System.AssignedTo", {})
            assigned_name = assigned.get("displayName", "") if isinstance(assigned, dict) else str(assigned)
            item_id = item.get("id") or fields.get("System.Id")
            item_url = item.get("url", "")
            # Build a web URL from the API URL
            web_url = (
                f"https://dev.azure.com/{AZURE_DEVOPS_ORG}/{AZURE_DEVOPS_PROJECT}/"
                f"_workitems/edit/{item_id}"
            )
            conn.execute(
                """INSERT INTO devops_work_items
                   (id, title, state, assigned_to, iteration_path, work_item_type,
                    area_path, tags, url, last_synced)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       title = excluded.title,
                       state = excluded.state,
                       assigned_to = excluded.assigned_to,
                       iteration_path = excluded.iteration_path,
                       work_item_type = excluded.work_item_type,
                       area_path = excluded.area_path,
                       tags = excluded.tags,
                       url = excluded.url,
                       last_synced = excluded.last_synced""",
                (
                    item_id,
                    fields.get("System.Title", ""),
                    fields.get("System.State", ""),
                    assigned_name,
                    fields.get("System.IterationPath", ""),
                    fields.get("System.WorkItemType", ""),
                    fields.get("System.AreaPath", ""),
                    fields.get("System.Tags", ""),
                    web_url,
                    now,
                ),
            )
    return len(items)


# ── Full Sync ────────────────────────────────────────────────────────────────

def sync_all() -> dict:
    """Run full sync: iterations + work items. Returns summary counts."""
    iter_count = sync_iterations()
    wi_count = sync_work_items()
    return {"iterations": iter_count, "work_items": wi_count}


# ── Query Helpers (for UI) ───────────────────────────────────────────────────

def get_iterations() -> list[dict]:
    """Return all iterations from local DB, ordered by start date."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM devops_iterations ORDER BY start_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_work_items(iteration_path: str = None, assigned_to: str = None,
                   state: str = None) -> list[dict]:
    """Return work items from local DB with optional filters."""
    clauses = []
    params = []
    if iteration_path:
        clauses.append("iteration_path = ?")
        params.append(iteration_path)
    if assigned_to:
        clauses.append("assigned_to LIKE ?")
        params.append(f"%{assigned_to}%")
    if state:
        clauses.append("state = ?")
        params.append(state)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM devops_work_items {where} ORDER BY iteration_path, assigned_to, title",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_work_items_by_sprint() -> dict[str, list[dict]]:
    """Return work items grouped by iteration path (sprint)."""
    items = get_work_items()
    grouped = {}
    for item in items:
        sprint = item.get("iteration_path") or "Unassigned"
        grouped.setdefault(sprint, []).append(item)
    return grouped


def get_work_items_by_person() -> dict[str, list[dict]]:
    """Return work items grouped by assigned person."""
    items = get_work_items()
    grouped = {}
    for item in items:
        person = item.get("assigned_to") or "Unassigned"
        grouped.setdefault(person, []).append(item)
    return grouped


def get_last_sync_time() -> str | None:
    """Return the most recent last_synced timestamp from work items, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(last_synced) as ts FROM devops_work_items"
        ).fetchone()
        return row["ts"] if row and row["ts"] else None

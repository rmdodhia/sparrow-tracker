"""
SPARROW Installation Tracker — Azure DevOps Sync

Pulls work items from Azure DevOps and stores them in devops_work_items.
Sprint grouping comes from each item's iteration_path — no separate sprint table.
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
    DEVOPS_SPRINT_QUERY_ID,
)
from db import get_conn


NO_SPRINT_LABEL = "No sprint assigned"


# ── Auth & URL helpers ───────────────────────────────────────────────────────

# Azure DevOps resource ID — same for every tenant/org.
_AZDO_RESOURCE = "499b84ac-1321-427f-aea8-67e1a0fd4a0d"
_AZDO_SCOPE = f"{_AZDO_RESOURCE}/.default"

_cached_credential = None


def _get_entra_token() -> str:
    """Acquire an Entra ID (Azure AD) bearer token for Azure DevOps.

    Uses DefaultAzureCredential, which tries env-var service principal,
    managed identity, VS Code, Azure CLI (`az login`), etc. in order.
    """
    global _cached_credential
    if _cached_credential is None:
        from azure.identity import DefaultAzureCredential
        _cached_credential = DefaultAzureCredential()
    # get_token handles refresh internally.
    return _cached_credential.get_token(_AZDO_SCOPE).token


def _auth_headers():
    """Return HTTP headers. Prefers Entra ID; falls back to PAT if set."""
    if AZURE_DEVOPS_PAT:
        token = base64.b64encode(f":{AZURE_DEVOPS_PAT}".encode()).decode()
        auth = f"Basic {token}"
    else:
        try:
            auth = f"Bearer {_get_entra_token()}"
        except Exception as e:
            raise RuntimeError(
                "Azure DevOps auth failed. Either run `az login` (preferred) "
                "or set AZURE_DEVOPS_PAT in .env. "
                f"Underlying error: {e}"
            ) from e
    return {
        "Authorization": auth,
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


# ── Work Items ───────────────────────────────────────────────────────────────

def _build_wiql(search_terms: list[str] = None) -> str:
    """Build a WIQL query that finds work items matching any search term.

    Note: WIQL rejects CONTAINS on tree-path fields (AreaPath, IterationPath) —
    those only support UNDER with an exact path. We match Title and Tags only.
    """
    terms = search_terms or DEVOPS_SEARCH_TERMS
    clauses = []
    for term in terms:
        t = term.replace("'", "''")
        clauses.append(f"[System.Title] CONTAINS WORDS '{t}'")
        clauses.append(f"[System.Tags] CONTAINS '{t}'")
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


def fetch_work_item_ids_from_saved_query(query_id: str) -> list[int]:
    """Run a saved DevOps query by ID and return matching work item IDs."""
    url = _api_url(f"wit/wiql/{query_id}?api-version=7.1")
    resp = requests.get(url, headers=_auth_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Flat queries return workItems; tree/one-hop queries return workItemRelations.
    items = data.get("workItems") or []
    if items:
        return [it["id"] for it in items]
    relations = data.get("workItemRelations") or []
    seen = set()
    ids = []
    for rel in relations:
        target = rel.get("target") or {}
        tid = target.get("id")
        if tid and tid not in seen:
            seen.add(tid)
            ids.append(tid)
    return ids


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


def _upsert_items(items: list[dict]) -> int:
    """Upsert a list of DevOps work-item payloads into the local DB."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        for item in items:
            fields = item.get("fields", {})
            assigned = fields.get("System.AssignedTo", {})
            assigned_name = assigned.get("displayName", "") if isinstance(assigned, dict) else str(assigned)
            item_id = item.get("id") or fields.get("System.Id")
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


def sync_work_items(search_terms: list[str] = None) -> int:
    """Fetch work items by term search and upsert into local DB. Returns count."""
    ids = fetch_work_item_ids(search_terms)
    items = fetch_work_item_details(ids)
    return _upsert_items(items)


def sync_from_saved_query(query_id: str = None) -> int:
    """Fetch work items from a saved DevOps query and upsert. Returns count.

    Defaults to the sprint query configured in config.DEVOPS_SPRINT_QUERY_ID.
    """
    qid = query_id or DEVOPS_SPRINT_QUERY_ID
    ids = fetch_work_item_ids_from_saved_query(qid)
    items = fetch_work_item_details(ids)
    return _upsert_items(items)


# ── Full Sync ────────────────────────────────────────────────────────────────

def sync_all() -> dict:
    """Run full sync: broad term-search work items + sprint saved query.
    Returns summary counts.
    """
    wi_count = sync_work_items()
    sprint_count = sync_from_saved_query()
    return {
        "work_items": wi_count,
        "sprint_query": sprint_count,
    }


# ── Query Helpers (for UI) ───────────────────────────────────────────────────

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


# States hidden on the Sprints page — finished or cancelled work.
HIDDEN_SPRINT_STATES = {"Closed", "Done", "Removed", "Cancelled", "Abandoned"}


def _is_sprint_visible(item: dict) -> bool:
    return (item.get("state") or "") not in HIDDEN_SPRINT_STATES


def _sprint_label(iteration_path: str) -> str | None:
    """Extract a sprint name from an iteration_path.

    Only paths under our project are considered a sprint; anything else
    (e.g. another team's iteration path that matched a search term) returns
    None and should be hidden. A path that is just the project root means
    the item has no sprint assigned — we return NO_SPRINT_LABEL.
    """
    if not iteration_path:
        return NO_SPRINT_LABEL
    project = AZURE_DEVOPS_PROJECT
    if iteration_path == project:
        return NO_SPRINT_LABEL
    prefix = project + "\\"
    if not iteration_path.startswith(prefix):
        return None  # different team's sprint — hide
    # Return the last segment as the sprint name.
    return iteration_path[len(prefix):].split("\\")[-1]


def get_work_items_by_sprint() -> dict[str, list[dict]]:
    """Return active work items grouped by sprint name (last segment of
    iteration_path under our project). Items from other teams' iteration
    paths are dropped. Closed/Removed/Cancelled/Abandoned are excluded.
    """
    grouped = {}
    for item in get_work_items():
        if not _is_sprint_visible(item):
            continue
        sprint = _sprint_label(item.get("iteration_path", ""))
        if sprint is None:
            continue
        grouped.setdefault(sprint, []).append(item)
    return grouped


def get_work_items_by_person() -> dict[str, list[dict]]:
    """Return active work items grouped by assigned person.
    Closed/Removed/Cancelled/Abandoned items are excluded.
    """
    grouped = {}
    for item in get_work_items():
        if not _is_sprint_visible(item):
            continue
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

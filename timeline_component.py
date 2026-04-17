"""
Timeline Gantt rendered with vis-timeline inside an st.components.v1.html iframe.

Why vis-timeline over Plotly px.timeline: purpose-built for swim-lane Gantt
views, cleaner typography, real per-item CSS control, foldable nested groups
for DEVELOPMENT / DEPLOYMENTS sections, and we can lay a custom SVG overlay
on top for elbow-style dependency connectors.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import streamlit.components.v1 as components


# ── Status → CSS class ──────────────────────────────────────────────────────

def _status_class(status: str) -> str:
    return "status-" + (status or "planned").lower().replace(" ", "-")


# ── Payload builder ─────────────────────────────────────────────────────────

def build_payload(rows: list[dict], today: date) -> dict:
    """
    Turn get_timeline_rows() output into the JSON shape vis-timeline expects,
    plus our dependency list for the SVG overlay.

    Groups come out in two sections (DEVELOPMENT, DEPLOYMENTS) using
    nestedGroups so the user can fold either section.
    """
    dev_rows = [r for r in rows if r["item_type"] == "dev_track"]
    deploy_rows = [r for r in rows if r["item_type"] != "dev_track"]

    # Dedup by project_id, preserving order
    def _uniq_pids(rs):
        seen, out = set(), []
        for r in rs:
            pid = r["project_id"]
            if pid in seen:
                continue
            seen.add(pid)
            out.append(r)
        return out

    dev_unique = _uniq_pids(dev_rows)
    deploy_unique = _uniq_pids(deploy_rows)

    groups = []
    if dev_unique:
        groups.append({
            "id": "_sec_dev",
            "content": "DEVELOPMENT",
            "className": "section-header",
            "nestedGroups": [r["project_id"] for r in dev_unique],
        })
        for r in dev_unique:
            groups.append({
                "id": r["project_id"],
                "content": r.get("track_name") or r["project_id"],
                "className": "track-label",
            })

    if deploy_unique:
        groups.append({
            "id": "_sec_deploy",
            "content": "DEPLOYMENTS",
            "className": "section-header",
            "nestedGroups": [r["project_id"] for r in deploy_unique],
        })
        for r in deploy_unique:
            loc = r.get("location") or r.get("partner_org") or r["project_id"]
            country = r.get("country") or ""
            label = f"{country} — {loc}" if country else loc
            groups.append({
                "id": r["project_id"],
                "content": label,
                "className": "track-label deployment-label",
            })

    items = []
    dependencies = []
    status_by_phase = {r["phase_id"]: r["phase_status"] for r in rows}

    for r in rows:
        start, end = r.get("start_date"), r.get("end_date")
        if not start and not end:
            continue
        if not start:
            start = end
        if not end:
            end = start

        title_html = (
            f"<b>{_html_escape(r['phase_name'])}</b><br>"
            f"<span style='color:#64748b'>{_html_escape(r['project_id'])} · "
            f"{_html_escape(r['phase_status'])}</span><br>"
            f"{start} → {end}"
        )
        if r.get("partner_org"):
            title_html += f"<br>Partner: {_html_escape(r['partner_org'])}"
        if r.get("project_target_date"):
            title_html += f"<br>Project target: {r['project_target_date']}"

        items.append({
            "id": r["phase_id"],
            "group": r["project_id"],
            "start": start,
            "end": end,
            "content": _html_escape(r["phase_name"]),
            "className": _status_class(r["phase_status"]),
            "title": title_html,
        })

        dep_id = r.get("depends_on_phase_id")
        if dep_id:
            upstream_status = status_by_phase.get(dep_id)
            blocking = upstream_status not in ("Done", "Cancelled")
            dependencies.append({
                "from": dep_id,
                "to": r["phase_id"],
                "blocking": blocking,
            })

    # View window: pad the observed span by a bit so bars aren't flush with edges.
    all_dates = [d for r in rows for d in (r.get("start_date"), r.get("end_date")) if d]
    if all_dates:
        try:
            min_d = min(date.fromisoformat(d) for d in all_dates) - timedelta(days=30)
            max_d = max(date.fromisoformat(d) for d in all_dates) + timedelta(days=45)
        except ValueError:
            min_d = today - timedelta(days=180)
            max_d = today + timedelta(days=365)
    else:
        min_d = today - timedelta(days=180)
        max_d = today + timedelta(days=365)

    return {
        "groups": groups,
        "items": items,
        "dependencies": dependencies,
        "view_start": min_d.isoformat(),
        "view_end": max_d.isoformat(),
        "today": today.isoformat(),
    }


def _html_escape(s):
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ── HTML template ───────────────────────────────────────────────────────────
#
# The template is deliberately self-contained: vis-timeline from CDN, our
# CSS palette inline, a small JS block that initializes the timeline and
# maintains the dependency-arrow SVG overlay on zoom/pan/redraw.

_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/styles/vis-timeline-graph2d.min.css" />
<style>
  :root {
    --slate-50:  #f8fafc;
    --slate-100: #f1f5f9;
    --slate-200: #e2e8f0;
    --slate-300: #cbd5e1;
    --slate-400: #94a3b8;
    --slate-500: #64748b;
    --slate-600: #475569;
    --slate-700: #334155;
    --slate-800: #1e293b;
    --blue-700:  #1d4ed8;
    --amber-600: #d97706;
    --red-700:   #b91c1c;
    --red-600:   #dc2626;
  }
  html, body {
    margin: 0; padding: 0;
    font-family: Inter, "Segoe UI", -apple-system, Arial, sans-serif;
    color: var(--slate-700);
    background: #fff;
    font-size: 12px;
  }
  #wrap {
    position: relative;
    background: #fff;
    border: 1px solid var(--slate-200);
    border-radius: 10px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.06);
    overflow: hidden;
  }
  #timeline { position: relative; z-index: 1; }
  #deps-svg {
    position: absolute;
    pointer-events: none;
    top: 0; left: 0;
    z-index: 5;
    overflow: visible;
  }

  /* ── vis-timeline skeletal overrides ── */
  .vis-timeline {
    border: none;
    font-family: inherit;
  }
  .vis-panel.vis-center,
  .vis-panel.vis-left,
  .vis-panel.vis-right,
  .vis-panel.vis-top,
  .vis-panel.vis-bottom {
    border-color: var(--slate-200);
  }
  .vis-labelset .vis-label {
    color: var(--slate-700);
    font-size: 12px;
    padding: 4px 12px;
    border-bottom: 1px solid var(--slate-100);
  }
  .vis-labelset .vis-label.track-label { font-weight: 500; }
  .vis-labelset .vis-label.deployment-label {
    color: var(--slate-600);
    font-weight: 400;
  }
  .vis-labelset .vis-label.section-header {
    background: var(--slate-50);
    color: var(--slate-500);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.7px;
    text-transform: uppercase;
    padding: 8px 12px;
    border-bottom: 1px solid var(--slate-200);
    border-top: 1px solid var(--slate-200);
  }

  .vis-foreground .vis-group { border-bottom: 1px solid var(--slate-100); }
  .vis-foreground .vis-group.section-header { background: var(--slate-50); }

  .vis-time-axis .vis-text {
    color: var(--slate-500);
    font-size: 11px;
  }
  .vis-time-axis .vis-grid.vis-minor { border-color: #eef2f6; }
  .vis-time-axis .vis-grid.vis-major { border-color: var(--slate-200); }

  /* ── Item (bar) styling by status ── */
  .vis-item {
    border-radius: 3px;
    border-width: 1px;
    font-family: inherit;
    font-size: 11px;
    font-weight: 500;
    padding-left: 6px;
    padding-right: 6px;
  }
  .vis-item .vis-item-content { padding: 3px 4px; }

  .vis-item.status-planned     { background: var(--slate-300); border-color: var(--slate-400); color: var(--slate-800); }
  .vis-item.status-in-progress { background: var(--blue-700);  border-color: #1e40af;          color: #fff; }
  .vis-item.status-done        { background: var(--slate-600); border-color: var(--slate-700); color: #fff; }
  .vis-item.status-blocked     { background: var(--red-700);   border-color: #991b1b;          color: #fff; }
  .vis-item.status-at-risk     { background: var(--amber-600); border-color: #b45309;          color: #fff; }
  .vis-item.status-on-hold     { background: var(--slate-200); border-color: var(--slate-300); color: var(--slate-700); }
  .vis-item.status-cancelled   { background: var(--slate-100); border-color: var(--slate-200); color: var(--slate-500); }

  .vis-item.vis-selected {
    box-shadow: 0 0 0 2px rgba(29,78,216,0.25);
    border-color: var(--blue-700);
  }

  .vis-current-time { background: var(--red-600); width: 2px; z-index: 4; }

  /* Tooltip */
  .vis-tooltip {
    background: #1e293b;
    color: #e2e8f0;
    border: none;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 12px;
    box-shadow: 0 4px 12px rgba(15,23,42,0.15);
    font-family: inherit;
  }
</style>
</head>
<body>
<div id="wrap">
  <div id="timeline"></div>
  <svg id="deps-svg"></svg>
</div>

<script src="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/standalone/umd/vis-timeline-graph2d.min.js"></script>
<script>
  const PAYLOAD = __PAYLOAD__;

  const container = document.getElementById('timeline');
  const groups = new vis.DataSet(PAYLOAD.groups);
  const items = new vis.DataSet(PAYLOAD.items);

  const options = {
    stack: false,
    orientation: { axis: 'top', item: 'top' },
    showCurrentTime: false,              // we draw our own "today" line via SVG marker
    zoomable: true,
    horizontalScroll: true,
    verticalScroll: true,
    zoomMin: 1000 * 60 * 60 * 24 * 30,   // 1 month
    zoomMax: 1000 * 60 * 60 * 24 * 365 * 5, // 5 years
    start: PAYLOAD.view_start,
    end: PAYLOAD.view_end,
    margin: { item: { vertical: 6, horizontal: 0 }, axis: 40 },
    tooltip: { followMouse: false, overflowMethod: 'cap' },
    groupOrder: null, // preserve our payload order
  };

  const timeline = new vis.Timeline(container, items, groups, options);

  // Custom today marker (rendered via vis-timeline's built-in addCustomTime for accuracy).
  timeline.addCustomTime(new Date(PAYLOAD.today), 'today');

  // ── Dependency-arrow overlay ────────────────────────────────────────────
  const svg = document.getElementById('deps-svg');
  const NS = 'http://www.w3.org/2000/svg';

  function drawDeps() {
    const wrap = document.getElementById('wrap').getBoundingClientRect();
    const centerPanel = container.querySelector('.vis-panel.vis-center');
    if (!centerPanel) return;
    const centerRect = centerPanel.getBoundingClientRect();

    svg.setAttribute('width',  wrap.width);
    svg.setAttribute('height', wrap.height);
    // Clip drawing to the center-panel area so arrows don't spill into the label column.
    svg.innerHTML = `<defs>
      <clipPath id="center-clip">
        <rect x="${centerRect.left - wrap.left}" y="${centerRect.top - wrap.top}"
              width="${centerRect.width}" height="${centerRect.height}" />
      </clipPath>
    </defs><g clip-path="url(#center-clip)"></g>`;
    const g = svg.querySelector('g');

    for (const dep of PAYLOAD.dependencies) {
      const upEl = findItemEl(dep.from);
      const downEl = findItemEl(dep.to);
      if (!upEl || !downEl) continue;

      const up = upEl.getBoundingClientRect();
      const down = downEl.getBoundingClientRect();

      // Elbow path: right-edge of upstream bar → horizontal to downstream start x →
      // vertical to the downstream bar's mid-y.
      const x1 = up.right - wrap.left;
      const y1 = up.top + up.height / 2 - wrap.top;
      const x2 = down.left - wrap.left;
      const y2 = down.top + down.height / 2 - wrap.top;

      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', `M ${x1},${y1} L ${x2 - 6},${y1} L ${x2 - 6},${y2} L ${x2 - 1},${y2}`);
      path.setAttribute('fill', 'none');
      if (dep.blocking) {
        path.setAttribute('stroke', '#d97706');
        path.setAttribute('stroke-width', '1.6');
      } else {
        path.setAttribute('stroke', '#94a3b8');
        path.setAttribute('stroke-width', '1');
        path.setAttribute('stroke-dasharray', '3,3');
      }
      path.setAttribute('opacity', '0.9');
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('stroke-linejoin', 'round');
      g.appendChild(path);

      // Small arrowhead triangle at the downstream edge
      const tip = document.createElementNS(NS, 'path');
      tip.setAttribute('d', `M ${x2},${y2} l -5,-3 l 0,6 z`);
      tip.setAttribute('fill', dep.blocking ? '#d97706' : '#94a3b8');
      tip.setAttribute('opacity', '0.9');
      g.appendChild(tip);
    }
  }

  function findItemEl(id) {
    // vis-timeline labels items internally; we find them by data ranges.
    const internal = timeline.itemSet && timeline.itemSet.items && timeline.itemSet.items[id];
    if (internal && internal.dom && internal.dom.box) return internal.dom.box;
    return null;
  }

  timeline.on('changed', drawDeps);
  timeline.on('rangechanged', drawDeps);
  window.addEventListener('resize', drawDeps);
  // First draw once the DOM has settled.
  setTimeout(drawDeps, 200);

  // Let Streamlit size the iframe to the natural content height.
  function pingHeight() {
    const h = document.body.scrollHeight;
    if (window.parent) {
      window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
    }
  }
  setTimeout(pingHeight, 300);
  new ResizeObserver(pingHeight).observe(document.body);
</script>
</body>
</html>
"""


# ── Public entrypoint ───────────────────────────────────────────────────────

def render_timeline(rows: list[dict], today: date | None = None, height: int = 700):
    """Render the SPARROW Gantt inside a Streamlit component."""
    if today is None:
        today = date.today()
    payload = build_payload(rows, today)
    html = _TEMPLATE.replace("__PAYLOAD__", json.dumps(payload))
    components.html(html, height=height, scrolling=True)
    return payload  # returned so the caller can compute KPIs from the same source

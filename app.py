"""
SPARROW Installation Tracker — Flask App (v2 Conservation Field Design)

Run:  flask run --debug
"""

import json
import getpass
import os
import pwd
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, url_for, jsonify

from db import (
    init_db, get_all_projects, get_project, update_project,
    add_history, get_project_history, get_recent_history,
    add_contact, get_contacts, add_raw_input,
    get_active_nudges, get_status_summary,
    get_stale_projects, get_deadline_approaching,
    get_timeline_rows,
)
from config import (
    VALID_STATUSES, VALID_HEALTH, VALID_PRIORITIES, CLOSED_STATUSES,
    TEAM_MEMBERS, AZURE_OPENAI_ENDPOINT, STALENESS_THRESHOLDS,
)

app = Flask(__name__)
app.secret_key = "sparrow-tracker-v2"

init_db()

llm_available = bool(AZURE_OPENAI_ENDPOINT)


def _current_session_user():
    """Best-effort identity for the currently logged-in local user."""
    username = getpass.getuser()
    display_name = username
    try:
        gecos = pwd.getpwnam(username).pw_gecos.split(",", 1)[0].strip()
        if gecos:
            display_name = gecos
    except KeyError:
        pass

    email = os.environ.get("EMAIL", "").strip() or "Local session"
    name_source = display_name if display_name else username
    parts = [part[0].upper() for part in name_source.replace("_", " ").replace(".", " ").split() if part]
    initials = "".join(parts[:2]) or username[:2].upper()

    return {
        "name": display_name,
        "email": email,
        "initials": initials,
    }


# ── Template helpers ─────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    """Make common values available to all templates."""
    projects = get_all_projects()
    current_user = _current_session_user()
    current_project_id = None
    if request.endpoint == "project_details":
        current_project_id = (request.view_args or {}).get("project_id")

    if current_project_id:
        project_details_url = url_for("project_details", project_id=current_project_id)
    elif projects:
        project_details_url = url_for("project_details", project_id=projects[0]["project_id"])
    else:
        project_details_url = url_for("dashboard")

    return dict(
        today=date.today(),
        total_projects=len(projects),
        llm_available=llm_available,
        current_user=current_user,
        project_details_url=project_details_url,
        VALID_STATUSES=VALID_STATUSES,
        VALID_HEALTH=VALID_HEALTH,
        VALID_PRIORITIES=VALID_PRIORITIES,
        TEAM_MEMBERS=TEAM_MEMBERS,
    )


@app.template_filter("timeago")
def timeago_filter(dt_str):
    """Convert an ISO datetime string to a relative time like '2 hours ago'."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return dt_str
    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = int(seconds // 60)
        return f"{m}m ago"
    if seconds < 86400:
        h = int(seconds // 3600)
        return f"{h}h ago"
    d = int(seconds // 86400)
    if d == 1:
        return "yesterday"
    if d < 30:
        return f"{d}d ago"
    if d < 365:
        mo = d // 30
        return f"{mo}mo ago"
    return dt.strftime("%Y-%m-%d")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    projects = get_all_projects()
    continents = len(set(p["continent"] for p in projects if p.get("continent")))
    countries = len(set(p["country"] for p in projects if p.get("country")))
    active = sum(1 for p in projects if p["status"] == "Active")
    completed = sum(1 for p in projects if p["status"] == "Complete")

    summary = get_status_summary()
    stale = get_stale_projects()
    deadline = get_deadline_approaching()
    attention = stale + [
        d for d in deadline
        if d["project_id"] not in {s["project_id"] for s in stale}
    ]
    recent = get_recent_history(limit=10)

    return render_template(
        "dashboard.html",
        projects=projects,
        continents=continents,
        countries=countries,
        active=active,
        completed=completed,
        summary=summary,
        attention=attention,
        recent=recent,
    )


@app.route("/project/<project_id>")
def project_details(project_id):
    p = get_project(project_id)
    if not p:
        return "Project not found", 404
    history = get_project_history(project_id)
    contacts = get_contacts(project_id)
    nudges = get_active_nudges()
    project_nudges = [n for n in nudges if n.get("project_id") == project_id]

    # Target date info
    target_sub = ""
    target_sub_color = "#6d6358"
    if p.get("target_date"):
        try:
            td = date.fromisoformat(p["target_date"])
            days_left = (td - date.today()).days
            if days_left < 0:
                target_sub = f"{-days_left}d overdue"
                target_sub_color = "#c62828"
            else:
                target_sub = f"{days_left} days left"
                target_sub_color = "#2e7d32"
        except ValueError:
            pass

    return render_template(
        "project_details.html",
        p=p,
        history=history,
        contacts=contacts,
        nudges=project_nudges,
        target_sub=target_sub,
        target_sub_color=target_sub_color,
    )


@app.route("/submit-update", methods=["GET", "POST"])
def submit_update():
    result = None
    if request.method == "POST":
        text = request.form.get("update_text") or request.form.get("text", "")
        input_type = "manual"
        submitted_by = request.form.get("submitter") or request.form.get("submitted_by", "Manual")
        if text and llm_available:
            from llm import parse_input
            result = parse_input(text, submitted_by)
            add_raw_input(text, input_type=input_type)
    return render_template("submit_update.html", result=result)


@app.route("/api/approve-changes", methods=["POST"])
def approve_changes():
    """Accept proposed changes from the AI and apply them."""
    data = request.get_json()
    changes = data.get("changes", [])
    submitted_by = data.get("submitted_by", "Unknown")
    applied = 0
    for change in changes:
        pid = change.get("project_id")
        field = change.get("field")
        new_val = change.get("new")
        if not pid or not field:
            continue
        try:
            updates = {field: new_val}
            result = update_project(pid, updates, f"Approved by {submitted_by}")
            if result:
                add_history(
                    pid, result,
                    source_text=f"AI-proposed change approved",
                    source_type="manual",
                    updated_by=submitted_by,
                    llm_summary=f"Updated {field}",
                )
                applied += 1
        except Exception:
            pass
    return jsonify({"applied": applied})


@app.route("/api/save-project", methods=["POST"])
def save_project():
    """Save inline edits to a project from the dashboard table."""
    data = request.get_json()
    pid = data.get("project_id")
    updates = data.get("updates", {})
    if not pid or not updates:
        return jsonify({"error": "Missing project_id or updates"}), 400
    try:
        changes = update_project(pid, updates, "Dashboard edit")
        if changes:
            add_history(
                pid, changes,
                source_text="Dashboard inline edit",
                source_type="manual",
                updated_by="Dashboard",
                llm_summary=f"Edited {', '.join(changes.keys())} via Dashboard",
            )
        return jsonify({"ok": True, "changed": list(changes.keys()) if changes else []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ask", methods=["POST"])
def ask_sparrow():
    """Handle Ask SPARROW questions."""
    data = request.get_json(silent=True) or {}
    question = data.get("question", "")
    if not question:
        return jsonify({"answer": "Enter a question first."}), 400
    if not llm_available:
        return jsonify({"answer": "Ask SPARROW is offline. Configure Azure OpenAI in .env."}), 503

    from llm import answer_question

    try:
        answer = answer_question(question)
    except Exception:
        return jsonify({
            "answer": "Ask SPARROW could not reach Azure OpenAI. Check the endpoint and API key in .env."
        }), 502

    add_raw_input(question, input_type="question")
    return jsonify({"answer": answer})


@app.route("/timeline")
def timeline():
    rows = get_timeline_rows()
    projects = get_all_projects()
    today = date.today()

    # Determine the year range for the Gantt display
    year = today.year
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    total_days = (year_end - year_start).days

    def date_to_pct(d_str):
        """Convert a date string to a percentage position within the year."""
        if not d_str:
            return None
        try:
            d = date.fromisoformat(d_str)
        except (ValueError, TypeError):
            return None
        days = (d - year_start).days
        return max(0, min(100, days / total_days * 100))

    # Group rows by project, then build Gantt bars
    dev_projects = {}
    deploy_projects = {}
    for r in rows:
        pid = r["project_id"]
        bucket = dev_projects if r["item_type"] == "dev_track" else deploy_projects
        if pid not in bucket:
            p_data = next((p for p in projects if p["project_id"] == pid), {})
            bucket[pid] = {
                "project_id": pid,
                "label": r.get("track_name") or r.get("location") or pid,
                "sub": r.get("partner_org") or "",
                "country": r.get("country") or "",
                "team_owner": p_data.get("team_owner") or "",
                "target_date": p_data.get("target_date"),
                "status": p_data.get("status", ""),
                "health": p_data.get("health", ""),
                "bars": [],
            }
        start_pct = date_to_pct(r.get("start_date"))
        end_pct = date_to_pct(r.get("end_date"))
        if start_pct is not None and end_pct is not None:
            width = max(2, end_pct - start_pct)
            phase_status = (r.get("phase_status") or "todo").lower()
            bar_class = "active" if phase_status == "doing" else ("complete" if phase_status == "done" else "scoping")
            bucket[pid]["bars"].append({
                "left": round(start_pct, 1),
                "width": round(width, 1),
                "label": r.get("phase_name", ""),
                "bar_class": bar_class,
                "title": f"{r.get('phase_name', '')}: {r.get('phase_status', '')}",
            })

    # Add milestone (target_date) for deploy projects
    for pid, data in deploy_projects.items():
        if data.get("target_date"):
            ms_pct = date_to_pct(data["target_date"])
            if ms_pct is not None:
                data["milestone_pct"] = round(ms_pct, 1)

    # Today line position
    today_pct = round(date_to_pct(today.isoformat()), 1)

    # Current month (1-indexed)
    current_month = today.month

    # Status counts for summary
    status_counts = {}
    for data in deploy_projects.values():
        s = data.get("status", "Unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    return render_template(
        "timeline.html",
        dev_projects=dev_projects,
        deploy_projects=deploy_projects,
        today_pct=today_pct,
        current_month=current_month,
        months=months,
        year=year,
        status_counts=status_counts,
    )


@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.route("/settings")
def settings():
    return render_template("settings.html", team=TEAM_MEMBERS,
                           thresholds=STALENESS_THRESHOLDS)


if __name__ == "__main__":
    app.run(debug=True, port=5001)

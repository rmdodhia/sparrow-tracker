"""
SPARROW Installation Tracker — Streamlit App (v2 Fluent Design)

Run:  streamlit run app.py
"""

import os
import sys
import json
from datetime import datetime, date

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from db import (
    init_db, get_all_projects, get_project, update_project,
    add_history, get_project_history, get_recent_history,
    add_contact, get_contacts, add_raw_input,
    get_active_nudges, get_status_summary,
    get_stale_projects, get_deadline_approaching,
)
from config import (
    VALID_STATUSES, CLOSED_STATUSES, TEAM_MEMBERS,
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT,
    STALENESS_THRESHOLDS, IMAP_HOST,
)
from theme import (
    inject_theme, render_hero, render_floating_ask,
    status_pill_html, severity_badge_html, confidence_badge_html,
    metric_card_html, attention_card_html, activity_item_html,
    timeline_entry_html, COLORS,
)

init_db()

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SPARROW Tracker",
    page_icon="\U0001F426",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

llm_available = bool(AZURE_OPENAI_ENDPOINT)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:4px 0 16px">'
        '<span style="font-size:28px">🐦</span>'
        '<div><div style="font-size:18px;font-weight:700;color:#242424">SPARROW</div>'
        '<div style="font-size:11px;color:#616161">Installation Tracker</div></div></div>',
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Navigate",
        ["Dashboard", "Submit Update", "Project Details", "Sprints", "Reports", "Settings"],
        index=0,
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Ask SPARROW section in sidebar
    st.markdown(
        '<div style="font-size:13px;font-weight:600;color:#242424;margin-bottom:8px">'
        '💬 Ask SPARROW</div>',
        unsafe_allow_html=True,
    )
    quick_queries = [
        "What's blocked or at risk?",
        "Recent changes",
        "FY26 deadlines",
        "Robin dependencies",
    ]
    for q in quick_queries:
        if st.button(q, key=f"sq_{q}", use_container_width=True):
            st.session_state["ask_question"] = q
            st.session_state["ask_pending"] = True

    ask_input = st.text_input(
        "Ask anything...",
        key="ask_sidebar_input",
        label_visibility="collapsed",
        placeholder="Ask about your projects...",
    )
    if ask_input and ask_input != st.session_state.get("_last_ask", ""):
        st.session_state["ask_question"] = ask_input
        st.session_state["ask_pending"] = True
        st.session_state["_last_ask"] = ask_input

    # Process the question
    if st.session_state.get("ask_pending") and llm_available:
        question = st.session_state.get("ask_question", "")
        if question:
            with st.spinner("Thinking..."):
                from llm import answer_question
                answer = answer_question(question)
            st.session_state["ask_answer"] = answer
            st.session_state["ask_pending"] = False
            add_raw_input(question, input_type="question")

    if st.session_state.get("ask_answer"):
        st.markdown(
            f'<div style="background:#eff6fc;border:1px solid #c7e0f4;border-radius:8px;'
            f'padding:12px;font-size:13px;max-height:300px;overflow-y:auto">'
            f'{st.session_state["ask_answer"]}</div>',
            unsafe_allow_html=True,
        )
        if st.button("Clear", key="clear_ask"):
            st.session_state["ask_answer"] = None
            st.session_state["ask_question"] = ""
            st.rerun()

    if not llm_available:
        st.caption("⚠️ LLM not configured")

    st.markdown("---")
    all_projects_count = len(get_all_projects())
    st.caption(f"{all_projects_count} Projects · {date.today().strftime('%B %d, %Y')}")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if page == "Dashboard":

    # ── Header ────────────────────────────────────────────────────────────
    header_cols = st.columns([8, 2])
    with header_cols[0]:
        st.markdown("## Dashboard")
    with header_cols[1]:
        st.link_button("Submit Update →", "#", type="primary", use_container_width=True)

    # ── Hero Banner ───────────────────────────────────────────────────────
    projects = get_all_projects()
    continents = len(set(p["continent"] for p in projects))
    countries = len(set(p["country"] for p in projects))
    active = sum(1 for p in projects if p["status"] == "Active")
    render_hero(len(projects), continents, countries, active)

    # ── Alert Ribbon ──────────────────────────────────────────────────────
    stale = get_stale_projects()
    deadline = get_deadline_approaching()
    attention_items = stale + [d for d in deadline if d["project_id"] not in {s["project_id"] for s in stale}]
    overdue = [d for d in deadline if d.get("days_until_deadline", 1) <= 0]

    if overdue:
        names = ", ".join(d["location"][:25] for d in overdue[:3])
        extra = f" and {len(overdue) - 3} more" if len(overdue) > 3 else ""
        st.markdown(
            f'<div class="alert-ribbon">'
            f'<div class="pulse-dot"></div>'
            f'<div><strong style="color:#d13438">{len(overdue)} project(s) overdue</strong> — '
            f'{names}{extra} need attention.</div></div>',
            unsafe_allow_html=True,
        )

    # ── Stat Cards ────────────────────────────────────────────────────────
    summary = get_status_summary()
    sorted_statuses = sorted(summary.items(), key=lambda x: -x[1])

    bar_color_map = {
        "Scoping": COLORS["neutral"],
        "Active - Waiting on Partner": COLORS["warning"],
        "Active - Waiting on Us": COLORS["primary"],
        "Complete": COLORS["success"],
        "Descoped": COLORS["neutral"],
    }

    ncols = len(sorted_statuses)
    stat_html = f'<div style="display:grid;grid-template-columns:repeat({ncols},1fr);gap:16px;margin-bottom:28px">'
    for status, count in sorted_statuses:
        bar = bar_color_map.get(status, COLORS["neutral"])
        stat_html += (
            f'<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
            f'padding:20px 20px 0;position:relative;overflow:hidden;'
            f'transition:all 0.15s ease">'
            f'<div style="font-size:32px;font-weight:700;letter-spacing:-1px;color:#242424">{count}</div>'
            f'<div style="font-size:13px;color:#616161;margin-top:4px;margin-bottom:16px;font-weight:500">{status}</div>'
            f'<div style="height:3px;margin:0 -20px;background:{bar}"></div>'
            f'</div>'
        )
    stat_html += '</div>'
    st.markdown(stat_html, unsafe_allow_html=True)

    # ── Two-Column: Attention + Activity ──────────────────────────────────
    left_col, right_col = st.columns([2, 1])

    with left_col:
        # Needs Attention
        if attention_items:
            st.markdown(
                f'<div class="section-title">Needs Attention '
                f'<span class="badge-count">{len(attention_items)}</span></div>',
                unsafe_allow_html=True,
            )
            for item in attention_items[:6]:
                if "days_since_update" in item:
                    detail = f"{item['days_since_update']} days since last update. {item.get('blocker') or ''}"
                    sev = "danger" if item["days_since_update"] > 30 else "warning"
                else:
                    d = item.get("days_until_deadline", 0)
                    detail = f"{'OVERDUE' if d < 0 else f'{d} days to deadline'}. {item.get('blocker') or ''}"
                    sev = "danger" if d <= 0 else ("warning" if d <= 14 else "info")
                st.markdown(
                    attention_card_html(item["location"], item["status"], detail.strip(), sev),
                    unsafe_allow_html=True,
                )

        # Project Table
        st.markdown('<div class="section-title" style="margin-top:20px">All Projects</div>',
                    unsafe_allow_html=True)

        default_status = []
        filter_cols = st.columns(4)
        with filter_cols[0]:
            status_filter = st.multiselect("Status", VALID_STATUSES, default=default_status)
        with filter_cols[1]:
            continent_list = sorted(set(p["continent"] for p in projects))
            continent_filter = st.multiselect("Continent", continent_list, default=[])
        with filter_cols[2]:
            owners = sorted(set(p.get("team_owner") or "Unassigned" for p in projects))
            owner_filter = st.multiselect("Owner", owners, default=[])
        with filter_cols[3]:
            search = st.text_input("Search", "", label_visibility="visible")

        filtered = projects
        if status_filter:
            filtered = [p for p in filtered if p["status"] in status_filter]
        if continent_filter:
            filtered = [p for p in filtered if p["continent"] in continent_filter]
        if owner_filter:
            filtered = [p for p in filtered if (p.get("team_owner") or "Unassigned") in owner_filter]
        if search:
            sl = search.lower()
            filtered = [p for p in filtered if sl in json.dumps(p).lower()]

        df = pd.DataFrame(filtered)
        display_cols = [
            "project_id", "location", "partner_org",
            "status", "team_owner", "target_date",
            "estimated_cost", "last_updated",
        ]
        display_cols = [c for c in display_cols if c in df.columns]
        if not df.empty:
            st.dataframe(
                df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "project_id": st.column_config.TextColumn("ID", width="small"),
                    "location": st.column_config.TextColumn("Location"),
                    "partner_org": st.column_config.TextColumn("Partner"),
                    "status": st.column_config.TextColumn("Status"),
                    "team_owner": st.column_config.TextColumn("Owner"),
                    "estimated_cost": st.column_config.NumberColumn("Cost (USD)", format="$%.0f"),
                    "target_date": st.column_config.TextColumn("Target Date"),
                    "last_updated": st.column_config.TextColumn("Last Updated"),
                },
            )
        else:
            st.info("No projects match the current filters.")

    with right_col:
        # Activity Feed
        st.markdown(
            '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;overflow:hidden">'
            '<div style="padding:14px 16px;border-bottom:1px solid #edebe9;font-size:14px;font-weight:600">'
            'Recent Activity</div><div style="padding:0 16px;max-height:500px;overflow-y:auto">',
            unsafe_allow_html=True,
        )
        history = get_recent_history(days=30, limit=15)
        if history:
            feed_html = ""
            for h in history:
                ts = h.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts)
                    diff = datetime.utcnow() - dt
                    if diff.days > 0:
                        ago = f"{diff.days}d ago"
                    elif diff.seconds > 3600:
                        ago = f"{diff.seconds // 3600}h ago"
                    else:
                        ago = f"{diff.seconds // 60}m ago"
                except (ValueError, TypeError):
                    ago = ts
                who = h.get("updated_by") or "System"
                pid = h.get("project_id", "")
                summary_text = h.get("llm_summary", "Update")
                source = h.get("source_type", "manual")
                feed_html += activity_item_html(
                    ago,
                    f"<strong>{who}</strong> updated <strong>{pid}</strong> — {summary_text[:80]}",
                    source,
                )
            st.markdown(feed_html + '</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="padding:16px;color:#8a8886;font-size:13px">No recent activity</div>'
                '</div></div>',
                unsafe_allow_html=True,
            )

        # Active Nudges
        nudges = get_active_nudges()
        if nudges:
            with st.expander(f"Active Nudges ({len(nudges)})"):
                for n in nudges:
                    st.markdown(
                        f"{severity_badge_html(n['severity'])} **{n['project_id']}** — {n['message'][:150]}",
                        unsafe_allow_html=True,
                    )


# ══════════════════════════════════════════════════════════════════════════════
# SUBMIT UPDATE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Submit Update":
    st.markdown("## Submit Update")
    st.markdown(
        "Paste an email, Teams message, meeting notes, or plain English. "
        "The AI will identify projects and propose changes."
    )

    input_col, context_col = st.columns([3, 2])

    with input_col:
        text = st.text_area(
            "Paste your update here", height=280,
            placeholder="e.g., 'Paulo confirmed Salonga shipment arrived in Kinshasa yesterday. "
            "Still waiting on customs clearance.'\n\nPaste emails, Teams messages, meeting notes, "
            "or plain English — the AI will figure out the rest.",
        )

        if st.button("⚡ Process with AI", type="primary", disabled=not llm_available or not text.strip(),
                      use_container_width=True):
            with st.spinner("Analyzing..."):
                from llm import parse_input
                result = parse_input(text, "auto")
            st.session_state["pending_result"] = result
            st.session_state["pending_text"] = text
            st.session_state["pending_type"] = "update"
            st.session_state["pending_by"] = "System"

        # ── Results ───────────────────────────────────────────────────────
        if "pending_result" in st.session_state:
            result = st.session_state["pending_result"]

            if result.get("input_type") == "question":
                st.info("This looks like a question:")
                st.markdown(result.get("question_answer") or result.get("llm_summary", ""))
                if st.button("Clear"):
                    del st.session_state["pending_result"]
                    st.rerun()

            elif result.get("input_type") == "unclear":
                st.warning("Could not clearly identify which project this relates to.")
                st.json(result)
                if st.button("Clear"):
                    del st.session_state["pending_result"]
                    st.rerun()

            else:
                # Summary banner
                matches = result.get("matched_projects", [])
                all_high = all(m.get("match_confidence") == "high" for m in matches)
                banner_color = "#dff6dd" if all_high else "#fff4ce"
                banner_icon = "✓" if all_high else "?"
                st.markdown(
                    f'<div style="background:{banner_color};border-radius:8px;padding:12px 16px;'
                    f'margin:12px 0;font-size:14px">'
                    f'{banner_icon} Matched {len(matches)} project(s) '
                    f'{"with high confidence" if all_high else "— review confidence below"}</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(f"*{result.get('llm_summary', '')}*")

                # Matched projects
                for match in matches:
                    conf = match.get("match_confidence", "?")
                    st.markdown(
                        f"**{match['project_id']}** — {confidence_badge_html(conf)} — "
                        f"{match.get('match_reason', '')}",
                        unsafe_allow_html=True,
                    )

                # Proposed changes
                changes = result.get("proposed_changes", [])
                if changes:
                    st.markdown("**Proposed Changes:**")
                    change_df = pd.DataFrame(changes)
                    st.dataframe(change_df, use_container_width=True, hide_index=True)

                # New contacts
                contacts = result.get("new_contacts", [])
                if contacts:
                    st.markdown("**New Contacts Detected:**")
                    st.dataframe(pd.DataFrame(contacts), use_container_width=True, hide_index=True)

                # Action buttons
                act_cols = st.columns([2, 2, 1])
                with act_cols[0]:
                    if st.button("Approve All", type="primary", use_container_width=True):
                        history_ids = []
                        for change in changes:
                            pid = change["project_id"]
                            field_changes = update_project(
                                pid, {change["field"]: change["new_value"]},
                                st.session_state["pending_by"],
                            )
                            if field_changes:
                                hid = add_history(
                                    pid, field_changes,
                                    source_text=st.session_state["pending_text"],
                                    source_type=st.session_state["pending_type"],
                                    updated_by=st.session_state["pending_by"],
                                    llm_summary=result.get("llm_summary"),
                                )
                                history_ids.append(hid)

                        for c in contacts:
                            add_contact(
                                name=c.get("name", ""),
                                organization=c.get("organization"),
                                role=c.get("role"),
                                email=c.get("email"),
                                phone=c.get("phone"),
                                linked_projects=[c.get("linked_project")] if c.get("linked_project") else [],
                            )

                        add_raw_input(
                            st.session_state["pending_text"],
                            submitted_by=st.session_state["pending_by"],
                            input_type="update",
                            history_ids=history_ids,
                        )
                        st.success(f"Applied {len(changes)} change(s).")
                        del st.session_state["pending_result"]
                        st.rerun()

                with act_cols[2]:
                    if st.button("Reject", use_container_width=True):
                        add_raw_input(
                            st.session_state["pending_text"],
                            submitted_by=st.session_state["pending_by"],
                            input_type="update",
                            history_ids=[],
                        )
                        del st.session_state["pending_result"]
                        st.rerun()

    with context_col:
        # Recently Updated feed
        st.markdown(
            '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;overflow:hidden">'
            '<div style="padding:14px 16px;border-bottom:1px solid #edebe9;font-size:14px;font-weight:600">'
            'Recently Updated</div><div style="padding:8px 16px">',
            unsafe_allow_html=True,
        )
        recent = get_recent_history(days=14, limit=5)
        if recent:
            items_html = ""
            for h in recent:
                pid = h.get("project_id", "")
                summary_text = h.get("llm_summary", "Update")[:60]
                ts = h.get("timestamp", "")[:10]
                items_html += (
                    f'<div style="padding:8px 0;border-bottom:1px solid #f3f2f1;font-size:13px">'
                    f'<span style="display:inline-block;padding:1px 6px;background:#eff6fc;'
                    f'border-radius:4px;font-size:11px;color:#0078d4;font-weight:600;margin-right:6px">'
                    f'{pid}</span>{summary_text}'
                    f'<div style="font-size:11px;color:#8a8886;margin-top:2px">{ts}</div></div>'
                )
            st.markdown(items_html + '</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="padding:16px;color:#8a8886;font-size:13px">No recent updates</div>'
                '</div></div>',
                unsafe_allow_html=True,
            )

        # Quick tip
        st.markdown(
            '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
            'padding:16px;margin-top:12px">'
            '<div style="font-size:14px;font-weight:600;margin-bottom:8px">💡 Quick Tip</div>'
            '<div style="font-size:13px;color:#616161">You can forward emails to your configured '
            'SPARROW inbox and they\'ll be processed automatically. '
            'Configure this in Settings → Email Ingestion.</div></div>',
            unsafe_allow_html=True,
        )

    # Manual update fallback
    with st.expander("Manual update (without AI)"):
        projects = get_all_projects()
        project_options = {f"{p['project_id']} — {p['location']} ({p['partner_org']})": p["project_id"] for p in projects}
        selected = st.selectbox("Select project", list(project_options.keys()), key="manual_proj")
        if selected:
            pid = project_options[selected]
            current = get_project(pid)

            manual_cols = st.columns(2)
            with manual_cols[0]:
                new_status = st.selectbox("Status", VALID_STATUSES, index=VALID_STATUSES.index(current["status"]))
                new_blocker = st.text_input("Blocker / Risk", current.get("blocker") or "")
                new_owner = st.selectbox(
                    "Team Owner", [""] + TEAM_MEMBERS,
                    index=(TEAM_MEMBERS.index(current["team_owner"]) + 1) if current.get("team_owner") in TEAM_MEMBERS else 0,
                )
            with manual_cols[1]:
                new_timeline = st.text_input("Timeline label", current.get("timeline_label") or "")
                new_target = st.text_input("Target date (YYYY-MM-DD)", current.get("target_date") or "")
                new_notes = st.text_area("Notes", current.get("notes") or "", height=100)

            manual_note = st.text_area("Change reason / source", height=80, placeholder="Why is this changing?")
            manual_by = st.selectbox("Updated by", TEAM_MEMBERS + ["Other"], key="manual_by")

            if st.button("Save Manual Update"):
                updates = {}
                if new_status != current["status"]:
                    updates["status"] = new_status
                if new_blocker != (current.get("blocker") or ""):
                    updates["blocker"] = new_blocker or None
                if new_owner != (current.get("team_owner") or ""):
                    updates["team_owner"] = new_owner or None
                if new_timeline != (current.get("timeline_label") or ""):
                    updates["timeline_label"] = new_timeline or None
                if new_target != (current.get("target_date") or ""):
                    updates["target_date"] = new_target or None
                if new_notes != (current.get("notes") or ""):
                    updates["notes"] = new_notes or None

                if updates:
                    field_changes = update_project(pid, updates, manual_by)
                    if field_changes:
                        add_history(
                            pid, field_changes,
                            source_text=manual_note or "Manual update via UI",
                            source_type="manual_note",
                            updated_by=manual_by,
                            llm_summary=f"Manual update: {', '.join(field_changes.keys())} changed",
                        )
                    st.success(f"Updated {len(updates)} field(s) for {pid}.")
                    st.rerun()
                else:
                    st.info("No changes detected.")


# ══════════════════════════════════════════════════════════════════════════════
# PROJECT DETAILS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Project Details":
    st.markdown("## Project Details")

    projects = get_all_projects()
    project_options = {f"{p['project_id']} — {p['location']} ({p['partner_org']})": p["project_id"] for p in projects}
    selected = st.selectbox("Select a project", list(project_options.keys()))

    if selected:
        pid = project_options[selected]
        p = get_project(pid)

        # ── Breadcrumb ────────────────────────────────────────────────────
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:6px;font-size:12.5px;color:#616161;margin-bottom:20px">'
            f'<span style="color:#0078d4">Dashboard</span>'
            f'<span style="color:#c8c6c4">/</span>'
            f'<span style="color:#0078d4">Projects</span>'
            f'<span style="color:#c8c6c4">/</span>'
            f'<span>{p["project_id"]}</span></div>',
            unsafe_allow_html=True,
        )

        # ── Header Card with Metrics ─────────────────────────────────────
        target = p.get("target_date") or "TBD"
        target_sub = ""
        if p.get("target_date"):
            try:
                days_left = (date.fromisoformat(p["target_date"]) - date.today()).days
                target_sub = f"{days_left} days left" if days_left >= 0 else f"OVERDUE by {-days_left}d"
            except ValueError:
                pass
        cost = p.get("estimated_cost")
        cost_str = f"${cost:,.0f}" if cost else "TBD"
        last_updated = (p.get("last_updated") or "unknown")[:10]
        last_by = p.get("last_updated_by") or "unknown"
        owner = p.get("team_owner") or "Unassigned"
        target_sub_color = "#107c10" if "left" in target_sub else "#d13438" if "OVERDUE" in target_sub else "#616161"

        st.markdown(
            f'<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;padding:24px 28px;margin-bottom:20px">'
            # Top: ID, Name, Status
            f'<div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px">'
            f'<div>'
            f'<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">'
            f'<span style="font-family:Cascadia Code,Consolas,monospace;font-size:13px;color:#0078d4;'
            f'background:#eff6fc;padding:3px 10px;border-radius:4px;font-weight:600;letter-spacing:0.5px">'
            f'{p["project_id"]}</span>'
            f'<span style="font-size:26px;font-weight:700;color:#242424;letter-spacing:-0.5px">'
            f'{p["location"]}, {p["country"]}</span>'
            f'{status_pill_html(p["status"])}'
            f'</div>'
            f'<div style="font-size:13.5px;color:#616161;margin-top:6px">'
            f'{p["partner_org"]} &middot; {p["country"]} &middot; {p["continent"]}</div>'
            f'</div></div>'
            # Metrics row
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin-top:20px;'
            f'border-top:1px solid #edebe9;padding-top:20px">'
            # Owner
            f'<div style="padding:0 20px 0 0;border-right:1px solid #edebe9">'
            f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.5px;'
            f'font-weight:600;margin-bottom:6px">Owner</div>'
            f'<div style="font-size:18px;font-weight:700;color:#242424;display:flex;align-items:center;gap:8px">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:#0078d4"></span>{owner}</div>'
            f'<div style="font-size:12px;color:#616161;margin-top:3px">Project lead</div></div>'
            # Target Date
            f'<div style="padding:0 20px;border-right:1px solid #edebe9">'
            f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.5px;'
            f'font-weight:600;margin-bottom:6px">Target Date</div>'
            f'<div style="font-size:18px;font-weight:700;color:#242424">{target}</div>'
            f'<div style="font-size:12px;color:{target_sub_color};margin-top:3px;font-weight:500">{target_sub}</div></div>'
            # Cost
            f'<div style="padding:0 20px;border-right:1px solid #edebe9">'
            f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.5px;'
            f'font-weight:600;margin-bottom:6px">Estimated Cost</div>'
            f'<div style="font-size:18px;font-weight:700;color:#242424">{cost_str}</div>'
            f'<div style="font-size:12px;color:#616161;margin-top:3px">USD</div></div>'
            # Last Updated
            f'<div style="padding:0 0 0 20px">'
            f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.5px;'
            f'font-weight:600;margin-bottom:6px">Last Updated</div>'
            f'<div style="font-size:18px;font-weight:700;color:#242424">{last_updated}</div>'
            f'<div style="font-size:12px;color:#616161;margin-top:3px">by {last_by}</div></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        # ── Two Column: Info + History / Contacts + Actions ───────────────
        left_col, right_col = st.columns([2, 1])

        with left_col:
            # Project Information (grid layout matching mockup)
            blocker = p.get("blocker") or "None"
            blocker_style = "color:#d13438;font-weight:500" if blocker != "None" else "color:#242424;font-weight:500"
            devops_html = ""
            if p.get("devops_id"):
                devops_html = (
                    f'<div style="grid-column:1/-1;padding:14px 0 14px 0">'
                    f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.4px;'
                    f'font-weight:600;margin-bottom:5px">DevOps ID</div>'
                    f'<div style="font-size:13.5px;color:#242424;font-weight:500">'
                    f'<code style="font-family:Cascadia Code,Consolas,monospace;background:#f5f5f5;'
                    f'padding:1px 6px;border-radius:3px;font-size:12.5px">{p["devops_id"]}</code></div></div>'
                )
            st.markdown(
                f'<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;padding:24px;margin-bottom:20px">'
                f'<div style="font-size:15px;font-weight:600;color:#242424;margin-bottom:16px">Project Information</div>'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0">'
                # Row 1: Deployment Type | Hardware
                f'<div style="padding:14px 20px 14px 0;border-bottom:1px solid #f3f2f1">'
                f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.4px;'
                f'font-weight:600;margin-bottom:5px">Deployment Type</div>'
                f'<div style="font-size:13.5px;color:#242424;font-weight:500">{p.get("deployment_type") or "TBD"}</div></div>'
                f'<div style="padding:14px 0 14px 20px;border-bottom:1px solid #f3f2f1;border-left:1px solid #f3f2f1">'
                f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.4px;'
                f'font-weight:600;margin-bottom:5px">Hardware</div>'
                f'<div style="font-size:13.5px;color:#242424;font-weight:500">{p.get("hardware") or "TBD"}</div></div>'
                # Row 2: Timeline | Confidence
                f'<div style="padding:14px 20px 14px 0;border-bottom:1px solid #f3f2f1">'
                f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.4px;'
                f'font-weight:600;margin-bottom:5px">Timeline</div>'
                f'<div style="font-size:13.5px;color:#242424;font-weight:500">{p.get("timeline_label") or "TBD"}</div></div>'
                f'<div style="padding:14px 0 14px 20px;border-bottom:1px solid #f3f2f1;border-left:1px solid #f3f2f1">'
                f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.4px;'
                f'font-weight:600;margin-bottom:5px">Confidence</div>'
                f'<div style="font-size:13.5px;color:#242424;font-weight:500">{p.get("target_confidence") or "N/A"}</div></div>'
                # Full-width: Blocker
                f'<div style="grid-column:1/-1;padding:14px 0;border-bottom:1px solid #f3f2f1">'
                f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.4px;'
                f'font-weight:600;margin-bottom:5px">Blocker</div>'
                f'<div style="font-size:13.5px;{blocker_style}">{blocker}</div></div>'
                # Full-width: Notes
                f'<div style="grid-column:1/-1;padding:14px 0;border-bottom:{"1px solid #f3f2f1" if p.get("devops_id") else "none"}">'
                f'<div style="font-size:11.5px;color:#616161;text-transform:uppercase;letter-spacing:0.4px;'
                f'font-weight:600;margin-bottom:5px">Notes</div>'
                f'<div style="font-size:13.5px;color:#424242;font-style:italic;font-weight:400;line-height:1.6">'
                f'{p.get("notes") or "None"}</div></div>'
                f'{devops_html}'
                f'</div></div>',
                unsafe_allow_html=True,
            )

            # ── History Timeline ───────────────────────────────────────────
            history = get_project_history(pid)

            # History header with filter
            hist_h_cols = st.columns([3, 2])
            with hist_h_cols[0]:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">'
                    f'<span style="font-size:17px;font-weight:700;color:#242424;letter-spacing:-0.2px">History</span>'
                    f'<span style="font-size:12px;color:#616161">({len(history) if history else 0} entries)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with hist_h_cols[1]:
                source_filter = st.selectbox(
                    "Filter",
                    ["All", "Email", "Manual", "System", "Teams"],
                    key="history_filter",
                    label_visibility="collapsed",
                )

            if history:
                filtered_history = history
                if source_filter != "All":
                    filter_map = {"Email": "email", "Manual": "manual_note", "System": "system", "Teams": "teams_paste"}
                    filtered_history = [h for h in history if h.get("source_type") == filter_map.get(source_filter, "")]

                # Build timeline in a single HTML block for the vertical line effect
                timeline_html = '<div class="sparrow-timeline">'
                for i, h in enumerate(filtered_history[:20]):
                    expanded = i < 3
                    timeline_html += timeline_entry_html(
                        timestamp=h.get("timestamp", ""),
                        source_type=h.get("source_type", "manual"),
                        author=h.get("updated_by", "unknown"),
                        summary=h.get("llm_summary", "Update"),
                        changes=h.get("changes") if expanded else None,
                        source_text=h.get("source_text") if expanded else None,
                        expanded=expanded,
                    )
                timeline_html += '</div>'
                st.markdown(timeline_html, unsafe_allow_html=True)

                if len(filtered_history) > 20:
                    st.caption(f"Showing 20 of {len(filtered_history)} entries")
            else:
                st.info("No history yet.")

        with right_col:
            # Contacts
            project_contacts = get_contacts(pid)
            st.markdown(
                '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
                'padding:16px;margin-bottom:12px">'
                '<div style="font-size:14px;font-weight:600;margin-bottom:10px">Contacts</div>',
                unsafe_allow_html=True,
            )
            if project_contacts:
                for c in project_contacts:
                    st.markdown(
                        f'<div style="padding:6px 0;border-bottom:1px solid #f3f2f1;font-size:13px">'
                        f'<strong>{c.get("name", "")}</strong>'
                        f'<div style="color:#616161">{c.get("organization", "")} · {c.get("role", "")}</div>'
                        f'{"<div style=color:#0078d4>" + c["email"] + "</div>" if c.get("email") else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown('<div style="color:#8a8886;font-size:13px">No contacts yet</div>',
                            unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            # Active Alerts
            project_nudges = get_active_nudges(pid)
            if project_nudges:
                st.markdown(
                    '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
                    'padding:16px;margin-bottom:12px">'
                    '<div style="font-size:14px;font-weight:600;margin-bottom:10px">Active Alerts</div>',
                    unsafe_allow_html=True,
                )
                for n in project_nudges:
                    sev_color = {"info": COLORS["primary"], "warning": COLORS["warning"],
                                 "escalation": COLORS["danger"]}.get(n["severity"], COLORS["neutral"])
                    st.markdown(
                        f'<div style="border-left:3px solid {sev_color};padding:8px 12px;margin-bottom:8px;'
                        f'font-size:13px">{severity_badge_html(n["severity"])} {n["message"][:150]}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown('</div>', unsafe_allow_html=True)

            # Quick Actions
            st.markdown(
                '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
                'padding:16px">'
                '<div style="font-size:14px;font-weight:600;margin-bottom:10px">Quick Actions</div>',
                unsafe_allow_html=True,
            )
            st.button("Submit update for this project", use_container_width=True, key="quick_update")
            st.markdown(
                f'<div style="padding:6px 0;font-size:13px;color:#0078d4;cursor:pointer">'
                f'Export history</div></div>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# SPRINTS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Sprints":
    from devops_sync import (
        sync_all, get_iterations, get_work_items, get_work_items_by_sprint,
        get_work_items_by_person, get_last_sync_time,
    )
    from config import AZURE_DEVOPS_PAT, AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT

    st.markdown("## Sprints & Roadmap")

    devops_configured = bool(AZURE_DEVOPS_PAT)

    # ── Sync Controls ────────────────────────────────────────────────────
    sync_cols = st.columns([4, 1, 1])
    with sync_cols[0]:
        last_sync = get_last_sync_time()
        if last_sync:
            st.markdown(
                f'<div style="font-size:13px;color:#616161;padding-top:8px">'
                f'Last synced: <strong>{last_sync}</strong> · '
                f'{AZURE_DEVOPS_ORG}/{AZURE_DEVOPS_PROJECT}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-size:13px;color:#8a8886;padding-top:8px">'
                'Not synced yet — click Sync to pull from Azure DevOps</div>',
                unsafe_allow_html=True,
            )
    with sync_cols[2]:
        if st.button("🔄 Sync", type="primary", disabled=not devops_configured,
                      use_container_width=True):
            with st.spinner("Syncing from Azure DevOps..."):
                try:
                    result = sync_all()
                    st.success(f"Synced {result['iterations']} sprints, {result['work_items']} work items")
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")

    if not devops_configured:
        st.warning("Azure DevOps PAT not configured. Add `AZURE_DEVOPS_PAT` to your `.env` file.")

    # ── View Tabs ────────────────────────────────────────────────────────
    tab_board, tab_person, tab_timeline = st.tabs(["Sprint Board", "By Person", "Timeline"])

    # ── Sprint Board ─────────────────────────────────────────────────────
    with tab_board:
        sprints_data = get_work_items_by_sprint()
        iterations = get_iterations()
        iter_map = {it["path"]: it for it in iterations}

        if not sprints_data:
            st.info("No work items found. Sync from Azure DevOps to populate.")
        else:
            # State color map
            state_colors = {
                "Done": COLORS["success"], "Closed": COLORS["success"],
                "Active": COLORS["primary"], "In Progress": COLORS["primary"],
                "New": COLORS["neutral"], "To Do": COLORS["neutral"],
                "Resolved": "#5c2d91",
            }
            type_icons = {
                "User Story": "📖", "Task": "✅", "Bug": "🐛",
                "Feature": "⭐", "Epic": "🏔️", "Issue": "⚠️",
            }

            for sprint_path in sorted(sprints_data.keys(), reverse=True):
                items = sprints_data[sprint_path]
                sprint_name = sprint_path.split("\\")[-1] if "\\" in sprint_path else sprint_path
                iter_info = iter_map.get(sprint_path, {})
                date_range = ""
                if iter_info.get("start_date") and iter_info.get("end_date"):
                    start = iter_info["start_date"][:10]
                    end = iter_info["end_date"][:10]
                    date_range = f" · {start} → {end}"

                done_count = sum(1 for i in items if i.get("state") in ("Done", "Closed"))
                total = len(items)
                pct = int(done_count / total * 100) if total else 0

                st.markdown(
                    f'<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
                    f'padding:18px 22px;margin-bottom:16px">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;'
                    f'flex-wrap:wrap;gap:8px;margin-bottom:14px">'
                    f'<div>'
                    f'<span style="font-size:16px;font-weight:700;color:#242424">{sprint_name}</span>'
                    f'<span style="font-size:12px;color:#616161;margin-left:8px">{date_range}</span>'
                    f'</div>'
                    f'<div style="display:flex;align-items:center;gap:12px">'
                    f'<span style="font-size:12px;color:#616161">{done_count}/{total} done</span>'
                    f'<div style="width:120px;height:6px;background:#f3f2f1;border-radius:3px;overflow:hidden">'
                    f'<div style="width:{pct}%;height:100%;background:{COLORS["success"]};'
                    f'border-radius:3px;transition:width 0.3s"></div></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

                # Work items table
                items_html = ""
                for wi in sorted(items, key=lambda x: (x.get("state", ""), x.get("title", ""))):
                    sc = state_colors.get(wi.get("state", ""), COLORS["neutral"])
                    icon = type_icons.get(wi.get("work_item_type", ""), "📋")
                    person = wi.get("assigned_to") or "Unassigned"
                    person_short = person.split(" ")[0] if person != "Unassigned" else person
                    tags = wi.get("tags") or ""
                    tags_html = ""
                    if tags:
                        for tag in tags.split(";")[:3]:
                            tag = tag.strip()
                            if tag:
                                tags_html += (
                                    f'<span style="display:inline-block;padding:1px 6px;'
                                    f'background:#f3f2f1;border-radius:3px;font-size:10px;'
                                    f'color:#616161;margin-left:4px">{tag}</span>'
                                )
                    wi_url = wi.get("url", "#")
                    items_html += (
                        f'<div style="display:flex;align-items:center;gap:10px;'
                        f'padding:8px 0;border-bottom:1px solid #f3f2f1;font-size:13px">'
                        f'<span style="width:8px;height:8px;border-radius:50%;background:{sc};flex-shrink:0"></span>'
                        f'<span>{icon}</span>'
                        f'<span style="flex:1;font-weight:500;color:#242424">{wi["title"]}</span>'
                        f'{tags_html}'
                        f'<span style="font-size:12px;color:#616161;min-width:80px;text-align:right">{person_short}</span>'
                        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
                        f'font-size:11px;font-weight:600;background:{sc}18;color:{sc}">{wi.get("state", "?")}</span>'
                        f'</div>'
                    )
                st.markdown(items_html + '</div>', unsafe_allow_html=True)

    # ── By Person ────────────────────────────────────────────────────────
    with tab_person:
        person_data = get_work_items_by_person()
        if not person_data:
            st.info("No work items found.")
        else:
            for person in sorted(person_data.keys()):
                items = person_data[person]
                active = sum(1 for i in items if i.get("state") not in ("Done", "Closed", "Removed"))
                done = sum(1 for i in items if i.get("state") in ("Done", "Closed"))

                st.markdown(
                    f'<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
                    f'padding:16px 20px;margin-bottom:12px">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
                    f'<div style="display:flex;align-items:center;gap:10px">'
                    f'<div style="width:32px;height:32px;border-radius:50%;background:#0078d4;'
                    f'display:flex;align-items:center;justify-content:center;color:#fff;'
                    f'font-size:14px;font-weight:600">{person[0].upper() if person else "?"}</div>'
                    f'<span style="font-size:15px;font-weight:600;color:#242424">{person}</span>'
                    f'</div>'
                    f'<div style="font-size:12px;color:#616161">'
                    f'{active} active · {done} done</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for wi in items:
                    sc = state_colors.get(wi.get("state", ""), COLORS["neutral"])
                    sprint = (wi.get("iteration_path") or "").split("\\")[-1] if wi.get("iteration_path") else ""
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:8px;'
                        f'padding:6px 0;border-bottom:1px solid #f3f2f1;font-size:13px">'
                        f'<span style="width:6px;height:6px;border-radius:50%;background:{sc};flex-shrink:0"></span>'
                        f'<span style="flex:1;color:#242424">{wi["title"]}</span>'
                        f'<span style="font-size:11px;color:#8a8886">{sprint}</span>'
                        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
                        f'font-size:11px;font-weight:600;background:{sc}18;color:{sc}">{wi.get("state", "?")}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown('</div>', unsafe_allow_html=True)

    # ── Timeline ─────────────────────────────────────────────────────────
    with tab_timeline:
        iterations = get_iterations()
        all_work_items = get_work_items()

        if not iterations:
            st.info("No sprint data. Sync from Azure DevOps to see the timeline.")
        else:
            # Filter controls
            tl_filter_cols = st.columns(3)
            with tl_filter_cols[0]:
                area_paths = sorted(set(wi.get("area_path", "") for wi in all_work_items if wi.get("area_path")))
                area_filter = st.multiselect("Area", area_paths, default=[], key="tl_area")
            with tl_filter_cols[1]:
                people = sorted(set(wi.get("assigned_to", "") for wi in all_work_items if wi.get("assigned_to")))
                person_filter = st.multiselect("Person", people, default=[], key="tl_person")
            with tl_filter_cols[2]:
                wi_types = sorted(set(wi.get("work_item_type", "") for wi in all_work_items if wi.get("work_item_type")))
                type_filter = st.multiselect("Type", wi_types, default=[], key="tl_type")

            # Build Gantt-style timeline using iteration date ranges
            today = date.today()
            gantt_html = '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;padding:24px;overflow-x:auto">'
            gantt_html += '<div style="font-size:15px;font-weight:600;color:#242424;margin-bottom:16px">Sprint Timeline</div>'

            # Only show iterations with dates
            dated_iters = [it for it in iterations if it.get("start_date") and it.get("end_date")]
            dated_iters.sort(key=lambda x: x["start_date"])

            if dated_iters:
                for it in dated_iters:
                    start_str = it["start_date"][:10]
                    end_str = it["end_date"][:10]
                    sprint_name = it["name"]
                    try:
                        start_d = date.fromisoformat(start_str)
                        end_d = date.fromisoformat(end_str)
                        is_current = start_d <= today <= end_d
                        is_past = end_d < today
                    except ValueError:
                        is_current = False
                        is_past = False

                    # Count items in this sprint
                    sprint_items = [wi for wi in all_work_items
                                    if wi.get("iteration_path", "").endswith(sprint_name)]
                    if area_filter:
                        sprint_items = [wi for wi in sprint_items if wi.get("area_path") in area_filter]
                    if person_filter:
                        sprint_items = [wi for wi in sprint_items if wi.get("assigned_to") in person_filter]
                    if type_filter:
                        sprint_items = [wi for wi in sprint_items if wi.get("work_item_type") in type_filter]

                    done = sum(1 for wi in sprint_items if wi.get("state") in ("Done", "Closed"))
                    total = len(sprint_items)
                    pct = int(done / total * 100) if total else 0

                    border_color = COLORS["primary"] if is_current else (COLORS["border"] if not is_past else "#e1dfdd")
                    bg = COLORS["primary_light"] if is_current else ("#faf9f8" if is_past else "#fff")
                    bar_color = COLORS["success"] if pct == 100 else (COLORS["primary"] if is_current else COLORS["neutral"])
                    badge = ""
                    if is_current:
                        badge = (
                            f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
                            f'font-size:10px;font-weight:700;background:{COLORS["primary"]};'
                            f'color:#fff;margin-left:8px">CURRENT</span>'
                        )

                    gantt_html += (
                        f'<div style="display:flex;align-items:center;gap:16px;padding:12px 16px;'
                        f'border:1px solid {border_color};border-radius:6px;margin-bottom:8px;'
                        f'background:{bg};transition:all 0.15s">'
                        f'<div style="min-width:160px">'
                        f'<div style="font-size:14px;font-weight:600;color:#242424">{sprint_name}{badge}</div>'
                        f'<div style="font-size:11px;color:#616161;margin-top:2px">{start_str} → {end_str}</div>'
                        f'</div>'
                        f'<div style="flex:1;display:flex;align-items:center;gap:12px">'
                        f'<div style="flex:1;height:8px;background:#f3f2f1;border-radius:4px;overflow:hidden">'
                        f'<div style="width:{pct}%;height:100%;background:{bar_color};'
                        f'border-radius:4px;transition:width 0.3s"></div></div>'
                        f'<span style="font-size:12px;color:#616161;min-width:70px;text-align:right">'
                        f'{done}/{total} done</span>'
                        f'</div></div>'
                    )
            else:
                gantt_html += '<div style="color:#8a8886;font-size:13px">No sprints with date ranges found.</div>'

            gantt_html += '</div>'
            st.markdown(gantt_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Reports":
    st.markdown("## Reports")
    st.markdown("Generate insights and export data.")

    tab_quick, tab_custom, tab_export = st.tabs(["Quick Reports", "Custom Report", "Export"])

    with tab_quick:
        report_options = [
            ("📊", "Executive Summary", "High-level overview for leadership"),
            ("🌍", "Regional Breakdown", "Projects grouped by continent and country"),
            ("🚨", "Blocked & At Risk", "All projects with blockers or risk flags"),
            ("📅", "Timeline Status", "Upcoming deadlines and overdue projects"),
            ("🤖", "Robin Dependencies", "All projects waiting on ROBIN hardware"),
            ("💰", "Cost Summary", "Budget overview across all installations"),
        ]

        # 2x3 grid
        for row in range(2):
            cols = st.columns(3)
            for col_idx in range(3):
                idx = row * 3 + col_idx
                icon, title, desc = report_options[idx]
                with cols[col_idx]:
                    st.markdown(
                        f'<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;'
                        f'padding:20px;text-align:center;min-height:140px">'
                        f'<div style="font-size:28px;margin-bottom:8px">{icon}</div>'
                        f'<div style="font-size:14px;font-weight:600">{title}</div>'
                        f'<div style="font-size:12px;color:#616161;margin-top:4px">{desc}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(f"Generate", key=f"report_{idx}", use_container_width=True,
                                 disabled=not llm_available):
                        st.session_state["report_type"] = title

        days_range = st.slider("Include history from last N days", 7, 90, 30)

        if st.session_state.get("report_type"):
            with st.spinner(f"Generating {st.session_state['report_type']}..."):
                from llm import generate_report
                report = generate_report(st.session_state["report_type"], days=days_range)
            st.markdown("---")
            st.markdown(report)
            del st.session_state["report_type"]

    with tab_custom:
        st.markdown("Describe the report you want in plain English:")
        custom_request = st.text_area(
            "Report request", height=100,
            placeholder="e.g., Show me all South America projects grouped by country with their current blockers",
        )
        if st.button("Generate Custom Report", type="primary", disabled=not llm_available or not custom_request.strip()):
            with st.spinner("Generating..."):
                from llm import generate_report
                report = generate_report(custom_request)
            st.markdown("---")
            st.markdown(report)

    with tab_export:
        export_cols = st.columns(2)
        with export_cols[0]:
            st.markdown(
                '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;padding:20px">'
                '<div style="font-size:14px;font-weight:600">Projects CSV</div>'
                '<div style="font-size:13px;color:#616161;margin:8px 0">Current state of all projects</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            projects = get_all_projects()
            df = pd.DataFrame(projects)
            csv = df.to_csv(index=False)
            st.download_button("Download Projects", csv, "sparrow_projects.csv", "text/csv",
                               use_container_width=True)

        with export_cols[1]:
            st.markdown(
                '<div style="background:#fff;border:1px solid #edebe9;border-radius:8px;padding:20px">'
                '<div style="font-size:14px;font-weight:600">History CSV</div>'
                '<div style="font-size:13px;color:#616161;margin:8px 0">Full changelog of all updates</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            all_history = get_recent_history(days=365, limit=5000)
            if all_history:
                for h in all_history:
                    h["changes"] = json.dumps(h["changes"])
                hdf = pd.DataFrame(all_history)
                hcsv = hdf.to_csv(index=False)
                st.download_button("Download History", hcsv, "sparrow_history.csv", "text/csv",
                                   use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Settings":
    st.markdown("## Settings")
    st.markdown("Configure monitoring, team, and integrations.")

    tab_team, tab_monitor, tab_devops, tab_email, tab_notif, tab_ai = st.tabs(
        ["Team", "Monitor", "Azure DevOps", "Email Ingestion", "Notifications", "AI / LLM"]
    )

    with tab_team:
        st.markdown("### Team Members")
        team_data = []
        for member in TEAM_MEMBERS:
            team_data.append({"Name": member, "Email": "Not configured", "Role": "Member"})
        st.dataframe(pd.DataFrame(team_data), use_container_width=True, hide_index=True)
        st.caption("Edit team members in config.py → TEAM_MEMBERS")

    with tab_monitor:
        st.markdown("### Staleness Thresholds")
        st.markdown("Projects are flagged as stale when they haven't been updated within these windows:")
        threshold_df = pd.DataFrame(
            [{"Status": k, "Stale After (days)": v} for k, v in STALENESS_THRESHOLDS.items()]
        )
        st.dataframe(threshold_df, use_container_width=True, hide_index=True)

        st.markdown("### Deadline Alert Windows")
        from config import DEADLINE_ALERTS
        for alert in DEADLINE_ALERTS:
            days = alert["days_before"]
            sev = alert["severity"]
            label = "Overdue" if days == 0 else f"{days} days before"
            st.markdown(f"- {severity_badge_html(sev)} — {label}", unsafe_allow_html=True)

        st.markdown("### Run Monitor")
        use_llm = st.checkbox("Use LLM for nudge generation", value=llm_available, disabled=not llm_available)
        if st.button("Run Monitor Check", type="primary"):
            with st.spinner("Checking all projects..."):
                from monitor import run_monitor
                import io
                from contextlib import redirect_stdout

                f = io.StringIO()
                with redirect_stdout(f):
                    nudges = run_monitor(use_llm=use_llm, dry_run=False, send_email=False)
                output = f.getvalue()

            if nudges:
                st.warning(f"Found {len(nudges)} project(s) needing attention.")
                for n in nudges:
                    st.markdown(f"**{n['project_id']}** — {n['type']} ({n['severity']})")
                    st.markdown(n["message"][:300])
                    st.markdown("---")
            else:
                st.success("All projects are up to date.")
            with st.expander("Raw output"):
                st.text(output)

        st.markdown("### Schedule (Cron)")
        st.code(
            "# Add to crontab (crontab -e) — runs weekdays at 9am:\n"
            "0 9 * * 1-5  cd /path/to/sparrow-tracker && python3 monitor.py --send-email",
            language="bash",
        )

    with tab_devops:
        st.markdown("### Azure DevOps Integration")
        from config import AZURE_DEVOPS_PAT, AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, DEVOPS_SEARCH_TERMS
        devops_configured = bool(AZURE_DEVOPS_PAT)
        if devops_configured:
            st.success(f"Connected to Azure DevOps")
            st.markdown(f"**Organization:** `{AZURE_DEVOPS_ORG}`")
            st.markdown(f"**Project:** `{AZURE_DEVOPS_PROJECT}`")
            st.markdown(f"**Search terms:** {', '.join(DEVOPS_SEARCH_TERMS)}")

            from devops_sync import get_last_sync_time, sync_all
            last_sync = get_last_sync_time()
            if last_sync:
                st.markdown(f"**Last synced:** {last_sync}")

            if st.button("Sync Now", type="primary", key="settings_devops_sync"):
                with st.spinner("Syncing from Azure DevOps..."):
                    try:
                        result = sync_all()
                        st.success(f"Synced {result['iterations']} sprints, {result['work_items']} work items")
                    except Exception as e:
                        st.error(f"Sync failed: {e}")

            if st.button("Test Connection", key="test_devops"):
                try:
                    from devops_sync import fetch_iterations
                    iters = fetch_iterations()
                    st.success(f"Connection OK — found {len(iters)} iterations")
                except Exception as e:
                    st.error(f"Connection failed: {e}")
        else:
            st.warning("Not configured. Add your Azure DevOps PAT to `.env`.")

        st.code(
            "# Add to .env:\n"
            "AZURE_DEVOPS_PAT=your-personal-access-token\n"
            "AZURE_DEVOPS_ORG=onecela\n"
            "AZURE_DEVOPS_PROJECT=AI For Good Lab",
            language="bash",
        )

    with tab_email:
        st.markdown("### Email Ingestion (IMAP)")
        st.markdown("Configure a mailbox for automatic email processing.")
        imap_configured = bool(IMAP_HOST)
        if imap_configured:
            st.success(f"IMAP configured: {IMAP_HOST}")
        else:
            st.info("Not configured. Add IMAP settings to your `.env` file.")

        st.code(
            "# Add to .env:\n"
            "IMAP_HOST=imap.example.com\n"
            "IMAP_USER=sparrow-inbox@example.com\n"
            "IMAP_PASS=your-password\n"
            "IMAP_FOLDER=INBOX\n"
            "IMAP_DONE_FOLDER=Processed",
            language="bash",
        )

        if imap_configured:
            if st.button("Test Connection"):
                try:
                    from email_ingest import connect_imap
                    imap = connect_imap()
                    imap.logout()
                    st.success("Connection successful!")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    with tab_notif:
        st.markdown("### Notification Settings (SMTP)")
        from config import SMTP_HOST
        if SMTP_HOST:
            st.success(f"SMTP configured: {SMTP_HOST}")
        else:
            st.info("Not configured. Add SMTP settings to your `.env` file.")

        st.code(
            "# Add to .env:\n"
            "SPARROW_SMTP_HOST=smtp.example.com\n"
            "SPARROW_SMTP_PORT=587\n"
            "SPARROW_SMTP_USER=your-user\n"
            "SPARROW_SMTP_PASS=your-password\n"
            "SPARROW_NOTIFY_FROM=sparrow-tracker@noreply.local",
            language="bash",
        )

    with tab_ai:
        st.markdown("### AI / LLM Configuration")
        if llm_available:
            st.success(f"Connected to Azure OpenAI")
            st.markdown(f"**Endpoint:** `{AZURE_OPENAI_ENDPOINT[:40]}...`")
            st.markdown(f"**Deployment:** `{AZURE_OPENAI_DEPLOYMENT}`")

            if st.button("Test Connection", key="test_llm"):
                try:
                    from llm import _chat
                    result = _chat("You are a test.", "Say hello in one word.")
                    st.success(f"Connected — Response: \"{result}\"")
                except Exception as e:
                    st.error(f"Connection failed: {e}")
        else:
            st.warning("Not configured. Add Azure OpenAI settings to your `.env` file.")

        st.code(
            "# Add to .env:\n"
            "AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/\n"
            "AZURE_OPENAI_DEPLOYMENT=gpt-4\n"
            "AZURE_OPENAI_API_KEY=your-key\n"
            "AZURE_OPENAI_API_VERSION=2024-10-21",
            language="bash",
        )

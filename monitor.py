#!/usr/bin/env python3
"""
SPARROW Installation Tracker — Timeline Monitor

Checks all active projects for:
  1. Staleness — no updates within the threshold for the project's status
  2. Deadline proximity — target date approaching or overdue

Generates context-aware nudges via the LLM and stores them in the database.
Can optionally send digest emails.

Usage:
  python3 monitor.py                  # check and print nudges
  python3 monitor.py --send-email     # check, store, and email digest
  python3 monitor.py --dry-run        # show what would be flagged, no writes

Schedule via cron, e.g.:
  0 9 * * 1-5  cd /path/to/sparrow-tracker && python3 monitor.py --send-email
"""

import argparse
import os
import sys
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(__file__))

from db import (
    init_db, get_stale_projects, get_deadline_approaching,
    get_active_nudges, add_nudge, get_project_history,
)
from config import CLOSED_STATUSES, TEAM_MEMBERS


def check_staleness(use_llm=True, dry_run=False):
    """Find stale projects and generate nudges."""
    stale = get_stale_projects()
    nudges_created = []

    for p in stale:
        pid = p["project_id"]
        # Skip if there's already an active nudge of the same type
        existing = get_active_nudges(pid)
        if any(n["nudge_type"] == "stale" for n in existing):
            continue

        days = p["days_since_update"]
        threshold = p["threshold"]
        health = p.get("health") or "On Track"
        reason = (
            f"No update in {days} days (threshold for '{health}' health is {threshold} days)."
        )

        if use_llm:
            try:
                from llm import generate_nudge
                message = generate_nudge(p, reason)
            except Exception as e:
                message = (
                    f"**{p['location']} ({p['country']})** — No update in {days} days.\n"
                    f"Status: {p['status']} | Owner: {p.get('team_owner') or 'unassigned'}\n"
                    f"Notes: {p.get('notes') or 'none'}\n"
                    f"Please provide an update."
                )
        else:
            message = (
                f"**{p['location']} ({p['country']})** — No update in {days} days.\n"
                f"Status: {p['status']} | Owner: {p.get('team_owner') or 'unassigned'}\n"
                f"Notes: {p.get('notes') or 'none'}\n"
                f"Please provide an update."
            )

        severity = "warning" if days >= threshold * 2 else "info"

        if not dry_run:
            add_nudge(pid, "stale", severity, message, sent_to=p.get("team_owner"))

        nudges_created.append({
            "project_id": pid,
            "type": "stale",
            "severity": severity,
            "days_since_update": days,
            "message": message,
            "owner": p.get("team_owner"),
        })

    return nudges_created


def check_deadlines(use_llm=True, dry_run=False):
    """Find projects approaching or past their deadline and generate nudges."""
    approaching = get_deadline_approaching()
    nudges_created = []

    for p in approaching:
        pid = p["project_id"]
        existing = get_active_nudges(pid)
        if any(n["nudge_type"] == "deadline" for n in existing):
            continue

        days_until = p["days_until_deadline"]
        severity = p["alert_severity"]

        if days_until < 0:
            reason = f"Project is {abs(days_until)} days OVERDUE (target: {p['target_date']})."
        elif days_until == 0:
            reason = f"Project target date is TODAY ({p['target_date']})."
        else:
            reason = f"Project target date is in {days_until} days ({p['target_date']})."

        if use_llm:
            try:
                from llm import generate_nudge
                message = generate_nudge(p, reason)
            except Exception:
                message = (
                    f"**{p['location']} ({p['country']})** — {reason}\n"
                    f"Status: {p['status']} | Owner: {p.get('team_owner') or 'unassigned'}\n"
                    f"Last updated: {p.get('last_updated', 'unknown')}"
                )
        else:
            message = (
                f"**{p['location']} ({p['country']})** — {reason}\n"
                f"Status: {p['status']} | Owner: {p.get('team_owner') or 'unassigned'}\n"
                f"Last updated: {p.get('last_updated', 'unknown')}"
            )

        if not dry_run:
            add_nudge(pid, "deadline", severity, message, sent_to=p.get("team_owner"))

        nudges_created.append({
            "project_id": pid,
            "type": "deadline",
            "severity": severity,
            "days_until": days_until,
            "message": message,
            "owner": p.get("team_owner"),
        })

    return nudges_created


def run_monitor(use_llm=True, dry_run=False, send_email=False):
    """Run all checks and optionally send notifications."""
    init_db()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Running SPARROW monitor...\n")

    stale_nudges = check_staleness(use_llm=use_llm, dry_run=dry_run)
    deadline_nudges = check_deadlines(use_llm=use_llm, dry_run=dry_run)

    all_nudges = stale_nudges + deadline_nudges

    if not all_nudges:
        print("No projects need attention right now.")
        return all_nudges

    # Group by owner for display
    by_owner = {}
    for n in all_nudges:
        owner = n.get("owner") or "Unassigned"
        by_owner.setdefault(owner, []).append(n)

    for owner, nudges in sorted(by_owner.items()):
        print(f"\n{'='*60}")
        print(f"  {owner} — {len(nudges)} project(s) need attention")
        print(f"{'='*60}")
        for n in nudges:
            icon = {"info": "ℹ️ ", "warning": "⚠️ ", "escalation": "🔴"}.get(n["severity"], "")
            print(f"\n{icon} [{n['type'].upper()}] {n['project_id']}")
            print(f"  {n['message']}")

    if send_email and not dry_run:
        try:
            from notifications import send_digest
            send_digest(all_nudges)
            print("\nDigest emails sent.")
        except Exception as e:
            print(f"\nFailed to send emails: {e}")

    print(f"\nTotal: {len(stale_nudges)} stale, {len(deadline_nudges)} deadline.")
    return all_nudges


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SPARROW timeline monitor")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be flagged without writing to DB")
    parser.add_argument("--send-email", action="store_true", help="Send digest emails after checking")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM for nudge generation (use templates)")
    args = parser.parse_args()

    run_monitor(use_llm=not args.no_llm, dry_run=args.dry_run, send_email=args.send_email)

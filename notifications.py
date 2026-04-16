"""
SPARROW Installation Tracker — Notification System

Formats nudges into digest emails grouped by team owner.
Supports SMTP and console output.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, NOTIFY_FROM, TEAM_MEMBERS


# ── Email addresses for team (configure here or in a DB table) ────────────────
# Map team member names to their email addresses.
# Update this dict or move to config/DB as needed.
TEAM_EMAILS = {
    # "Bruno": "bruno@example.com",
    # "Carl":  "carl@example.com",
}


def _format_digest_html(owner: str, nudges: list) -> str:
    """Format nudges into an HTML email body."""
    today = datetime.now().strftime("%B %d, %Y")
    severity_icon = {"info": "&#8505;&#65039;", "warning": "&#9888;&#65039;", "escalation": "&#128308;"}

    rows = []
    for n in nudges:
        icon = severity_icon.get(n.get("severity", ""), "")
        rows.append(f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee">{icon} {n.get('severity','').upper()}</td>
            <td style="padding:8px;border-bottom:1px solid #eee"><strong>{n['project_id']}</strong></td>
            <td style="padding:8px;border-bottom:1px solid #eee">{n['type']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{n['message'][:200]}</td>
        </tr>""")

    return f"""
    <html><body style="font-family:Segoe UI,Arial,sans-serif;color:#333">
    <h2>SPARROW Tracker &mdash; Daily Digest for {owner}</h2>
    <p style="color:#666">{today}</p>
    <p><strong>{len(nudges)} project(s) need your attention:</strong></p>
    <table style="border-collapse:collapse;width:100%">
        <tr style="background:#f5f5f5">
            <th style="padding:8px;text-align:left">Severity</th>
            <th style="padding:8px;text-align:left">Project</th>
            <th style="padding:8px;text-align:left">Type</th>
            <th style="padding:8px;text-align:left">Details</th>
        </tr>
        {''.join(rows)}
    </table>
    <p style="margin-top:20px;color:#666;font-size:0.9em">
        Paste your update into the SPARROW Tracker to resolve these items.
    </p>
    </body></html>
    """


def _format_digest_text(owner: str, nudges: list) -> str:
    """Format nudges into plain text."""
    today = datetime.now().strftime("%B %d, %Y")
    lines = [
        f"SPARROW Tracker — Daily Digest for {owner}",
        today,
        f"\n{len(nudges)} project(s) need your attention:\n",
    ]
    for i, n in enumerate(nudges, 1):
        lines.append(f"  {i}. [{n.get('severity','').upper()}] {n['project_id']} ({n['type']})")
        lines.append(f"     {n['message'][:200]}")
        lines.append("")
    lines.append("Paste your update into the SPARROW Tracker to resolve these items.")
    return "\n".join(lines)


def send_digest(all_nudges: list):
    """Group nudges by owner and send one email per owner."""
    by_owner = {}
    for n in all_nudges:
        owner = n.get("owner") or "Unassigned"
        by_owner.setdefault(owner, []).append(n)

    for owner, nudges in by_owner.items():
        email_addr = TEAM_EMAILS.get(owner)

        # Always print to console
        print(f"\n--- Digest for {owner} ---")
        print(_format_digest_text(owner, nudges))

        if not email_addr:
            print(f"  (No email configured for {owner}, skipping send)")
            continue

        if not SMTP_HOST:
            print(f"  (SMTP not configured, skipping send)")
            continue

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"SPARROW Tracker — {len(nudges)} project(s) need attention"
        msg["From"] = NOTIFY_FROM
        msg["To"] = email_addr
        msg.attach(MIMEText(_format_digest_text(owner, nudges), "plain"))
        msg.attach(MIMEText(_format_digest_html(owner, nudges), "html"))

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(NOTIFY_FROM, [email_addr], msg.as_string())
            print(f"  Email sent to {email_addr}")
        except Exception as e:
            print(f"  Failed to send email to {email_addr}: {e}")

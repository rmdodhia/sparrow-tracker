"""
SPARROW Installation Tracker — Email Ingestion

Supports two backends:
  - Microsoft Graph (production) — reads from sparrow-tracker@microsoft.com
  - IMAP (legacy/local dev) — polls an IMAP mailbox

Backend is auto-selected based on config: Graph if GRAPH_CLIENT_ID is set,
otherwise IMAP if IMAP_HOST is set.
"""

import imaplib
import email
from email.header import decode_header
from datetime import datetime

from config import (
    IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASS,
    IMAP_FOLDER, IMAP_DONE_FOLDER, EMAIL_BACKEND,
)
from llm import parse_input
from db import (
    update_project, add_history, add_contact, add_raw_input,
)


def _decode_header_value(value):
    """Decode an email header that may be encoded."""
    if value is None:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body(msg):
    """Extract plain-text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and "attachment" not in (part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        # Fallback: try text/html
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html" and "attachment" not in (part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def _apply_result(result, email_text, sender):
    """Apply a parsed LLM result: update projects, save contacts, log history."""
    changes = result.get("proposed_changes", [])
    contacts = result.get("new_contacts", [])
    history_ids = []

    for change in changes:
        pid = change.get("project_id")
        field = change.get("field")
        new_val = change.get("new_value")
        if not pid or not field:
            continue
        try:
            field_changes = update_project(pid, {field: new_val}, sender)
        except ValueError:
            continue
        if field_changes:
            hid = add_history(
                pid, field_changes,
                source_text=email_text[:2000],
                source_type="email",
                updated_by=sender,
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
        email_text[:5000],
        submitted_by=sender,
        input_type="email",
        history_ids=history_ids,
    )

    return {
        "changes_applied": len(history_ids),
        "contacts_added": len(contacts),
        "summary": result.get("llm_summary", ""),
        "input_type": result.get("input_type", "unknown"),
    }


def connect_imap():
    """Connect to the IMAP server and return the mailbox connection."""
    if not IMAP_HOST or not IMAP_USER:
        raise RuntimeError(
            "IMAP not configured. Set IMAP_HOST, IMAP_USER, IMAP_PASS in .env"
        )
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(IMAP_USER, IMAP_PASS)
    return imap


def fetch_unread_emails(imap=None, limit=20):
    """Fetch unread emails from the configured IMAP folder.
    Returns list of dicts with subject, sender, body, uid.
    """
    own_conn = imap is None
    if own_conn:
        imap = connect_imap()

    try:
        imap.select(IMAP_FOLDER)
        status, data = imap.uid("search", None, "UNSEEN")
        if status != "OK":
            return []

        uids = data[0].split()
        if not uids:
            return []

        emails = []
        for uid in uids[-limit:]:
            status, msg_data = imap.uid("fetch", uid, "(RFC822)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            emails.append({
                "uid": uid,
                "subject": _decode_header_value(msg.get("Subject")),
                "sender": _decode_header_value(msg.get("From")),
                "date": _decode_header_value(msg.get("Date")),
                "body": _extract_body(msg),
            })
        return emails
    finally:
        if own_conn:
            imap.logout()


def mark_as_read(imap, uid):
    """Mark an email as read (add \\Seen flag)."""
    imap.uid("store", uid, "+FLAGS", "(\\Seen)")


def move_to_done(imap, uid):
    """Move processed email to the done folder."""
    if IMAP_DONE_FOLDER:
        imap.uid("copy", uid, IMAP_DONE_FOLDER)
        imap.uid("store", uid, "+FLAGS", "(\\Deleted)")
        imap.expunge()
    else:
        mark_as_read(imap, uid)


def process_mailbox(auto_apply=False, limit=20):
    """Poll the mailbox, parse each email through the LLM, optionally auto-apply.

    Auto-selects Graph or IMAP backend based on config.EMAIL_BACKEND.
    Returns a list of results, one per email processed.
    """
    if EMAIL_BACKEND == "graph":
        return _process_mailbox_graph(auto_apply=auto_apply, limit=limit)
    return _process_mailbox_imap(auto_apply=auto_apply, limit=limit)


def _process_mailbox_graph(auto_apply=False, limit=20):
    """Process emails via Microsoft Graph API."""
    from graph_email import (
        fetch_unread_emails as graph_fetch,
        mark_as_read as graph_mark_read,
        move_to_folder as graph_move,
    )
    results = []
    emails = graph_fetch(limit=limit)

    for em in emails:
        full_text = f"Subject: {em['subject']}\nFrom: {em['sender']}\n\n{em['body']}"
        parsed = parse_input(full_text, submitted_by=em["sender"])

        entry = {
            "email": em,
            "parsed": parsed,
            "applied": False,
        }

        if auto_apply and parsed.get("input_type") == "update":
            high_confidence = all(
                m.get("match_confidence") == "high"
                for m in parsed.get("matched_projects", [])
            )
            if high_confidence and parsed.get("proposed_changes"):
                apply_result = _apply_result(parsed, full_text, em["sender"])
                entry["apply_result"] = apply_result
                entry["applied"] = True
                graph_move(em["id"])
            else:
                graph_mark_read(em["id"])
        else:
            graph_mark_read(em["id"])

        results.append(entry)

    return results


def _process_mailbox_imap(auto_apply=False, limit=20):
    """Process emails via IMAP (legacy)."""
    imap = connect_imap()
    results = []

    try:
        emails = fetch_unread_emails(imap, limit=limit)

        for em in emails:
            full_text = f"Subject: {em['subject']}\nFrom: {em['sender']}\n\n{em['body']}"
            parsed = parse_input(full_text, submitted_by=em["sender"])

            entry = {
                "email": em,
                "parsed": parsed,
                "applied": False,
            }

            if auto_apply and parsed.get("input_type") == "update":
                high_confidence = all(
                    m.get("match_confidence") == "high"
                    for m in parsed.get("matched_projects", [])
                )
                if high_confidence and parsed.get("proposed_changes"):
                    apply_result = _apply_result(parsed, full_text, em["sender"])
                    entry["apply_result"] = apply_result
                    entry["applied"] = True
                    move_to_done(imap, em["uid"])
                else:
                    mark_as_read(imap, em["uid"])
            else:
                mark_as_read(imap, em["uid"])

            results.append(entry)

        return results
    finally:
        imap.logout()

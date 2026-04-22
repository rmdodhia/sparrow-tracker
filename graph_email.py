"""
SPARROW Installation Tracker — Microsoft Graph Email Client

Reads email from a shared mailbox (sparrow-tracker@microsoft.com) using
the Microsoft Graph API with client credentials (daemon/app-only) flow.

Requires:
  - App registration with Mail.ReadWrite (Application) + admin consent
  - GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID in env
"""

import msal
import requests

from config import (
    GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID, GRAPH_USER_EMAIL,
)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPES = ["https://graph.microsoft.com/.default"]

_cached_app = None


def _get_app():
    """Return a cached MSAL ConfidentialClientApplication."""
    global _cached_app
    if _cached_app is None:
        if not GRAPH_CLIENT_ID or not GRAPH_CLIENT_SECRET:
            raise RuntimeError(
                "Microsoft Graph not configured. Set GRAPH_CLIENT_ID, "
                "GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID in .env"
            )
        _cached_app = msal.ConfidentialClientApplication(
            GRAPH_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}",
            client_credential=GRAPH_CLIENT_SECRET,
        )
    return _cached_app


def _get_token() -> str:
    """Acquire an app-only access token for Microsoft Graph."""
    app = _get_app()
    result = app.acquire_token_for_client(scopes=_SCOPES)
    if "access_token" in result:
        return result["access_token"]
    raise RuntimeError(
        f"Failed to acquire Graph token: {result.get('error_description', result)}"
    )


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


def fetch_unread_emails(limit=20) -> list[dict]:
    """Fetch unread emails from the configured Graph mailbox.

    Returns list of dicts with id, subject, sender, body, receivedDateTime.
    """
    url = (
        f"{_GRAPH_BASE}/users/{GRAPH_USER_EMAIL}/mailFolders/Inbox/messages"
        f"?$filter=isRead eq false"
        f"&$top={limit}"
        f"&$select=id,subject,from,body,receivedDateTime"
        f"&$orderby=receivedDateTime desc"
    )
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()

    emails = []
    for msg in resp.json().get("value", []):
        sender_email = ""
        sender_name = ""
        from_field = msg.get("from", {}).get("emailAddress", {})
        if from_field:
            sender_email = from_field.get("address", "")
            sender_name = from_field.get("name", "")

        emails.append({
            "id": msg["id"],
            "subject": msg.get("subject", ""),
            "sender": f"{sender_name} <{sender_email}>" if sender_name else sender_email,
            "sender_email": sender_email,
            "date": msg.get("receivedDateTime", ""),
            "body": msg.get("body", {}).get("content", ""),
        })
    return emails


def mark_as_read(message_id: str):
    """Mark a message as read in the mailbox."""
    url = f"{_GRAPH_BASE}/users/{GRAPH_USER_EMAIL}/messages/{message_id}"
    resp = requests.patch(
        url, headers=_headers(), json={"isRead": True}, timeout=15,
    )
    resp.raise_for_status()


def move_to_folder(message_id: str, folder_name: str = "Archive"):
    """Move a processed message to a folder (e.g., Archive)."""
    # First, find the folder ID
    url = f"{_GRAPH_BASE}/users/{GRAPH_USER_EMAIL}/mailFolders"
    resp = requests.get(
        url, headers=_headers(),
        params={"$filter": f"displayName eq '{folder_name}'"},
        timeout=15,
    )
    resp.raise_for_status()
    folders = resp.json().get("value", [])

    if folders:
        folder_id = folders[0]["id"]
    else:
        # Create the folder if it doesn't exist
        resp = requests.post(
            url, headers=_headers(),
            json={"displayName": folder_name}, timeout=15,
        )
        resp.raise_for_status()
        folder_id = resp.json()["id"]

    # Move the message
    move_url = f"{_GRAPH_BASE}/users/{GRAPH_USER_EMAIL}/messages/{message_id}/move"
    resp = requests.post(
        move_url, headers=_headers(),
        json={"destinationId": folder_id}, timeout=15,
    )
    resp.raise_for_status()

"""
SPARROW Installation Tracker — Microsoft Graph Email Client

Reads email from a shared mailbox (sparrow-tracker@microsoft.com) using
the Microsoft Graph API.

Auth strategy (in priority order):
  1. Managed identity (production on App Service) — no secrets needed
  2. MSAL client credentials (if GRAPH_CLIENT_SECRET is set)
  3. DefaultAzureCredential fallback (az login, VS Code, etc.)

Requires:
  - App registration with Mail.ReadWrite (Application) + admin consent
  - GRAPH_USER_EMAIL set to the target mailbox
"""

import requests

from config import (
    GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID, GRAPH_USER_EMAIL,
)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"

_cached_credential = None


def _get_token() -> str:
    """Acquire an access token for Microsoft Graph.

    Uses MSAL client credentials if a secret is configured,
    otherwise falls back to DefaultAzureCredential (managed identity,
    az login, etc.).
    """
    global _cached_credential

    # Path 1: MSAL client credentials (if secret is available)
    if GRAPH_CLIENT_SECRET and GRAPH_CLIENT_ID:
        import msal
        if _cached_credential is None:
            _cached_credential = msal.ConfidentialClientApplication(
                GRAPH_CLIENT_ID,
                authority=f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}",
                client_credential=GRAPH_CLIENT_SECRET,
            )
        result = _cached_credential.acquire_token_for_client(
            scopes=[_GRAPH_SCOPE]
        )
        if "access_token" in result:
            return result["access_token"]
        raise RuntimeError(
            f"MSAL token acquisition failed: {result.get('error_description', result)}"
        )

    # Path 2: DefaultAzureCredential (managed identity on App Service, az login locally)
    from azure.identity import DefaultAzureCredential
    if _cached_credential is None:
        _cached_credential = DefaultAzureCredential()
    token = _cached_credential.get_token(_GRAPH_SCOPE)
    return token.token


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

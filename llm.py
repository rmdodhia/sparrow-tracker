"""
SPARROW Installation Tracker — LLM Integration (Azure OpenAI)

Authenticates via API key (set AZURE_OPENAI_API_KEY), falling back to Azure AD (az login).
"""

import json
from openai import AzureOpenAI

from config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_API_KEY, VALID_STATUSES,
)
from db import get_all_projects, get_project_history, get_recent_history


_cached_client = None


def _client():
    global _cached_client
    if _cached_client is not None:
        return _cached_client

    if not AZURE_OPENAI_ENDPOINT:
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT not set. Either:\n"
            "  1. Set it in config.py, or\n"
            "  2. export AZURE_OPENAI_ENDPOINT='https://your-resource.openai.azure.com/'\n\n"
            "Then set AZURE_OPENAI_API_KEY, or run:  az login --use-device-code"
        )

    if AZURE_OPENAI_API_KEY:
        _cached_client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    else:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        _cached_client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_ad_token_provider=token_provider,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    return _cached_client


def _chat(system: str, user: str, max_tokens: int = 4096) -> str:
    """Send a chat completion request and return the assistant's text."""
    client = _client()
    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content


def _projects_context(projects=None):
    """Format all projects as compact context for the LLM."""
    if projects is None:
        projects = get_all_projects()
    lines = []
    for p in projects:
        lines.append(
            f"- {p['project_id']}: {p['location']} ({p['country']}) | "
            f"Partner: {p['partner_org']} | Status: {p['status']} | "
            f"Owner: {p.get('team_owner') or 'unassigned'} | "
            f"Timeline: {p.get('timeline_label') or 'TBD'} | "
            f"Target date: {p.get('target_date') or 'none'} | "
            f"Hardware: {p.get('hardware') or 'TBD'} | "
            f"Cost: {p.get('estimated_cost') or 'TBD'} | "
            f"Blocker: {p.get('blocker') or 'none'} | "
            f"Notes: {p.get('notes') or 'none'}"
        )
    return "\n".join(lines)


# ── Parse Input ───────────────────────────────────────────────────────────────

PARSE_SYSTEM = """You are the SPARROW Installation Tracker assistant. Your job is to process
unstructured text (emails, Teams messages, meeting notes, plain English updates) and extract
structured project updates.

CURRENT PROJECTS:
{projects}

VALID STATUSES (use only these): {statuses}

RULES:
1. Identify which project(s) the input relates to by matching location, partner, country,
   person names, or any identifying information.
2. Extract field updates: status, blocker, timeline_label, target_date, hardware,
   estimated_cost, deployment_type, team_owner, notes.
3. Extract any new contact information (names, emails, phones).
4. If the target_date can be inferred from language like "before end of FY26", normalize to
   ISO date (FY26 ends 2026-06-30). Include a confidence level: hard/committed/soft/aspirational.
5. If the input doesn't clearly map to a project, set match_confidence to "low".
6. If the input is a question rather than an update, set input_type to "question".
7. Preserve important context in a one-line llm_summary.
8. For status changes, only use statuses from the VALID STATUSES list.

Respond with ONLY valid JSON (no markdown fencing) in this exact format:
{{
  "input_type": "update" | "question" | "new_project" | "unclear",
  "matched_projects": [
    {{
      "project_id": "...",
      "match_confidence": "high" | "medium" | "low",
      "match_reason": "..."
    }}
  ],
  "proposed_changes": [
    {{
      "project_id": "...",
      "field": "...",
      "new_value": "...",
      "evidence": "quote or paraphrase from input that justifies this change"
    }}
  ],
  "new_contacts": [
    {{
      "name": "...",
      "organization": "...",
      "role": "...",
      "email": null,
      "phone": null,
      "linked_project": "..."
    }}
  ],
  "llm_summary": "one-line summary of what this input is about",
  "question_answer": null
}}

If input_type is "question", populate question_answer with your answer and leave proposed_changes empty.
"""


def parse_input(text: str, submitted_by: str = None) -> dict:
    """Send unstructured text to Azure OpenAI, get structured project update proposal."""
    projects = get_all_projects()
    system = PARSE_SYSTEM.format(
        projects=_projects_context(projects),
        statuses=", ".join(VALID_STATUSES),
    )

    raw = _chat(system, text).strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "input_type": "unclear",
            "matched_projects": [],
            "proposed_changes": [],
            "new_contacts": [],
            "llm_summary": "Failed to parse LLM response",
            "question_answer": None,
            "_raw_response": raw,
        }

    return result


# ── Answer Question ───────────────────────────────────────────────────────────

QUESTION_SYSTEM = """You are the SPARROW Installation Tracker assistant. Answer questions about
the SPARROW installation projects using the data provided. Be concise and specific.
Reference project IDs and locations when relevant.

CURRENT PROJECTS:
{projects}

RECENT HISTORY (last 30 days):
{history}

Answer the user's question directly. Use markdown tables or bullet points where helpful.
If you don't have enough information to answer, say so."""


def answer_question(question: str) -> str:
    """Answer a natural-language question about the projects."""
    projects = get_all_projects()
    history = get_recent_history(days=30)
    history_text = "\n".join(
        f"- [{h['timestamp']}] {h['project_id']}: {h.get('llm_summary', json.dumps(h['changes']))}"
        for h in history
    ) or "(no recent changes)"

    system = QUESTION_SYSTEM.format(
        projects=_projects_context(projects),
        history=history_text,
    )

    return _chat(system, question)


# ── Generate Nudge ────────────────────────────────────────────────────────────

NUDGE_SYSTEM = """You are the SPARROW Installation Tracker assistant generating a follow-up
nudge for a project that needs attention.

PROJECT:
{project}

RECENT HISTORY:
{history}

REASON FOR NUDGE: {reason}

Write a short, context-aware nudge (3-5 sentences max). Include:
1. What the project's current state is
2. What specifically triggered this nudge (staleness or approaching deadline)
3. A suggested follow-up action or question for the team owner

Be direct and helpful, not generic. Reference specific details from the history and notes."""


def generate_nudge(project: dict, reason: str) -> str:
    """Generate a context-aware nudge message for a stale or at-risk project."""
    history = get_project_history(project["project_id"], limit=10)
    history_text = "\n".join(
        f"- [{h['timestamp']}] {h.get('llm_summary', json.dumps(h['changes']))}"
        for h in history
    ) or "(no history)"

    project_text = "\n".join(f"  {k}: {v}" for k, v in project.items() if v)

    system = NUDGE_SYSTEM.format(
        project=project_text,
        history=history_text,
        reason=reason,
    )

    return _chat(system, "Generate the nudge message.", max_tokens=512)


# ── Generate Report ───────────────────────────────────────────────────────────

REPORT_SYSTEM = """You are the SPARROW Installation Tracker assistant generating a project report.

CURRENT PROJECTS:
{projects}

RECENT HISTORY (last {days} days):
{history}

Generate a report in markdown format based on the user's request. Be thorough but concise.
Use tables, bullet points, and sections as appropriate. Include project IDs for reference."""


def generate_report(request: str, days: int = 30) -> str:
    """Generate a custom report based on a natural-language request."""
    projects = get_all_projects()
    history = get_recent_history(days=days)
    history_text = "\n".join(
        f"- [{h['timestamp']}] {h['project_id']}: {h.get('llm_summary', json.dumps(h['changes']))}"
        for h in history
    ) or "(no recent changes)"

    system = REPORT_SYSTEM.format(
        projects=_projects_context(projects),
        history=history_text,
        days=days,
    )

    return _chat(system, request, max_tokens=8192)

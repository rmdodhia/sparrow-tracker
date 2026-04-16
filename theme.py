"""
SPARROW Tracker — Fluent Design Theme

Injects custom CSS to restyle Streamlit with Microsoft Fluent design language.
Call inject_theme() at the top of app.py after st.set_page_config().
"""

import streamlit as st

# ── Color Tokens ─────────────────────────────────────────────────────────────

COLORS = {
    "primary": "#0078d4",
    "primary_hover": "#106ebe",
    "primary_light": "#eff6fc",
    "surface": "#ffffff",
    "background": "#f5f5f5",
    "border": "#edebe9",
    "border_hover": "#c8c6c4",
    "text": "#242424",
    "text_secondary": "#616161",
    "text_muted": "#8a8886",
    "success": "#107c10",
    "success_bg": "#dff6dd",
    "warning": "#f7630c",
    "warning_bg": "#fff4ce",
    "danger": "#d13438",
    "danger_bg": "#fde7e9",
    "purple": "#5c2d91",
    "purple_bg": "#e8dff7",
    "neutral": "#8a8886",
    "neutral_bg": "#e8e8e8",
}

STATUS_COLORS = {
    "Scoping": (COLORS["neutral"], COLORS["neutral_bg"]),
    "Active - Waiting on Partner": ("#c4500e", "#fff1e6"),
    "Active - Waiting on Us": (COLORS["primary"], COLORS["primary_light"]),
    "Complete": (COLORS["success"], COLORS["success_bg"]),
    "Descoped": (COLORS["neutral"], COLORS["neutral_bg"]),
}


def status_pill_html(status: str, is_at_risk: bool = False) -> str:
    """Return an HTML span styled as a status pill, with optional risk flag."""
    fg, bg = STATUS_COLORS.get(status, (COLORS["neutral"], COLORS["neutral_bg"]))
    risk_html = (
        f' <span style="color:{COLORS["danger"]};font-size:11px" title="At Risk">\u26a0</span>'
        if is_at_risk else ''
    )
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;'
        f'font-size:12px;font-weight:600;background:{bg};color:{fg}">'
        f'{status}{risk_html}</span>'
    )


def severity_badge_html(severity: str) -> str:
    """Return an HTML badge for nudge severity."""
    colors = {
        "info": (COLORS["primary"], COLORS["primary_light"]),
        "warning": (COLORS["warning"], COLORS["warning_bg"]),
        "escalation": (COLORS["danger"], COLORS["danger_bg"]),
    }
    fg, bg = colors.get(severity, (COLORS["neutral"], COLORS["neutral_bg"]))
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
        f'font-size:11px;font-weight:600;background:{bg};color:{fg}">'
        f'{severity.upper()}</span>'
    )


def confidence_badge_html(confidence: str) -> str:
    """Return an HTML badge for match confidence."""
    colors = {
        "high": (COLORS["success"], COLORS["success_bg"]),
        "medium": ("#c4500e", "#fff1e6"),
        "low": (COLORS["danger"], COLORS["danger_bg"]),
    }
    fg, bg = colors.get(confidence, (COLORS["neutral"], COLORS["neutral_bg"]))
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
        f'font-size:11px;font-weight:600;background:{bg};color:{fg}">'
        f'{confidence.upper()}</span>'
    )


def metric_card_html(label: str, value, sublabel: str = None, color: str = None) -> str:
    """Return an HTML metric card."""
    color = color or COLORS["text"]
    sub_html = f'<div style="font-size:12px;color:{COLORS["text_secondary"]};margin-top:2px">{sublabel}</div>' if sublabel else ''
    return (
        f'<div style="background:#fff;border:1px solid {COLORS["border"]};border-radius:8px;'
        f'padding:16px;text-align:center">'
        f'<div style="font-size:12px;color:{COLORS["text_secondary"]};margin-bottom:4px">{label}</div>'
        f'<div style="font-size:22px;font-weight:700;color:{color}">{value}</div>'
        f'{sub_html}</div>'
    )


def attention_card_html(location: str, status: str, detail: str, severity: str = "warning") -> str:
    """Return an HTML attention card with colored left border."""
    border_colors = {"danger": COLORS["danger"], "warning": COLORS["warning"], "info": COLORS["primary"]}
    border = border_colors.get(severity, COLORS["warning"])
    return (
        f'<div style="background:#fff;border:1px solid {COLORS["border"]};border-left:4px solid {border};'
        f'border-radius:8px;padding:16px 18px;margin-bottom:10px;'
        f'box-shadow:0 1px 2px rgba(0,0,0,0.04);transition:all 0.15s ease;cursor:pointer" '
        f'onmouseover="this.style.boxShadow=\'0 1px 2px rgba(0,0,0,0.06)\';this.style.transform=\'translateX(2px)\'" '
        f'onmouseout="this.style.boxShadow=\'0 1px 2px rgba(0,0,0,0.04)\';this.style.transform=\'none\'">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
        f'<span style="font-weight:600;font-size:14px">{location}</span>'
        f'{status_pill_html(status)}</div>'
        f'<div style="font-size:13px;color:{COLORS["text_secondary"]};line-height:1.5">{detail}</div>'
        f'</div>'
    )


def activity_item_html(timestamp: str, text: str, source_type: str = "manual") -> str:
    """Return an HTML activity feed item."""
    dot_colors = {"manual": COLORS["primary"], "email": COLORS["success"], "system": COLORS["neutral"],
                  "teams_paste": COLORS["warning"], "manual_note": COLORS["primary"]}
    dot = dot_colors.get(source_type, COLORS["neutral"])
    return (
        f'<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid {COLORS["border"]}">'
        f'<div style="width:8px;height:8px;border-radius:50%;background:{dot};margin-top:5px;flex-shrink:0"></div>'
        f'<div style="flex:1">'
        f'<div style="font-size:11px;color:{COLORS["text_muted"]}">{timestamp}</div>'
        f'<div style="font-size:13px;color:{COLORS["text"]};margin-top:2px">{text}</div>'
        f'</div></div>'
    )


def timeline_entry_html(timestamp: str, source_type: str, author: str, summary: str,
                         changes: dict = None, source_text: str = None, expanded: bool = False) -> str:
    """Return an HTML timeline entry matching the v2 mockup design."""
    dot_class_map = {"email": "green", "manual_note": "blue", "manual": "blue",
                     "system": "purple", "teams_paste": "orange"}
    dot_class = dot_class_map.get(source_type, "blue")
    badge_class_map = {"email": "email", "manual_note": "manual", "manual": "manual",
                       "system": "system", "teams_paste": "teams"}
    badge_class = badge_class_map.get(source_type, "manual")
    source_labels = {"email": "Email", "manual_note": "Manual", "manual": "Manual",
                     "system": "System", "teams_paste": "Teams"}
    source_label = source_labels.get(source_type, source_type or "Update")

    # Field changes
    changes_html = ""
    if changes and expanded:
        rows = []
        for field, vals in changes.items():
            if field.startswith("_"):
                continue
            old = vals.get("old", "\u2014")
            new = vals.get("new", "\u2014")
            rows.append(
                f'<div class="tl-field-change">'
                f'<span class="tl-field-name">{field}</span>'
                f'<span class="tl-field-old">{old}</span>'
                f'<span class="tl-field-arrow">&rarr;</span>'
                f'<span class="tl-field-new">{new}</span>'
                f'</div>'
            )
        if rows:
            changes_html = f'<div class="tl-field-changes">{"".join(rows)}</div>'

    # Source text
    source_html = ""
    if source_text and expanded:
        truncated = source_text[:400]
        src_label = {"email": "Original email", "manual_note": "Manual entry", "manual": "Manual entry",
                     "system": "System note", "teams_paste": "Teams message"}.get(source_type, "Source")
        source_html = (
            f'<div class="tl-source-text">'
            f'<div class="tl-source-label">{src_label}</div>'
            f'{truncated}'
            f'</div>'
        )

    return (
        f'<div class="tl-entry">'
        f'<div class="tl-dot {dot_class}"><div class="tl-dot-inner"></div></div>'
        f'<div class="tl-card">'
        f'<div class="tl-card-header">'
        f'<span class="tl-time">{timestamp}</span>'
        f'<span class="tl-source-badge {badge_class}">{source_label}</span>'
        f'<span class="tl-author">by <strong>{author}</strong></span>'
        f'</div>'
        f'<div class="tl-summary">{summary}</div>'
        f'{changes_html}{source_html}'
        f'</div></div>'
    )


# ── Hero Banner ──────────────────────────────────────────────────────────────

HERO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 200">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0078d4"/>
      <stop offset="50%" stop-color="#2b88d8"/>
      <stop offset="100%" stop-color="#71afe5"/>
    </linearGradient>
    <linearGradient id="mountain1" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1b5e20"/>
      <stop offset="100%" stop-color="#2e7d32"/>
    </linearGradient>
    <linearGradient id="mountain2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#388e3c"/>
      <stop offset="100%" stop-color="#43a047"/>
    </linearGradient>
  </defs>
  <!-- Sky -->
  <rect width="1200" height="200" fill="url(#sky)"/>
  <!-- Clouds -->
  <ellipse cx="200" cy="50" rx="80" ry="25" fill="white" opacity="0.15"/>
  <ellipse cx="250" cy="45" rx="60" ry="20" fill="white" opacity="0.1"/>
  <ellipse cx="800" cy="35" rx="90" ry="22" fill="white" opacity="0.12"/>
  <ellipse cx="860" cy="30" rx="50" ry="18" fill="white" opacity="0.08"/>
  <!-- Sun -->
  <circle cx="1050" cy="45" r="30" fill="#FFD54F" opacity="0.6"/>
  <circle cx="1050" cy="45" r="22" fill="#FFEB3B" opacity="0.4"/>
  <!-- Far mountains -->
  <polygon points="0,200 100,100 200,140 350,80 500,130 600,90 750,120 900,70 1050,110 1200,85 1200,200" fill="url(#mountain1)" opacity="0.5"/>
  <!-- Near mountains -->
  <polygon points="0,200 80,140 200,160 300,120 450,155 550,110 700,150 850,115 950,145 1100,105 1200,130 1200,200" fill="url(#mountain2)" opacity="0.6"/>
  <!-- Trees (near) -->
  <polygon points="50,200 60,155 70,200" fill="#1b5e20" opacity="0.7"/>
  <polygon points="90,200 105,145 120,200" fill="#2e7d32" opacity="0.6"/>
  <polygon points="150,200 160,160 170,200" fill="#1b5e20" opacity="0.5"/>
  <polygon points="1050,200 1065,150 1080,200" fill="#1b5e20" opacity="0.7"/>
  <polygon points="1100,200 1110,160 1120,200" fill="#2e7d32" opacity="0.6"/>
  <polygon points="1140,200 1155,145 1170,200" fill="#1b5e20" opacity="0.5"/>
  <!-- Birds in flight -->
  <path d="M300,55 Q305,48 310,55 Q315,48 320,55" fill="none" stroke="white" stroke-width="1.5" opacity="0.7"/>
  <path d="M330,45 Q334,40 338,45 Q342,40 346,45" fill="none" stroke="white" stroke-width="1.2" opacity="0.5"/>
  <path d="M280,62 Q283,57 286,62 Q289,57 292,62" fill="none" stroke="white" stroke-width="1" opacity="0.4"/>
  <path d="M950,40 Q955,33 960,40 Q965,33 970,40" fill="none" stroke="white" stroke-width="1.5" opacity="0.6"/>
  <path d="M920,50 Q924,45 928,50 Q932,45 936,50" fill="none" stroke="white" stroke-width="1.2" opacity="0.4"/>
  <!-- Foreground grass -->
  <rect x="0" y="180" width="1200" height="20" fill="#2e7d32" opacity="0.4"/>
</svg>'''


# ── Main CSS ─────────────────────────────────────────────────────────────────

CUSTOM_CSS = """
<style>
/* ── Global ───────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

.stApp {
    font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* ── Gray background on main content area (match mockups) ── */
.stApp,
.stApp > header,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > section,
[data-testid="stMain"],
.main .block-container {
    background-color: #f5f5f5 !important;
}

/* Override Streamlit default padding */
.block-container {
    padding-top: 2rem !important;
    max-width: 1200px;
}

/* ── Sidebar Styling ──────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #edebe9;
}

section[data-testid="stSidebar"] > div {
    background: #ffffff !important;
}

section[data-testid="stSidebar"] .stRadio > label {
    font-size: 14px;
    color: #424242;
}

/* ── Cards ────────────────────────────────────────────── */
.sparrow-card {
    background: #ffffff;
    border: 1px solid #edebe9;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.sparrow-card-header {
    font-size: 16px;
    font-weight: 600;
    color: #242424;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

/* ── Stat Cards ───────────────────────────────────────── */
.stat-card {
    background: #ffffff;
    border: 1px solid #edebe9;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
    transition: all 0.15s ease;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.stat-card:hover {
    transform: translateY(-2px);
    border-color: #d2d0ce;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* ── Buttons ──────────────────────────────────────────── */
.stButton > button {
    border-radius: 6px;
    font-weight: 500;
    font-size: 13px;
    transition: all 0.15s ease;
}

/* Primary buttons */
.stButton > button[kind="primary"] {
    background-color: #0078d4;
    border-color: #0078d4;
}

.stButton > button[kind="primary"]:hover {
    background-color: #106ebe;
    border-color: #106ebe;
}

/* ── Section Titles ───────────────────────────────────── */
.section-title {
    font-size: 16px;
    font-weight: 700;
    color: #242424;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    letter-spacing: -0.2px;
}

.badge-count {
    background: #d13438;
    color: white;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 700;
    line-height: 1.4;
}

/* ── Alert Ribbon ─────────────────────────────────────── */
.alert-ribbon {
    background: #fff5f5;
    border: 1px solid #fecdd3;
    border-left: 4px solid #d13438;
    border-radius: 8px;
    padding: 14px 20px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 14px;
    animation: fadeInDown 0.3s ease;
}

@keyframes fadeInDown {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
}

.pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d13438;
    animation: pulse-glow 2s infinite;
    flex-shrink: 0;
}

@keyframes pulse-glow {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(209, 52, 56, 0.4); }
    50% { opacity: 0.8; box-shadow: 0 0 0 6px rgba(209, 52, 56, 0); }
}

/* ── Table Styling ────────────────────────────────────── */
.stDataFrame {
    border: 1px solid #edebe9;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

/* ── Activity Feed ────────────────────────────────────── */
.activity-feed {
    background: #ffffff;
    border: 1px solid #edebe9;
    border-radius: 8px;
    padding: 0 16px;
    max-height: 600px;
    overflow-y: auto;
}

.activity-feed::-webkit-scrollbar {
    width: 4px;
}

.activity-feed::-webkit-scrollbar-thumb {
    background: #d2d0ce;
    border-radius: 2px;
}

/* ── Hero Banner ──────────────────────────────────────── */
.hero-banner {
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 24px;
    position: relative;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.hero-banner svg {
    display: block;
    width: 100%;
    height: auto;
}

.hero-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 48px;
}

.hero-stat {
    text-align: center;
    color: white;
}

.hero-stat .num {
    font-size: 36px;
    font-weight: 700;
    text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

.hero-stat .lbl {
    font-size: 12px;
    opacity: 0.85;
    margin-top: 2px;
}

/* ── Floating Ask Button ──────────────────────────────── */
.ask-float-btn {
    position: fixed;
    bottom: 28px;
    right: 28px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: #0078d4;
    color: white;
    border: none;
    font-size: 24px;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(0,120,212,0.35), 0 2px 4px rgba(0,0,0,0.1);
    transition: all 0.2s ease;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
}

.ask-float-btn:hover {
    transform: scale(1.08);
    box-shadow: 0 6px 24px rgba(0,120,212,0.45), 0 3px 8px rgba(0,0,0,0.12);
}

/* ── Ask Panel ────────────────────────────────────────── */
.ask-panel {
    position: fixed;
    bottom: 96px;
    right: 28px;
    width: 400px;
    max-height: 500px;
    background: white;
    border: 1px solid #edebe9;
    border-radius: 12px;
    box-shadow: 0 16px 48px rgba(0,0,0,0.16);
    z-index: 9998;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.ask-panel-header {
    padding: 16px 20px;
    border-bottom: 1px solid #edebe9;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.ask-panel-header h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: #242424;
}

.ask-panel-body {
    padding: 16px 20px;
    flex: 1;
    overflow-y: auto;
}

.quick-chip {
    display: inline-block;
    padding: 6px 12px;
    border: 1px solid #d2d0ce;
    border-radius: 16px;
    font-size: 12px;
    color: #424242;
    cursor: pointer;
    margin: 0 4px 6px 0;
    transition: all 0.15s;
}

.quick-chip:hover {
    border-color: #0078d4;
    color: #0078d4;
    background: #eff6fc;
}

/* ── Expander overrides ───────────────────────────────── */
.streamlit-expanderHeader {
    font-weight: 500;
    font-size: 14px;
}

/* ── Tab styling ──────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background: transparent;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 6px 6px 0 0;
    padding: 8px 20px;
    font-size: 14px;
}

/* ── Manual override for multiselect to look cleaner ──── */
.stMultiSelect {
    font-size: 13px;
}

/* ── Input controls on gray bg ────────────────────────── */
.stTextInput > div > div,
.stTextArea > div > div,
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background-color: #ffffff !important;
    border-color: #edebe9 !important;
}

.stTextInput > div > div:focus-within,
.stTextArea > div > div:focus-within,
.stSelectbox > div > div:focus-within,
.stMultiSelect > div > div:focus-within {
    border-color: #0078d4 !important;
    box-shadow: 0 0 0 2px rgba(0,120,212,0.15) !important;
}

/* ── Timeline ─────────────────────────────────────────── */
.timeline-container {
    padding: 10px 0;
}

/* ── Settings form ────────────────────────────────────── */
.settings-card {
    background: #ffffff;
    border: 1px solid #edebe9;
    border-radius: 8px;
    padding: 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.settings-card h4 {
    font-size: 15px;
    font-weight: 600;
    color: #242424;
    margin-bottom: 16px;
}

/* ── Streamlit widget containers on gray bg ───────────── */
[data-testid="stExpander"] {
    background: #ffffff;
    border: 1px solid #edebe9;
    border-radius: 8px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

/* ── Scrollbar (global) ──────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d2d0ce; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #a19f9d; }

/* ── Timeline (Project Details) ──────────────────────── */
.sparrow-timeline {
    position: relative;
    padding-left: 36px;
}
.sparrow-timeline::before {
    content: '';
    position: absolute;
    left: 11px;
    top: 8px;
    bottom: 40px;
    width: 2px;
    background: linear-gradient(to bottom, #e1dfdd 0%, #e1dfdd 85%, transparent 100%);
    border-radius: 1px;
}
.tl-entry {
    position: relative;
    margin-bottom: 4px;
}
.tl-dot {
    position: absolute;
    left: -36px;
    top: 22px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2;
    transition: transform 0.2s ease;
}
.tl-entry:hover .tl-dot { transform: scale(1.15); }
.tl-dot-inner {
    width: 10px;
    height: 10px;
    border-radius: 50%;
}
.tl-dot.blue { background: rgba(0, 120, 212, 0.12); }
.tl-dot.blue .tl-dot-inner { background: #0078d4; }
.tl-dot.green { background: rgba(16, 124, 16, 0.12); }
.tl-dot.green .tl-dot-inner { background: #107c10; }
.tl-dot.purple { background: rgba(92, 45, 145, 0.12); }
.tl-dot.purple .tl-dot-inner { background: #5c2d91; }
.tl-dot.orange { background: rgba(247, 99, 12, 0.12); }
.tl-dot.orange .tl-dot-inner { background: #f7630c; }
.tl-card {
    background: #ffffff;
    border: 1px solid #edebe9;
    border-radius: 8px;
    padding: 16px 20px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.tl-entry:hover .tl-card {
    border-color: #d2d0ce;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.tl-card-header {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}
.tl-time {
    font-size: 12px;
    color: #616161;
    font-weight: 500;
    min-width: 80px;
}
.tl-source-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 10px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.2px;
}
.tl-source-badge.email { background: #e6f4e6; color: #107c10; }
.tl-source-badge.manual { background: #eff6fc; color: #0078d4; }
.tl-source-badge.system { background: #f0e6f6; color: #5c2d91; }
.tl-source-badge.teams { background: #fff4ec; color: #f7630c; }
.tl-author {
    font-size: 12px;
    color: #616161;
}
.tl-author strong { color: #242424; font-weight: 600; }
.tl-summary {
    font-size: 13.5px;
    color: #242424;
    margin-top: 8px;
    line-height: 1.55;
    font-weight: 500;
}
.tl-field-changes {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.tl-field-change {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    flex-wrap: wrap;
}
.tl-field-name {
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 11.5px;
    color: #616161;
    background: #f5f5f5;
    padding: 2px 8px;
    border-radius: 3px;
    font-weight: 500;
}
.tl-field-old {
    text-decoration: line-through;
    color: #a19f9d;
}
.tl-field-arrow {
    color: #c8c6c4;
    font-size: 14px;
}
.tl-field-new {
    color: #107c10;
    font-weight: 600;
}
.tl-source-text {
    background: #faf9f8;
    border-left: 3px solid #e1dfdd;
    padding: 12px 16px;
    border-radius: 0 6px 6px 0;
    font-size: 12.5px;
    color: #616161;
    line-height: 1.6;
    font-style: italic;
    margin-top: 12px;
}
.tl-source-label {
    font-size: 10.5px;
    color: #a19f9d;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
    margin-bottom: 6px;
    font-style: normal;
}
</style>
"""


def inject_theme():
    """Inject the full custom CSS into the Streamlit app."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_hero(total_projects: int, continents: int, countries: int, active: int):
    """Render the hero banner with wildlife SVG and overlay stats."""
    st.markdown(
        f'''<div class="hero-banner">
        {HERO_SVG}
        <div class="hero-overlay">
            <div class="hero-stat"><div class="num">{total_projects}</div><div class="lbl">Total Projects</div></div>
            <div class="hero-stat"><div class="num">{continents}</div><div class="lbl">Continents</div></div>
            <div class="hero-stat"><div class="num">{countries}</div><div class="lbl">Countries</div></div>
            <div class="hero-stat"><div class="num">{active}</div><div class="lbl">Active Deployments</div></div>
        </div>
        </div>''',
        unsafe_allow_html=True,
    )


def render_floating_ask():
    """Render the floating Ask button HTML. Actual logic is handled in app.py via session state."""
    st.markdown(
        '<div class="ask-float-btn" title="Ask SPARROW" onclick="alert(\'Use the Ask SPARROW panel in the sidebar\')">💬</div>',
        unsafe_allow_html=True,
    )

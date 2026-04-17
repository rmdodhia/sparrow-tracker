#!/usr/bin/env python3
"""
Seed dev-track projects and their phases from the FY26-27 roadmap.

Creates a handful of `item_type='dev_track'` projects (Water SPARROW,
Robin, SPARROW Studio, Weather SPARROW, Pi SPARROW, CONDOR) with phases
spanning the months shown in SPARROW_BACKLOG_OF_PRIORITIES.xlsx.

Idempotent: safe to re-run. Uses track_name as the natural key.

Run: python3 seed_dev_tracks.py
"""

import os
import sys
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(__file__))

from db import init_db, get_conn


# ── Dev tracks and their phases (hand-transcribed from the xlsx roadmap) ─────

DEV_TRACKS = [
    {
        "project_id": "DEV-WATER-SPARROW",
        "track_name": "Water SPARROW",
        "notes": "Underwater acoustic monitoring platform. Puget Sound + NOAA Sound deployments in FY26.",
        "start_date": "2025-11-01",
        "target_date": "2026-06-30",
        "phases": [
            {"key": "Dev",        "name": "Water SPARROW Development",  "start": "2025-11-01", "end": "2026-04-30", "status": "In Progress"},
            {"key": "Testing",    "name": "Testing",                    "start": "2026-04-01", "end": "2026-05-31", "status": "Planned"},
            {"key": "Rollout",    "name": "Puget Sound Deployment",     "start": "2026-05-01", "end": "2026-06-30", "status": "Planned"},
        ],
    },
    {
        "project_id": "DEV-ROBIN",
        "track_name": "Robin",
        "notes": "Bioacoustic Raspberry Pi sensor. Many downstream deployments are waiting on Robin readiness.",
        "start_date": "2025-08-01",
        "target_date": "2026-12-31",
        "phases": [
            {"key": "Dev",        "name": "Robin Dev + Testing",        "start": "2025-08-01", "end": "2026-02-28", "status": "In Progress"},
            {"key": "Manual",     "name": "Robin Installation Manual",  "start": "2026-03-01", "end": "2026-04-30", "status": "Planned"},
            {"key": "OpenSource", "name": "Robin Open Sourcing",        "start": "2026-08-01", "end": "2026-10-31", "status": "Planned"},
            {"key": "Testing",    "name": "Testing",                    "start": "2026-11-01", "end": "2026-11-30", "status": "Planned"},
            {"key": "Launch",     "name": "Robin Launch",               "start": "2026-12-01", "end": "2026-12-31", "status": "Planned"},
        ],
    },
    {
        "project_id": "DEV-SPARROW-STUDIO",
        "track_name": "SPARROW Studio",
        "notes": "Desktop client for Sparrow/PyTorch solution. DevOps Epic 502065.",
        "start_date": "2025-09-01",
        "target_date": "2026-07-31",
        "devops_id": 502065,
        "phases": [
            {"key": "Dev",        "name": "PyTorch Desktop Client",     "start": "2025-09-01", "end": "2025-09-30", "status": "Done"},
            {"key": "Dev",        "name": "SPARROW STUDIO Development", "start": "2025-11-01", "end": "2026-03-31", "status": "In Progress"},
            {"key": "Launch",     "name": "SPARROW STUDIO Launch",      "start": "2026-06-01", "end": "2026-06-30", "status": "Planned"},
            {"key": "Rollout",    "name": "MAC & Linux Version",        "start": "2026-07-01", "end": "2026-07-31", "status": "Planned"},
        ],
    },
    {
        "project_id": "DEV-PI-SPARROW",
        "track_name": "Pi SPARROW",
        "notes": "Raspberry-Pi based SPARROW variant. Sub-track of SPARROW platform.",
        "start_date": "2025-11-01",
        "target_date": "2026-07-31",
        "parent_project_id": None,
        "phases": [
            {"key": "Dev",        "name": "Pi SPARROW Development",     "start": "2025-11-01", "end": "2026-04-30", "status": "In Progress"},
            {"key": "Manual",     "name": "Pi SPARROW Manual",          "start": "2026-05-01", "end": "2026-05-31", "status": "Planned"},
            {"key": "Launch",     "name": "Pi SPARROW Launch",          "start": "2026-07-01", "end": "2026-07-31", "status": "Planned"},
        ],
    },
    {
        "project_id": "DEV-WEATHER-SPARROW",
        "track_name": "Weather SPARROW",
        "notes": "Weather-monitoring sensor variant. Later in the roadmap.",
        "start_date": "2026-06-01",
        "target_date": "2026-12-31",
        "phases": [
            {"key": "Dev",        "name": "Weather SPARROW Development","start": "2026-06-01", "end": "2026-10-31", "status": "Planned"},
            {"key": "Testing",    "name": "Sensor integration & testing","start": "2026-11-01", "end": "2026-12-31", "status": "Planned"},
        ],
    },
    {
        "project_id": "DEV-CONDOR",
        "track_name": "CONDOR",
        "notes": "Fire detection and localization pipeline. AlertCalifornia integration.",
        "start_date": "2025-08-01",
        "target_date": "2026-04-30",
        "phases": [
            {"key": "Dev",        "name": "Data Annotation",            "start": "2025-08-01", "end": "2025-09-30", "status": "Done"},
            {"key": "Dev",        "name": "Fire Triangulation v1",      "start": "2025-08-01", "end": "2025-10-31", "status": "Done"},
            {"key": "Dev",        "name": "Online Inference",           "start": "2025-10-01", "end": "2025-11-30", "status": "In Progress"},
            {"key": "Dev",        "name": "Fire Localization",          "start": "2026-04-01", "end": "2026-04-30", "status": "Planned"},
            {"key": "Dev",        "name": "Archive Data Pipeline",      "start": "2026-04-01", "end": "2026-04-30", "status": "Planned"},
        ],
    },
]


# ── Cross-project dependencies to demonstrate the arrows ────────────────────
#
# Each entry describes: "this downstream phase is blocked by this upstream phase".
# upstream is identified by (project_id, phase_name_contains) so we match
# flexibly; downstream is (project_id, phase_name_contains). The seeder
# resolves both to phase IDs after insert.
DEPENDENCIES = [
    # Robin launch gates several deployments that explicitly say "waiting on Robin".
    {"upstream": ("DEV-ROBIN", "Robin Launch"),
     "downstream": ("AS-IDN-INDO", None)},                # Indonesia — Waiting for Robin
    {"upstream": ("DEV-ROBIN", "Robin Launch"),
     "downstream": ("EU-GRL-GREE", None)},                # Greenland
    {"upstream": ("DEV-ROBIN", "Robin Launch"),
     "downstream": ("EU-UK-UKNO", None)},                 # UK - North England
    {"upstream": ("DEV-ROBIN", "Robin Launch"),
     "downstream": ("EU-SCO-SCOT", None)},                # Scotland

    # Water SPARROW development gates the Puget Sound deployment + Antarctica.
    {"upstream": ("DEV-WATER-SPARROW", "Water SPARROW Development"),
     "downstream": ("NA-USA-PUGE", None)},                # Puget Sound
    {"upstream": ("DEV-WATER-SPARROW", "Water SPARROW Development"),
     "downstream": ("AN-ANT-CHIL", None)},                # Antarctica Chile Base

    # Pi SPARROW Manual gates Colombia Humboldt (waiting on Pi SPARROW docs).
    {"upstream": ("DEV-PI-SPARROW", "Pi SPARROW Manual"),
     "downstream": ("SA-COL-COLO3", None)},               # Humboldt
]


def _find_phase_id(conn, project_id, phase_name_contains=None):
    if phase_name_contains:
        row = conn.execute(
            "SELECT id FROM phases WHERE project_id = ? AND name LIKE ? ORDER BY ordering LIMIT 1",
            (project_id, f"%{phase_name_contains}%"),
        ).fetchone()
    else:
        # For deployments with one backfilled phase, just take the first one.
        row = conn.execute(
            "SELECT id FROM phases WHERE project_id = ? ORDER BY ordering LIMIT 1",
            (project_id,),
        ).fetchone()
    return row[0] if row else None


def seed_dependencies():
    """Link downstream phases to their upstream blockers. Idempotent."""
    wired = 0
    with get_conn() as conn:
        for dep in DEPENDENCIES:
            up_pid, up_name = dep["upstream"]
            down_pid, down_name = dep["downstream"]
            up_id = _find_phase_id(conn, up_pid, up_name)
            down_id = _find_phase_id(conn, down_pid, down_name)
            if not up_id or not down_id:
                print(f"  ! skip {up_pid}→{down_pid}: phase not found (up={up_id}, down={down_id})")
                continue
            conn.execute(
                "UPDATE phases SET depends_on_phase_id = ? WHERE id = ?",
                (up_id, down_id),
            )
            wired += 1
            print(f"  ↳ {up_pid} phase #{up_id} → {down_pid} phase #{down_id}")
    print(f"\nWired {wired} dependencies.")


def seed_dev_tracks():
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        for track in DEV_TRACKS:
            existing = conn.execute(
                "SELECT project_id FROM projects WHERE project_id = ?",
                (track["project_id"],),
            ).fetchone()

            if not existing:
                conn.execute(
                    """INSERT INTO projects
                       (project_id, item_type, track_name, status, start_date, target_date,
                        devops_id, notes, last_updated, last_updated_by, continent, country, location)
                       VALUES (?, 'dev_track', ?, 'Active - Waiting on Us', ?, ?, ?, ?, ?, 'seed', '', '', '')""",
                    (
                        track["project_id"],
                        track["track_name"],
                        track["start_date"],
                        track["target_date"],
                        track.get("devops_id"),
                        track["notes"],
                        now,
                    ),
                )
                print(f"  + created dev track {track['project_id']} ({track['track_name']})")
            else:
                print(f"  = dev track {track['project_id']} exists — leaving project row alone")

            # Wipe + re-seed phases for this track so the seed is idempotent
            conn.execute("DELETE FROM phases WHERE project_id = ?", (track["project_id"],))
            for i, ph in enumerate(track["phases"]):
                conn.execute(
                    """INSERT INTO phases
                       (project_id, phase_key, name, ordering, start_date, end_date, status, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (track["project_id"], ph["key"], ph["name"], i,
                     ph["start"], ph["end"], ph["status"], now),
                )
            print(f"    → {len(track['phases'])} phases")

    print(f"\nSeeded {len(DEV_TRACKS)} dev tracks.")


if __name__ == "__main__":
    seed_dev_tracks()
    print()
    seed_dependencies()

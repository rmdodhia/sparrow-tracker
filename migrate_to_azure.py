"""
Migrate data from SQLite (sparrow_tracker.db) to Azure SQL.

Usage:
  1. Fill in your Azure SQL credentials in .env
  2. Run: python migrate_to_azure.py

This script:
  - Creates tables in Azure SQL (via init_db)
  - Reads all data from the local SQLite database
  - Inserts it into Azure SQL
  - Skips rows that already exist (idempotent)
"""

import json
import sqlite3
import sys

from config import DB_PATH
from db import init_db, get_conn, _execute, _fetchone


def get_sqlite_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_table(sqlite_conn, azure_conn, table, id_col="id", identity=True):
    """Copy all rows from a SQLite table to Azure SQL."""
    rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        print(f"  {table}: 0 rows (empty)")
        return

    cols = rows[0].keys()

    if identity and id_col in cols:
        # Enable identity insert so we preserve original IDs
        _execute(azure_conn, f"SET IDENTITY_INSERT {table} ON")

    inserted = 0
    skipped = 0
    for row in rows:
        vals = [row[c] for c in cols]
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)

        # Check if row already exists
        if id_col in cols:
            existing = _fetchone(azure_conn,
                f"SELECT {id_col} FROM {table} WHERE {id_col} = ?",
                (row[id_col],))
            if existing:
                skipped += 1
                continue

        try:
            _execute(azure_conn,
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                vals)
            inserted += 1
        except Exception as e:
            print(f"  WARNING: {table} row {row[id_col] if id_col in cols else '?'}: {e}")
            skipped += 1

    if identity and id_col in cols:
        _execute(azure_conn, f"SET IDENTITY_INSERT {table} OFF")

    print(f"  {table}: {inserted} inserted, {skipped} skipped")


def main():
    print("=== SPARROW Tracker: SQLite → Azure SQL Migration ===\n")

    # Step 1: Create schema in Azure SQL
    print("1. Creating tables in Azure SQL...")
    try:
        init_db()
        print("   Done.\n")
    except Exception as e:
        print(f"   ERROR connecting to Azure SQL: {e}")
        print("   Check your .env credentials (AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USER, AZURE_SQL_PASSWORD)")
        sys.exit(1)

    # Step 2: Open both connections
    print("2. Opening SQLite database...")
    sqlite_conn = get_sqlite_conn()
    print(f"   Opened: {DB_PATH}\n")

    print("3. Migrating data...\n")
    with get_conn() as azure_conn:
        # Migrate in dependency order (projects first, then tables that reference it)
        migrate_table(sqlite_conn, azure_conn, "projects", id_col="project_id", identity=False)
        migrate_table(sqlite_conn, azure_conn, "history", id_col="id", identity=True)
        migrate_table(sqlite_conn, azure_conn, "contacts", id_col="id", identity=True)
        migrate_table(sqlite_conn, azure_conn, "raw_inputs", id_col="id", identity=True)
        migrate_table(sqlite_conn, azure_conn, "nudges", id_col="id", identity=True)
        migrate_table(sqlite_conn, azure_conn, "phases", id_col="id", identity=True)

        # devops_work_items uses a non-identity PK
        migrate_table(sqlite_conn, azure_conn, "devops_work_items", id_col="id", identity=False)

    sqlite_conn.close()
    print("\n=== Migration complete! ===")
    print("Your Flask app will now use Azure SQL. Run: flask run --debug")


if __name__ == "__main__":
    main()

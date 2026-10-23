#!/usr/bin/env python3
"""
Verify that the SQL dump has been restored into Postgres.

Checks:
- Row counts for all tables under schemas: automation, client, clientcontacts, legalbot, server
- Presence of key functions, views, extensions, domain, triggers, and indexes

Uses DSN from .env (DATABASE, POSTGRES_DSN, DATABASE_URL).
"""
from __future__ import annotations
import os
import sys
from typing import Dict, List, Tuple


SCHEMAS = ["automation", "client", "clientcontacts", "legalbot", "server"]


def load_env_value(keys: List[str]) -> str | None:
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ.setdefault(k, v)
        except Exception:
            pass
    for k in keys:
        v = os.getenv(k)
        if v and v.strip():
            return v.strip()
    return None


def main(argv: List[str]) -> int:
    dsn = load_env_value(["DATABASE", "POSTGRES_DSN", "DATABASE_URL"]) or ""
    if not dsn:
        print("❌ No Postgres DSN found in .env (DATABASE/POSTGRES_DSN/DATABASE_URL)")
        return 2

    try:
        import psycopg2  # type: ignore
    except Exception:
        print("❌ psycopg2 not installed. Activate myenv and run: pip install psycopg2-binary")
        return 3

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    print("== Schema Table Row Counts ==")
    totals_by_schema: Dict[str, int] = {s: 0 for s in SCHEMAS}
    table_counts: List[Tuple[str, str, int]] = []
    for sch in SCHEMAS:
        cur.execute(
            """
            select tablename
            from pg_tables
            where schemaname = %s
            order by tablename
            """,
            (sch,),
        )
        tables = [r[0] for r in cur.fetchall()]
        for tbl in tables:
            q = f"select count(*) from {sch}.{tbl}"
            try:
                cur.execute(q)
                cnt = cur.fetchone()[0]
            except Exception as e:
                cnt = -1
            table_counts.append((sch, tbl, cnt))
            if cnt >= 0:
                totals_by_schema[sch] += cnt

    # Print concise summary first
    for sch in SCHEMAS:
        cur.execute(
            "select count(*) from pg_tables where schemaname=%s",
            (sch,),
        )
        tcount = cur.fetchone()[0]
        print(f"- {sch}: tables={tcount}, total_rows={totals_by_schema[sch]}")

    # Print per-table counts (short, one per line)
    print("\n== Per Table Counts ==")
    for sch, tbl, cnt in table_counts:
        print(f"{sch}.{tbl}: {cnt}")

    # Object checks
    print("\n== Object Checks ==")
    # Functions
    funs = [
        ("automation", "update_updated_at_column"),
        ("legalbot", "tg_touch_updated_at"),
        ("legalbot", "tg_phases_outbox"),
    ]
    for ns, fn in funs:
        cur.execute(
            "select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname=%s and p.proname=%s",
            (ns, fn),
        )
        ok = bool(cur.fetchone())
        print(f"function {ns}.{fn}: {'OK' if ok else 'MISSING'}")

    # Views
    views = ["legalbot.vw_data_dictionary", "legalbot.vw_phases_leaf"]
    for v in views:
        cur.execute("select to_regclass(%s)", (v,))
        ok = bool(cur.fetchone()[0])
        print(f"view {v}: {'OK' if ok else 'MISSING'}")

    # Extensions
    for ext in ("citext", "pg_trgm"):
        cur.execute("select 1 from pg_extension where extname=%s", (ext,))
        ok = bool(cur.fetchone())
        print(f"extension {ext}: {'OK' if ok else 'MISSING'}")

    # Domain
    cur.execute(
        """
        select 1 from pg_type t
        join pg_namespace n on n.oid=t.typnamespace
        where n.nspname='legalbot' and t.typname='citext'
        """
    )
    print(f"domain legalbot.citext: {'OK' if cur.fetchone() else 'MISSING'}")

    # Indexes/Triggers on slot_kv (optional table)
    cur.execute("select to_regclass('legalbot.slot_kv')")
    if cur.fetchone()[0]:
        # trigger
        cur.execute(
            """
            select 1 from pg_trigger t
            join pg_class c on c.oid=t.tgrelid
            join pg_namespace n on n.oid=c.relnamespace
            where n.nspname='legalbot' and c.relname='slot_kv' and t.tgname='trg_slotkv_upd'
            """
        )
        print(f"trigger legalbot.trg_slotkv_upd: {'OK' if cur.fetchone() else 'MISSING'}")
        # index
        cur.execute(
            """
            select 1 from pg_class i
            join pg_namespace n on n.oid=i.relnamespace
            where n.nspname='legalbot' and i.relname='ix_slotkv_field_value'
            """
        )
        print(f"index legalbot.ix_slotkv_field_value: {'OK' if cur.fetchone() else 'MISSING'}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


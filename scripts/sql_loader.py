#!/usr/bin/env python3
"""
Robust Postgres SQL dump loader.

- Uses DATABASE DSN from .env by default (fallback: POSTGRES_DSN, DATABASE_URL).
- Skips unsafe/psql-only commands (DROP/CREATE DATABASE, \connect).
- Creates schemas/types/tables, then loads data.
- Appends ON CONFLICT DO NOTHING to INSERT ... VALUES (...) to avoid duplicate errors.
- Temporarily disables triggers via session_replication_role during data inserts (if permitted).
  This bypasses FK checks/triggers to avoid ordering issues; constraints are added later by the dump.
 - Executes each statement independently and continues on benign errors (already exists, duplicates).

Note: Designed for plain SQL dumps produced by pg_dump. COPY FROM STDIN blocks are not
      expected in this dump; basic support is included if present.
"""
from __future__ import annotations

import os
import re
import sys
import io
import time
from typing import Optional, Tuple


def load_env_value(keys: list[str]) -> Optional[str]:
    """Load first non-empty value among keys from environment or .env file in repo root.

    Minimal .env parser to avoid external deps.
    """
    # Load .env once if not loaded yet
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line or line.strip().startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        # keep original env var if already set
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            # best-effort; ignore
            pass

    for k in keys:
        v = os.getenv(k)
        if v and v.strip():
            return v.strip()
    return None


def get_connection(dsn: Optional[str] = None):
    """Return a (conn, flavor) where flavor is 'psycopg2' or 'psycopg'.

    Tries psycopg (v3) first, then psycopg2.
    """
    last_err = None
    if dsn is None:
        dsn = load_env_value(["DATABASE", "POSTGRES_DSN", "DATABASE_URL"]) or ""
    if not dsn:
        raise RuntimeError("No Postgres DSN found. Set DATABASE in .env or pass --dsn.")

    # psycopg (v3)
    try:
        import psycopg  # type: ignore

        conn = psycopg.connect(dsn, autocommit=True)
        return conn, "psycopg"
    except Exception as e:
        last_err = e

    # psycopg2
    try:
        import psycopg2  # type: ignore

        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        return conn, "psycopg2"
    except Exception as e2:
        if last_err:
            raise RuntimeError(
                f"Failed to import/connect psycopg and psycopg2. Errors: {last_err} | {e2}\n"
                f"Please `pip install psycopg[binary]` or `psycopg2-binary` in your env."
            )
        raise


class SQLStreamParser:
    """Simple SQL splitter handling quotes and dollar-quoted bodies.

    For this dump we don't expect COPY FROM STDIN blocks, but the splitter
    is robust for multi-line statements with semicolons inside $$...$$ or quotes.
    """

    def __init__(self):
        pass

    def split(self, content: str) -> list[str]:
        s = content
        # Drop psql meta lines like \connect ...
        s = re.sub(r"^\\\S.*$", "", s, flags=re.M)
        # Normalize newlines
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        # Remove SQL comments to avoid splitting on semicolons inside them
        s = re.sub(r"(?m)^\s*--.*?$", "", s)
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
        out: list[str] = []
        i = 0
        n = len(s)
        start = 0
        in_single = False
        in_double = False
        in_dollar: Optional[str] = None

        while i < n:
            ch = s[i]
            if in_dollar:
                token = in_dollar
                if s.startswith(token, i):
                    in_dollar = None
                    i += len(token)
                    continue
                i += 1
                continue
            if ch == "'" and not in_double:
                # toggle single quote unless it's an escaped '' pair
                if in_single and i + 1 < n and s[i + 1] == "'":
                    i += 2
                    continue
                in_single = not in_single
                i += 1
                continue
            if ch == '"' and not in_single:
                in_double = not in_double
                i += 1
                continue
            if not in_single and not in_double:
                # detect $tag$
                m = re.match(r"\$([A-Za-z0-9_]*)\$", s[i:])
                if m:
                    in_dollar = m.group(0)
                    i += len(in_dollar)
                    continue
                if ch == ";":
                    stmt = s[start : i + 1].strip()
                    if stmt:
                        out.append(stmt)
                    start = i + 1
            i += 1
        # tail
        tail = s[start:].strip()
        if tail:
            out.append(tail)
        return out


def benign_sql_error(err_msg: str, sqlstate: Optional[str]) -> bool:
    """Return True if error is safe to ignore and continue."""
    em = (err_msg or "").lower()
    # Common duplicate/exists codes
    if sqlstate in {"23505", "42P06", "42P07", "42710"}:  # unique_violation, duplicate_schema/table/object
        return True
    # Cannot drop current DB, role exists, etc. -> skip
    if "cannot drop the currently open database" in em:
        return True
    if "already exists" in em:
        return True
    if "does not exist" in em and ("drop" in em or "owned by" in em):
        return True
    if "must be owner of" in em:
        return True
    # Re-applying PK constraints after inline PKs were created
    if "multiple primary keys for table" in em:
        return True
    # Extensions missing can be acceptable for load (e.g., vector)
    if "could not access file" in em and "extension" in em:
        return True
    return False


def _strip_leading_comments(stmt: str) -> str:
    s = stmt.lstrip()
    # Remove any leading -- comment lines
    out = []
    i = 0
    n = len(s)
    while True:
        # strip whitespace
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i >= n:
            return ""
        if s.startswith("--", i):
            # skip to end of line
            j = s.find("\n", i)
            if j == -1:
                return ""
            i = j + 1
            continue
        if s.startswith("/*", i):
            j = s.find("*/", i + 2)
            if j == -1:
                return ""  # unclosed, treat as empty
            i = j + 2
            continue
        # not a comment
        break
    return s[i:]


def should_skip_statement(stmt: str) -> bool:
    base = _strip_leading_comments(stmt).strip()
    sl = base.lower()
    # Skip DB-level and psql meta regardless of leading comments
    if "drop database" in sl:
        return True
    if "create database" in sl:
        return True
    if base.startswith("\\"):
        return True
    # Keep SET/COMMENT statements (generally harmless)
    return False


def maybe_rewrite_insert(stmt: str) -> str:
    """Append ON CONFLICT DO NOTHING to INSERT ... VALUES (...) if not already present."""
    # Only handle simple VALUES form; leave INSERT ... SELECT unchanged
    m = re.match(r"(?is)^\s*INSERT\s+INTO\s+.+?\s+VALUES\s*\(.*\)\s*;\s*$", stmt)
    if not m:
        return stmt
    if re.search(r"(?is)\bON\s+CONFLICT\b", stmt):
        return stmt
    # inject before the trailing semicolon
    return stmt[:-1] + " ON CONFLICT DO NOTHING;"


def resplit_statements(block: str) -> list[Tuple[str, str]]:
    """Split a possibly multi-statement block into individual statements/COPY items.

    Returns a list of (kind, text) where kind is 'STMT' or 'COPY'.
    """
    p = SQLStreamParser()
    out: list[Tuple[str, str]] = []
    for line in block.splitlines(keepends=True):
        res = p.feed_line(line)
        if not res:
            continue
        if res[0] == "STMT":
            out.append(("STMT", res[1]))
        elif res[0] == "COPY":
            out.append(("COPY", res[1] + "\n" + res[2]))
    return out


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load a plain SQL dump into Postgres robustly")
    parser.add_argument("--file", "-f", default=os.path.join("oldTool", "全备份-postgres-202507082022.sql"), help="Path to SQL file")
    parser.add_argument("--dsn", "-d", default=None, help="Postgres DSN. Defaults to DATABASE/POSTGRES_DSN in .env")
    parser.add_argument("--no-on-conflict", action="store_true", help="Do not add ON CONFLICT DO NOTHING to INSERTs")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args(argv)

    sql_path = args.file
    if not os.path.exists(sql_path):
        print(f"❌ SQL file not found: {sql_path}")
        return 1

    try:
        conn, flavor = get_connection(args.dsn)
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return 2

    print(f"✅ Connected to Postgres via {flavor}")
    cur = conn.cursor()

    # basic preflight
    try:
        try:
            cur.execute("select current_user, current_database(), version();")
            row = cur.fetchone()
            print(f"👤 User={row[0]} | 📦 DB={row[1]}")
            print(f"🧩 {row[2].splitlines()[0]}")
        except Exception:
            pass

        # Set UTF-8 and sane timeouts
        for s in (
            "SET client_encoding = 'UTF8';",
            "SET standard_conforming_strings = on;",
            "SET statement_timeout = 0;",
            "SET lock_timeout = 0;",
            "SET idle_in_transaction_session_timeout = 0;",
        ):
            try:
                cur.execute(s)
            except Exception:
                pass
    except Exception:
        pass

    # Pre-create extensions/domains that the dump expects but might be missing
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS citext;")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        # Ensure target schemas exist before domain creation
        cur.execute("CREATE SCHEMA IF NOT EXISTS legalbot;")
        cur.execute("CREATE DOMAIN IF NOT EXISTS legalbot.citext AS citext;")
    except Exception:
        # Best-effort; continue if not available
        pass

    parser_state = SQLStreamParser()
    total = 0
    applied = 0
    skipped = 0
    errors = 0
    data_mode_enabled = False
    last_progress = time.time()

    def enable_replica():
        nonlocal data_mode_enabled
        if data_mode_enabled:
            return
        try:
            cur.execute("SET session_replication_role = 'replica';")
            data_mode_enabled = True
            if args.verbose:
                print("🔧 Disabled triggers (session_replication_role=replica)")
        except Exception as e:
            if args.verbose:
                print(f"ℹ️ Could not set replication_role=replica (need superuser): {e}")

    def disable_replica():
        nonlocal data_mode_enabled
        if not data_mode_enabled:
            return
        try:
            cur.execute("SET session_replication_role = 'origin';")
            data_mode_enabled = False
            if args.verbose:
                print("🔧 Restored triggers (session_replication_role=origin)")
        except Exception:
            pass

    # Parse and classify all statements first
    pre_ddl: list[str] = []
    data_inserts: list[str] = []
    data_copies: list[Tuple[str, str]] = []
    post_constraints: list[str] = []
    post_sequences: list[str] = []
    post_indexes: list[str] = []
    post_triggers: list[str] = []
    others: list[str] = []

    def classify(stmt: str) -> str:
        s = _strip_leading_comments(stmt).strip()
        sl = s.lower()
        if should_skip_statement(s):
            return "skip"
        if sl.startswith("set ") or sl.startswith("comment "):
            return "pre"
        if sl.startswith("create schema"):
            return "pre"
        if sl.startswith("create type") or sl.startswith("create domain"):
            return "pre"
        if sl.startswith("create sequence") or sl.startswith("alter sequence"):
            return "pre"
        if sl.startswith("create table"):
            return "pre"
        if sl.startswith("create function") or sl.startswith("create procedure"):
            return "pre"
        if sl.startswith("create view"):
            return "pre"
        if sl.startswith("alter table"):
            if " add constraint " in sl:
                return "post_constraints"
            # identity/sequence defaults also belong to pre
            return "pre"
        if sl.startswith("create index"):
            return "post_indexes"
        if sl.startswith("create trigger"):
            return "post_triggers"
        if sl.startswith("insert into"):
            return "data"
        if sl.startswith("copy "):
            return "copy"
        if sl.startswith("select pg_catalog.setval") or sl.startswith("select setval"):
            return "post_sequences"
        return "other"

    with open(sql_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    statements = parser_state.split(content)
    total = len(statements)
    for stmt in statements:
        cat = classify(stmt)
        if cat == "skip":
            skipped += 1
            continue
        if cat == "pre":
            pre_ddl.append(stmt)
        elif cat == "data":
            data_inserts.append(stmt)
        elif cat == "post_constraints":
            post_constraints.append(stmt)
        elif cat == "post_sequences":
            post_sequences.append(stmt)
        elif cat == "post_indexes":
            post_indexes.append(stmt)
        elif cat == "post_triggers":
            post_triggers.append(stmt)
        elif cat == "copy":
            # Not expected in this dump; kept for completeness
            data_copies.append((stmt, ""))
        else:
            others.append(stmt)

    if args.verbose:
        print(f"Parsed: pre={len(pre_ddl)}, inserts={len(data_inserts)}, constraints={len(post_constraints)}, setvals={len(post_sequences)}, copies={len(data_copies)}, others={len(others)}, skipped={skipped}")

    # Execute pre-DDL
    for s in pre_ddl:
        try:
            cur.execute(s)
            applied += 1
        except Exception as e:
            sqlstate = getattr(e, "pgcode", None) or getattr(getattr(e, "sqlstate", None), "value", None)
            if benign_sql_error(str(e), sqlstate) or ("unrecognized configuration parameter" in str(e).lower()):
                skipped += 1
                if args.verbose:
                    print(f"⚠️  benign error, skipping: {e}\n   SQL: {s[:200]}…")
                continue
            errors += 1
            print(f"❌ Error executing pre-DDL: {e}")
            if args.verbose:
                print(s)

    # Fallback: ensure special objects that some dumps assume
    try:
        # Ensure citext and legalbot.citext domain
        cur.execute("CREATE EXTENSION IF NOT EXISTS citext;")
        cur.execute("CREATE SCHEMA IF NOT EXISTS legalbot;")
        cur.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='legalbot' AND t.typname='citext') THEN EXECUTE 'CREATE DOMAIN legalbot.citext AS citext'; END IF; END $$;")
        # Ensure pg_trgm availability
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        # Ensure legalbot.slot_kv exists if missed earlier
        cur.execute("SELECT to_regclass('legalbot.slot_kv')")
        if not cur.fetchone()[0]:
            cur.execute(
                """
                CREATE TABLE legalbot.slot_kv (
                    conv_id bigint NOT NULL,
                    phase text DEFAULT 'all'::text NOT NULL,
                    field_name character varying(64) NOT NULL,
                    field_value legalbot.citext,
                    attempts smallint DEFAULT 0,
                    updated_at timestamp with time zone DEFAULT now(),
                    branch text DEFAULT 'all'::text NOT NULL
                );
                """
            )
            if args.verbose:
                print("⚠️  created missing table legalbot.slot_kv (fallback)")
    except Exception as e:
        if args.verbose:
            print(f"⚠️  fallback ensure objects error: {e}")

    # Execute data inserts/copies with triggers disabled
    enable_replica()
    for ins in data_inserts:
        stmt = ins
        if not args.no_on_conflict:
            stmt = maybe_rewrite_insert(stmt)
        try:
            cur.execute(stmt)
            applied += 1
        except Exception as e:
            sqlstate = getattr(e, "pgcode", None) or getattr(getattr(e, "sqlstate", None), "value", None)
            if benign_sql_error(str(e), sqlstate):
                skipped += 1
                if args.verbose:
                    print(f"⚠️  benign error, skipping: {e}\n   SQL: {stmt[:200]}…")
                continue
            errors += 1
            print(f"❌ Error executing INSERT: {e}")
            if args.verbose:
                print(stmt)

    for copy_sql, copy_data in data_copies:
        try:
            try:
                import psycopg2  # type: ignore
                with io.StringIO(copy_data) as sio:
                    cur.copy_expert(copy_sql, file=sio)
            except Exception:
                # psycopg3 path
                cur.copy(copy_sql, source=io.StringIO(copy_data))  # type: ignore[attr-defined]
            applied += 1
        except Exception as e:
            sqlstate = getattr(e, "pgcode", None)
            if benign_sql_error(str(e), sqlstate):
                skipped += 1
                continue
            errors += 1
            print(f"❌ Error executing COPY: {e}")

    disable_replica()

    # Apply constraints, indexes, triggers and sequence setvals
    for s in post_constraints:
        try:
            cur.execute(s)
            applied += 1
        except Exception as e:
            sqlstate = getattr(e, "pgcode", None)
            if benign_sql_error(str(e), sqlstate):
                skipped += 1
                continue
            errors += 1
            print(f"❌ Error applying constraint: {e}")
            if args.verbose:
                print(s)

    # Rewrites for index opclasses if needed
    def rewrite_index(stmt: str) -> str:
        # map legalbot.gin_trgm_ops -> gin_trgm_ops to avoid schema-coupled extension install
        return re.sub(r"\blegalbot\.gin_trgm_ops\b", "gin_trgm_ops", stmt)

    for s in post_indexes:
        stmt = rewrite_index(s)
        try:
            cur.execute(stmt)
            applied += 1
        except Exception as e:
            sqlstate = getattr(e, "pgcode", None)
            if benign_sql_error(str(e), sqlstate):
                skipped += 1
                continue
            errors += 1
            print(f"❌ Error creating index: {e}")
            if args.verbose:
                print(stmt)

    for s in post_triggers:
        try:
            cur.execute(s)
            applied += 1
        except Exception as e:
            sqlstate = getattr(e, "pgcode", None)
            if benign_sql_error(str(e), sqlstate):
                skipped += 1
                continue
            errors += 1
            print(f"❌ Error creating trigger: {e}")
            if args.verbose:
                print(s)

    for s in post_sequences:
        try:
            cur.execute(s)
            applied += 1
        except Exception as e:
            sqlstate = getattr(e, "pgcode", None)
            if benign_sql_error(str(e), sqlstate):
                skipped += 1
                continue
            errors += 1
            print(f"❌ Error applying setval: {e}")
            if args.verbose:
                print(s)

    print(f"\n✅ Done. Statements: total={total}, applied={applied}, skipped={skipped}, errors={errors}")
    if errors:
        print("Some statements failed. Review logs above; core data should still be loaded.")
    return 0 if errors == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""
oracle_to_pg_sync.py
====================

Copies data from an Oracle CURATED schema into a PostgreSQL curated schema
(upsert on keys), and syncs sequences from the Oracle STAGING schema into
the PostgreSQL staging schema (create-if-missing + setval to Oracle's
current value).

Designed for medium-large tables (1M-50M rows):
  Oracle (batched fetch) -> COPY into a PG TEMP table -> single set-based
  upsert (INSERT ... ON CONFLICT when a matching unique constraint exists,
  otherwise DELETE USING + INSERT) -> ANALYZE.

Keys are auto-detected from Oracle metadata (primary key first, then the
first unique constraint) and can be overridden per table via --key.

Requirements:
    pip install oracledb psycopg2-binary
    (optional) pip install python-dotenv   # to load a .env file

Environment variables (or .env in the working directory):
    ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN      e.g. host:1521/ORCLPDB1
    PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD
    ORACLE_CURATED_SCHEMA   (default: CURATED)
    PG_CURATED_SCHEMA       (default: curated)
    ORACLE_STAGING_SCHEMA   (default: STAGING)
    PG_STAGING_SCHEMA       (default: staging)

Usage examples:
    # Full sync: all curated tables + staging sequences
    python oracle_to_pg_sync.py

    # Only some tables, with a manual key override for one of them
    python oracle_to_pg_sync.py --tables DIM_ACCOUNT,FCT_PAYMENT_ORDER \
        --key FCT_PAYMENT_ORDER=ORDER_ID,BOOKING_DATE

    # Sequences only
    python oracle_to_pg_sync.py --only sequences

    # See the plan (tables, keys, row counts, sequences) without writing
    python oracle_to_pg_sync.py --dry-run
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import oracledb
import psycopg2
import psycopg2.extensions

log = logging.getLogger("ora2pg")

PG_BIGINT_MAX = 2**63 - 1
PG_BIGINT_MIN = -(2**63)

# Fetch CLOB/BLOB as str/bytes directly and NUMBER as Decimal (no float
# precision loss). Both are parse-time-safe module settings.
oracledb.defaults.fetch_lobs = False
oracledb.defaults.fetch_decimals = True


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

@dataclass
class Config:
    ora_user: str
    ora_password: str
    ora_dsn: str
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    ora_curated: str
    pg_curated: str
    ora_staging: str
    pg_staging: str
    batch_size: int = 50_000
    include_tables: list[str] = field(default_factory=list)
    exclude_tables: list[str] = field(default_factory=list)
    key_overrides: dict[str, list[str]] = field(default_factory=dict)
    only: str = "all"              # all | tables | sequences
    create_missing: bool = False
    no_key_mode: str = "skip"      # skip | truncate | append
    dry_run: bool = False


def load_config(args: argparse.Namespace) -> Config:

    key_overrides: dict[str, list[str]] = {}
    for spec in args.key or []:
        if "=" not in spec:
            log.error("Bad --key spec %r, expected TABLE=col1,col2", spec)
            sys.exit(2)
        table, cols = spec.split("=", 1)
        key_overrides[table.strip().upper()] = [
            c.strip().upper() for c in cols.split(",") if c.strip()
        ]

    return Config(
        ora_user="CURATED",
        ora_password="NSout9h3rTqB38rm1",
        ora_dsn="10.109.94.6:1521/DATAPLAT_DATAPLATSIT.paas.oracle.com",
        pg_host="localhost",
        pg_port=5432,
        pg_database="postgres",
        pg_user="postgres",
        pg_password="postgres",
        ora_curated=(args.ora_curated or "CURATED").upper(),
        pg_curated=(args.pg_curated or "curated").lower(),
        ora_staging=(args.ora_staging or "STAGING").upper(),
        pg_staging=(args.pg_staging or "staging").lower(),
        batch_size=args.batch_size,
        include_tables=[t.strip().upper() for t in (args.tables or "").split(",") if t.strip()],
        exclude_tables=[t.strip().upper() for t in (args.exclude or "").split(",") if t.strip()],
        key_overrides=key_overrides,
        only=args.only,
        create_missing=args.create_missing,
        no_key_mode=args.no_key_mode,
        dry_run=args.dry_run,
    )


# --------------------------------------------------------------------------
# Identifier helpers
# --------------------------------------------------------------------------

def q_ora(name: str) -> str:
    """Quote an Oracle identifier (kept uppercase)."""
    return '"' + name.upper().replace('"', '""') + '"'


def q_pg(name: str) -> str:
    """Quote a Postgres identifier, folded to lowercase."""
    return '"' + name.lower().replace('"', '""') + '"'


# --------------------------------------------------------------------------
# Oracle metadata
# --------------------------------------------------------------------------

def ora_list_tables(ora, owner: str) -> list[str]:
    with ora.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
              FROM all_tables
             WHERE owner = :owner
               AND (iot_type IS NULL OR iot_type != 'IOT_OVERFLOW')
               AND nested = 'NO'
               AND (dropped IS NULL OR dropped = 'NO')
             ORDER BY table_name
            """,
            owner=owner,
        )
        return [r[0] for r in cur.fetchall()]


def ora_table_columns(ora, owner: str, table: str) -> list[dict]:
    """Real (non-hidden, non-virtual) columns, in column_id order."""
    with ora.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, data_precision, data_scale,
                   char_length, nullable
              FROM all_tab_cols
             WHERE owner = :owner
               AND table_name = :tab
               AND hidden_column = 'NO'
               AND virtual_column = 'NO'
             ORDER BY column_id
            """,
            owner=owner, tab=table,
        )
        return [
            dict(name=r[0], data_type=r[1], precision=r[2], scale=r[3],
                 char_length=r[4], nullable=(r[5] == "Y"))
            for r in cur.fetchall()
        ]


def ora_table_keys(ora, owner: str, table: str) -> list[str]:
    """Primary key columns; falls back to the first unique constraint."""
    sql = """
        SELECT cons.constraint_name, cols.column_name
          FROM all_constraints cons
          JOIN all_cons_columns cols
            ON cols.owner = cons.owner
           AND cols.constraint_name = cons.constraint_name
         WHERE cons.owner = :owner
           AND cons.table_name = :tab
           AND cons.constraint_type = :ctype
           AND cons.status = 'ENABLED'
         ORDER BY cons.constraint_name, cols.position
    """
    with ora.cursor() as cur:
        for ctype in ("P", "U"):
            cur.execute(sql, owner=owner, tab=table, ctype=ctype)
            rows = cur.fetchall()
            if rows:
                first = rows[0][0]
                return [c for (name, c) in rows if name == first]
    return []


def ora_table_count(ora, owner: str, table: str) -> int:
    with ora.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {q_ora(owner)}.{q_ora(table)}")
        return int(cur.fetchone()[0])


def ora_list_sequences(ora, owner: str) -> list[dict]:
    with ora.cursor() as cur:
        cur.execute(
            """
            SELECT sequence_name, last_number, increment_by,
                   min_value, max_value, cycle_flag, cache_size
              FROM all_sequences
             WHERE sequence_owner = :owner
             ORDER BY sequence_name
            """,
            owner=owner,
        )
        return [
            dict(name=r[0], last_number=int(r[1]), increment_by=int(r[2]),
                 min_value=int(r[3]), max_value=int(r[4]),
                 cycle=(r[5] == "Y"), cache=int(r[6]))
            for r in cur.fetchall()
        ]

# --------------------------------------------------------------------------
# Postgres metadata
# --------------------------------------------------------------------------

def pg_table_exists(pg, schema: str, table: str) -> bool:
    with pg.cursor() as cur:
        cur.execute(
            "SELECT to_regclass(%s) IS NOT NULL",
            (f'"{schema}"."{table.lower()}"',),
        )
        return cur.fetchone()[0]


def pg_table_columns(pg, schema: str, table: str) -> list[str]:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = %s AND table_name = %s
             ORDER BY ordinal_position
            """,
            (schema, table.lower()),
        )
        return [r[0] for r in cur.fetchall()]


def pg_unique_constraint_matches(pg, schema: str, table: str,
                                 key_cols: list[str]) -> bool:
    """True if the PG table has a PK/UNIQUE constraint on exactly key_cols."""
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT array_agg(kcu.column_name ORDER BY kcu.ordinal_position)
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON kcu.constraint_name = tc.constraint_name
               AND kcu.table_schema = tc.table_schema
               AND kcu.table_name = tc.table_name
             WHERE tc.table_schema = %s
               AND tc.table_name = %s
               AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
             GROUP BY tc.constraint_name
            """,
            (schema, table.lower()),
        )
        want = {c.lower() for c in key_cols}
        return any(set(row[0]) == want for row in cur.fetchall())


# --------------------------------------------------------------------------
# Oracle -> Postgres type mapping (only used with --create-missing)
# --------------------------------------------------------------------------

def map_type(col: dict) -> str:
    dt = col["data_type"].upper()
    p, s, clen = col["precision"], col["scale"], col["char_length"]

    if dt == "NUMBER":
        if p is None:
            return "numeric"
        if s in (None, 0):
            if p <= 4:
                return "smallint"
            if p <= 9:
                return "integer"
            if p <= 18:
                return "bigint"
            return f"numeric({p})"
        return f"numeric({p},{s})"
    if dt in ("VARCHAR2", "NVARCHAR2"):
        return f"varchar({clen})" if clen else "text"
    if dt in ("CHAR", "NCHAR"):
        return f"char({clen})" if clen else "char(1)"
    if dt in ("CLOB", "NCLOB", "LONG", "XMLTYPE"):
        return "text"
    if dt in ("BLOB", "RAW", "LONG RAW"):
        return "bytea"
    if dt == "DATE":
        return "timestamp"          # Oracle DATE carries a time component
    if dt.startswith("TIMESTAMP"):
        return "timestamptz" if "TIME ZONE" in dt else "timestamp"
    if dt == "BINARY_FLOAT":
        return "real"
    if dt in ("BINARY_DOUBLE", "FLOAT"):
        return "double precision"
    log.warning("Unmapped Oracle type %s (column %s) -> text", dt, col["name"])
    return "text"


def create_pg_table(pg, schema: str, table: str,
                    columns: list[dict], keys: list[str]) -> None:
    col_defs = []
    for col in columns:
        null_sql = "" if col["nullable"] else " NOT NULL"
        col_defs.append(f'    {q_pg(col["name"])} {map_type(col)}{null_sql}')
    ddl = (f'CREATE TABLE {q_pg(schema)}.{q_pg(table)} (\n'
           + ",\n".join(col_defs))
    if keys:
        ddl += ",\n    PRIMARY KEY (" + ", ".join(q_pg(k) for k in keys) + ")"
    ddl += "\n)"
    log.info("Creating missing table %s.%s", schema, table.lower())
    log.debug("%s", ddl)
    with pg.cursor() as cur:
        cur.execute(ddl)


# --------------------------------------------------------------------------
# COPY streaming: Oracle cursor -> COPY text format
# --------------------------------------------------------------------------

def _fmt_value(v) -> str:
    r"""Render one value in COPY text format (tab-separated, \N for NULL)."""
    if v is None:
        return r"\N"
    if isinstance(v, bool):
        return "t" if v else "f"
    if isinstance(v, (int, Decimal, float)):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        s = r"\x" + bytes(v).hex()          # bytea hex input
    else:
        s = str(v)
    return (s.replace("\\", "\\\\")
             .replace("\t", "\\t")
             .replace("\n", "\\n")
             .replace("\r", "\\r"))


class _CursorCopyFile(io.TextIOBase):
    """File-like adapter streaming an Oracle cursor as COPY text lines."""

    def __init__(self, cursor, batch_size: int, table: str):
        self._cur = cursor
        self._batch = batch_size
        self._table = table
        self._buf = ""
        self._done = False
        self.rows = 0
        self._t0 = time.monotonic()

    def readable(self) -> bool:
        return True

    def _fill(self) -> None:
        rows = self._cur.fetchmany(self._batch)
        if not rows:
            self._done = True
            return
        parts = []
        for row in rows:
            parts.append("\t".join(_fmt_value(v) for v in row))
            parts.append("\n")
        self._buf += "".join(parts)
        self.rows += len(rows)
        rate = self.rows / max(time.monotonic() - self._t0, 1e-6)
        log.info("  %s: %s rows streamed (%.0f rows/s)",
                 self._table, f"{self.rows:,}", rate)

    def read(self, n: int = -1) -> str:
        while not self._done and (n < 0 or len(self._buf) < n):
            self._fill()
        if n < 0:
            out, self._buf = self._buf, ""
        else:
            out, self._buf = self._buf[:n], self._buf[n:]
        return out

# --------------------------------------------------------------------------
# Table sync (upsert)
# --------------------------------------------------------------------------

def sync_table(ora, pg, cfg: Config, table: str) -> None:
    ora_cols = ora_table_columns(ora, cfg.ora_curated, table)
    if not ora_cols:
        log.warning("SKIP %s: no columns found in Oracle", table)
        return

    keys = cfg.key_overrides.get(table) or ora_table_keys(ora, cfg.ora_curated, table)
    pg_table = table.lower()

    # Target table existence / creation
    if not pg_table_exists(pg, cfg.pg_curated, table):
        if cfg.create_missing:
            create_pg_table(pg, cfg.pg_curated, table, ora_cols, keys)
            pg.commit()
        else:
            log.error("SKIP %s: %s.%s does not exist in Postgres "
                      "(use --create-missing to create it)",
                      table, cfg.pg_curated, pg_table)
            return

    # Column intersection (Oracle order preserved)
    pg_cols = set(pg_table_columns(pg, cfg.pg_curated, table))
    common = [c["name"] for c in ora_cols if c["name"].lower() in pg_cols]
    missing_in_pg = [c["name"] for c in ora_cols if c["name"].lower() not in pg_cols]
    if missing_in_pg:
        log.warning("%s: columns present in Oracle but not in PG "
                    "(will not be copied): %s", table, ", ".join(missing_in_pg))
    if not common:
        log.error("SKIP %s: no common columns between Oracle and PG", table)
        return

    # Key handling
    mode = "upsert"
    if keys and not all(k.lower() in pg_cols for k in keys):
        log.warning("%s: key columns %s missing in PG, treating as no-key",
                    table, keys)
        keys = []
    if not keys:
        mode = cfg.no_key_mode
        if mode == "skip":
            log.error("SKIP %s: no PK/unique key found in Oracle and no --key "
                      "override (use --no-key-mode truncate|append to load anyway)",
                      table)
            return
        log.warning("%s: no key found, falling back to %s", table, mode)

    tgt = f"{q_pg(cfg.pg_curated)}.{q_pg(table)}"
    col_list_pg = ", ".join(q_pg(c) for c in common)
    col_list_ora = ", ".join(q_ora(c) for c in common)
    key_list = ", ".join(q_pg(k) for k in keys) if keys else ""

    log.info("Syncing %s.%s -> %s.%s [%s%s]",
             cfg.ora_curated, table, cfg.pg_curated, pg_table, mode,
             f" on ({', '.join(k.lower() for k in keys)})" if keys else "")

    ora_cur = ora.cursor()
    ora_cur.arraysize = cfg.batch_size
    ora_cur.prefetchrows = cfg.batch_size + 1
    ora_cur.execute(
        f"SELECT {col_list_ora} FROM {q_ora(cfg.ora_curated)}.{q_ora(table)}"
    )

    t0 = time.monotonic()
    with pg.cursor() as cur:
        cur.execute("SET LOCAL synchronous_commit TO OFF")
        cur.execute(
            f"CREATE TEMP TABLE _ora_sync (LIKE {tgt} INCLUDING DEFAULTS) "
            f"ON COMMIT DROP"
        )
        stream = _CursorCopyFile(ora_cur, cfg.batch_size, pg_table)
        cur.copy_expert(
            f"COPY _ora_sync ({col_list_pg}) FROM STDIN", stream, size=1 << 20
        )
        n_rows = stream.rows

        if mode == "truncate":
            cur.execute(f"TRUNCATE {tgt}")
            cur.execute(f"INSERT INTO {tgt} ({col_list_pg}) "
                        f"SELECT {col_list_pg} FROM _ora_sync")
        elif mode == "append":
            cur.execute(f"INSERT INTO {tgt} ({col_list_pg}) "
                        f"SELECT {col_list_pg} FROM _ora_sync")
        elif pg_unique_constraint_matches(pg, cfg.pg_curated, table, keys):
            non_keys = [c for c in common
                        if c.lower() not in {k.lower() for k in keys}]
            action = ("DO UPDATE SET "
                      + ", ".join(f"{q_pg(c)} = EXCLUDED.{q_pg(c)}"
                                  for c in non_keys)
                      if non_keys else "DO NOTHING")
            cur.execute(
                f"INSERT INTO {tgt} ({col_list_pg}) "
                f"SELECT DISTINCT ON ({key_list}) {col_list_pg} "
                f"FROM _ora_sync ORDER BY {key_list} "
                f"ON CONFLICT ({key_list}) {action}"
            )
        else:
            # No matching unique constraint in PG: delete + insert
            log.info("  %s: no matching PG unique constraint on (%s), "
                     "using delete+insert", pg_table,
                     ", ".join(k.lower() for k in keys))
            join = " AND ".join(
                f"t.{q_pg(k)} IS NOT DISTINCT FROM s.{q_pg(k)}" for k in keys
            )
            cur.execute(f"DELETE FROM {tgt} t USING _ora_sync s WHERE {join}")
            cur.execute(
                f"INSERT INTO {tgt} ({col_list_pg}) "
                f"SELECT DISTINCT ON ({key_list}) {col_list_pg} "
                f"FROM _ora_sync ORDER BY {key_list}"
            )
    pg.commit()
    ora_cur.close()

    with pg.cursor() as cur:
        cur.execute(f"ANALYZE {tgt}")
    pg.commit()

    log.info("DONE %s: %s rows in %.1fs", pg_table, f"{n_rows:,}",
             time.monotonic() - t0)


# --------------------------------------------------------------------------
# Sequence sync
# --------------------------------------------------------------------------

def sync_sequences(ora, pg, cfg: Config) -> None:
    seqs = ora_list_sequences(ora, cfg.ora_staging)
    if not seqs:
        log.warning("No sequences found in Oracle schema %s", cfg.ora_staging)
        return
    log.info("Syncing %d sequences %s -> %s",
             len(seqs), cfg.ora_staging, cfg.pg_staging)

    with pg.cursor() as cur:
        for s in seqs:
            name = f"{q_pg(cfg.pg_staging)}.{q_pg(s['name'])}"
            minv = max(s["min_value"], PG_BIGINT_MIN)
            maxv = min(s["max_value"], PG_BIGINT_MAX)
            # Oracle LAST_NUMBER is the next value not yet written to disk
            # (it runs ahead by the cache), so setval(..., true) here means
            # PG's nextval starts strictly above anything Oracle handed out.
            cur_val = min(max(s["last_number"], minv), maxv)
            if cfg.dry_run:
                log.info("  [dry-run] %s -> setval %s", name, f"{cur_val:,}")
                continue
            cur.execute(
                f"CREATE SEQUENCE IF NOT EXISTS {name} "
                f"INCREMENT BY {s['increment_by']} "
                f"MINVALUE {minv} MAXVALUE {maxv} "
                f"{'CYCLE' if s['cycle'] else 'NO CYCLE'} "
                f"CACHE {max(s['cache'], 1)}"
            )
            cur.execute("SELECT setval(%s::regclass, %s, true)",
                        (name, cur_val))
            log.info("  %s -> %s", name, f"{cur_val:,}")
    pg.commit()


# --------------------------------------------------------------------------
# Planning / main
# --------------------------------------------------------------------------

def select_tables(ora, cfg: Config) -> list[str]:
    tables = ora_list_tables(ora, cfg.ora_curated)
    if cfg.include_tables:
        wanted = set(cfg.include_tables)
        missing = wanted - set(tables)
        if missing:
            log.error("Tables not found in Oracle %s: %s",
                      cfg.ora_curated, ", ".join(sorted(missing)))
            sys.exit(2)
        tables = [t for t in tables if t in wanted]
    if cfg.exclude_tables:
        tables = [t for t in tables if t not in set(cfg.exclude_tables)]
    return tables


def dry_run_report(ora, pg, cfg: Config, tables: list[str]) -> None:
    log.info("---- DRY RUN: table plan ----")
    for t in tables:
        keys = cfg.key_overrides.get(t) or ora_table_keys(ora, cfg.ora_curated, t)
        exists = pg_table_exists(pg, cfg.pg_curated, t)
        count = ora_table_count(ora, cfg.ora_curated, t)
        log.info("  %-32s rows=%12s key=%-30s pg_exists=%s",
                 t, f"{count:,}",
                 ",".join(keys) if keys else "(none)", exists)
    log.info("---- DRY RUN: sequences ----")
    sync_sequences(ora, pg, cfg)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sync Oracle curated schema data (upsert) and staging "
                    "sequences into PostgreSQL.")
    p.add_argument("--tables", help="Comma-separated Oracle table names to include")
    p.add_argument("--exclude", help="Comma-separated Oracle table names to skip")
    p.add_argument("--key", action="append", metavar="TABLE=COL1,COL2",
                   help="Override upsert key for a table (repeatable)")
    p.add_argument("--only", choices=["all", "tables", "sequences"], default="all")
    p.add_argument("--batch-size", type=int, default=50_000,
                   help="Oracle fetch batch size (default 50000)")
    p.add_argument("--create-missing", action="store_true",
                   help="Create missing PG tables from Oracle metadata")
    p.add_argument("--no-key-mode", choices=["skip", "truncate", "append"],
                   default="skip",
                   help="What to do when a table has no usable key (default skip)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan without writing anything")
    p.add_argument("--ora-curated", help="Override Oracle curated schema name")
    p.add_argument("--pg-curated", help="Override PG curated schema name")
    p.add_argument("--ora-staging", help="Override Oracle staging schema name")
    p.add_argument("--pg-staging", help="Override PG staging schema name")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_config(args)

    log.info("Connecting to Oracle (%s) ...", cfg.ora_dsn)
    ora = oracledb.connect(user=cfg.ora_user, password=cfg.ora_password,
                           dsn=cfg.ora_dsn)
    log.info("Connecting to Postgres (%s:%s/%s) ...",
             cfg.pg_host, cfg.pg_port, cfg.pg_database)
    pg = psycopg2.connect(host=cfg.pg_host, port=cfg.pg_port,
                          dbname=cfg.pg_database, user=cfg.pg_user,
                          password=cfg.pg_password)

    failures: list[str] = []
    try:
        tables = select_tables(ora, cfg) if cfg.only != "sequences" else []

        if cfg.dry_run:
            dry_run_report(ora, pg, cfg, tables)
            return 0

        for t in tables:
            try:
                sync_table(ora, pg, cfg, t)
            except Exception:
                pg.rollback()
                log.exception("FAILED %s", t)
                failures.append(t)

        if cfg.only in ("all", "sequences"):
            sync_sequences(ora, pg, cfg)
    finally:
        ora.close()
        pg.close()

    if failures:
        log.error("Completed with %d failed table(s): %s",
                  len(failures), ", ".join(failures))
        return 1
    log.info("All done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
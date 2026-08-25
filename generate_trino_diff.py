#!/usr/bin/env python3
"""
generate_trino_diff.py
======================
Dynamically generates a Trino SQL query that performs a column-level diff
between <source_catalog>.<schema>.<table> and <target_catalog>.<schema>.<table>.

Connection defaults: localhost:8080, user=admin, no password.

Usage Examples
--------------
# Minimal (auto-detects schema between 'curated' and 'rdm', default catalogs 'postgres' and 'oracle')
python generate_trino_diff.py --table-name fct_product_financial_transactions --id-column transaction_id

# Dynamic Catalogs
python generate_trino_diff.py --table-name ref_t24_sector --source-catalog postgres --target-catalog oracle --id-column sector_code

# Explicit schema
python generate_trino_diff.py --table-name ref_t24_sector --schema rdm --id-column sector_code

# Schema-prefixed table name
python generate_trino_diff.py --table-name rdm.ref_t24_sector --id-column sector_code

# Composite key
python generate_trino_diff.py --table-name fct_ledger --id-column transaction_id --id-column company_code

# With options
python generate_trino_diff.py \
    --table-name fct_product_financial_transactions \
    --id-column transaction_id \
    --exclude-columns as_of_date,extraction_timestamp,date_time \
    --exclude-suffix key \
    --trim-strings \
    --verbose \
    --output diff_query.sql
"""

import argparse
import sys
import os
from concurrent.futures import ThreadPoolExecutor

# ---------------------------------------------------------------------------
# Optional Trino client import
# ---------------------------------------------------------------------------
try:
    import trino
except ImportError:
    trino = None  # handled at runtime when connection is needed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRINO_HOST = "localhost"
TRINO_PORT = 8080
TRINO_USER = "admin"
DEFAULT_SOURCE_CATALOG = "postgres"
DEFAULT_TARGET_CATALOG = "oracle"
DEFAULT_SCHEMAS = ["curated", "rdm"]
ROW_FIELD_HARD_LIMIT    = 32   # Trino ROW() connector field cap
ROW_FIELD_LIMIT_WARNING = 28   # warn with headroom before the hard limit

# Trino reserved keywords that must be double-quoted when used as identifiers
TRINO_RESERVED_KEYWORDS = {
    "date", "time", "timestamp", "value", "values", "key", "comment",
    "end", "start", "begin", "order", "group", "table", "column",
    "current", "type", "year", "month", "day", "hour", "minute", "second",
    "zone", "true", "false", "null", "select", "from", "where", "join",
    "inner", "outer", "left", "right", "full", "cross", "on", "as",
    "and", "or", "not", "in", "exists", "between", "like", "is",
    "distinct", "all", "union", "intersect", "except", "case", "when",
    "then", "else", "cast", "row", "array", "map", "with", "insert",
    "update", "delete", "drop", "create", "alter", "set", "show",
    "describe", "explain", "use", "limit", "offset", "fetch", "next",
    "rows", "only", "over", "partition", "by", "having", "into",
    "format", "natural", "position", "filter", "within",
}

# Data types that require precision normalisation warning
NUMERIC_TYPES = {"decimal", "numeric", "double", "real", "float"}
DATE_TYPES = {
    "date", "timestamp", "timestamp with time zone",
    "timestamp without time zone", "time", "time with time zone",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def quote(col: str) -> str:
    """Return double-quoted identifier if the name is a reserved keyword
    or contains special characters, otherwise return as-is.
    Corner Case #10: reserved SQL keywords as column names.
    """
    if col.lower() in TRINO_RESERVED_KEYWORDS or not col.replace("_", "").isalnum():
        return f'"{col}"'
    return col


def get_trino_connection():
    """Create and return a Trino DBAPI connection."""
    if trino is None:
        print(
            "[ERROR] The 'trino' Python package is not installed.\n"
            "        Install it with:  pip install trino",
            file=sys.stderr,
        )
        sys.exit(1)
    return trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        http_scheme="http",
    )


def fetch_columns(
    cursor,
    catalog: str,
    table_name: str,
    schema: str = None,
    exclude_cols: list = None,
    exclude_suffix: str = None,
    id_columns: list = None,
) -> tuple:
    """
    Fetch column metadata (name + data_type) from information_schema in a single roundtrip,
    filtering out excluded column names and suffixes early at metadata retrieval time.
    If schema is not specified, tries DEFAULT_SCHEMAS ('curated', 'rdm') in precedence order.
    Returns a tuple: (schema_found, [{'name': str, 'data_type': str}, ...])
    """
    id_set = {ic.strip().lower() for ic in (id_columns or []) if ic and ic.strip()}
    excluded_set = {c.strip().lower() for c in (exclude_cols or []) if c and c.strip()}
    suf_lower = exclude_suffix.strip().lower() if exclude_suffix and exclude_suffix.strip() else None

    def _filter_cols(raw_cols):
        if not excluded_set and not suf_lower:
            return raw_cols
        filtered = []
        for c in raw_cols:
            cname = c["name"].lower()
            # Always preserve designated ID / Business key columns
            if cname in id_set:
                filtered.append(c)
                continue
            if cname in excluded_set:
                continue
            if suf_lower and cname.endswith(suf_lower):
                continue
            filtered.append(c)
        return filtered

    if schema:
        sql = (
            "SELECT column_name, data_type "
            f"FROM {catalog}.information_schema.columns "
            f"WHERE table_schema = '{schema}' "
            f"  AND table_name   = '{table_name}' "
            "ORDER BY ordinal_position"
        )
        cursor.execute(sql)
        rows = cursor.fetchall()
        if rows:
            cols = [{"name": row[0], "data_type": row[1].lower()} for row in rows]
            return schema, _filter_cols(cols)
        return schema, []

    schemas_in = ", ".join(f"'{s}'" for s in DEFAULT_SCHEMAS)
    sql = (
        "SELECT table_schema, column_name, data_type "
        f"FROM {catalog}.information_schema.columns "
        f"WHERE table_schema IN ({schemas_in}) "
        f"  AND table_name = '{table_name}' "
        "ORDER BY ordinal_position"
    )
    cursor.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        return DEFAULT_SCHEMAS[0], []

    by_schema = {}
    for r in rows:
        sch_name, col_name, dt = r[0], r[1], r[2].lower()
        by_schema.setdefault(sch_name, []).append({"name": col_name, "data_type": dt})

    for sch in DEFAULT_SCHEMAS:
        if sch in by_schema:
            return sch, _filter_cols(by_schema[sch])

    first_found = next(iter(by_schema))
    return first_found, _filter_cols(by_schema[first_found])


# ---------------------------------------------------------------------------
# Gap / Warning Analysis
# ---------------------------------------------------------------------------

def print_gap_report(pg_cols: list, ora_cols: list, id_columns: list):
    """Print schema divergence between Postgres and Oracle.
    Corner Case #6: surface columns unique to one catalog.
    """
    pg_names = {c["name"] for c in pg_cols}
    ora_names = {c["name"] for c in ora_cols}
    id_col_set = set(id_columns)

    only_pg = pg_names - ora_names - id_col_set
    only_ora = ora_names - pg_names - id_col_set

    print("\n" + "=" * 70)
    print("SCHEMA GAP REPORT")
    print("=" * 70)

    if only_pg:
        print(f"\n[GAP] Columns ONLY in Postgres ({len(only_pg)}) — excluded from diff:")
        for col in sorted(only_pg):
            print(f"       - {col}")
    else:
        print("\n[OK]  No columns exclusive to Postgres.")

    if only_ora:
        print(f"\n[GAP] Columns ONLY in Oracle ({len(only_ora)}) — excluded from diff:")
        for col in sorted(only_ora):
            print(f"       - {col}")
    else:
        print("\n[OK]  No columns exclusive to Oracle.")

    print("=" * 70 + "\n")


def warn_type_issues(common_col_meta: list):
    """Emit warnings for columns whose types may cause false mismatches.
    Corner Cases #8 (numeric) and #9 (date/timestamp).
    """
    numeric_cols = [c["name"] for c in common_col_meta if c["data_type"] in NUMERIC_TYPES]
    date_cols = [c["name"] for c in common_col_meta if c["data_type"] in DATE_TYPES]

    if numeric_cols:
        print("[WARN] Numeric columns detected — CAST to VARCHAR may differ in precision.")
        print("       Consider using CAST(CAST(col AS DECIMAL(38,10)) AS VARCHAR) manually.")
        print(f"       Affected: {', '.join(numeric_cols)}\n")

    if date_cols:
        print("[INFO] Date/Timestamp columns detected — normalised via CAST(col AS TIMESTAMP(0)) for consistent formatting.")
        print(f"       Affected: {', '.join(date_cols)}\n")


# ---------------------------------------------------------------------------
# Query Builders: Direct & Iceberg-Staged Pipelines
# ---------------------------------------------------------------------------

def build_cast_expr(col: str, data_type: str, trim: bool, table_alias: str = "") -> str:
    """Build a standard CAST expression for a column."""
    qcol = quote(col)
    tbl = f"{table_alias}." if table_alias else ""
    if "timestamp" in data_type or data_type == "date":
        expr = f"CAST(CAST({tbl}{qcol} AS TIMESTAMP(0)) AS VARCHAR)"
    else:
        expr = f"CAST({tbl}{qcol} AS VARCHAR)"
    if trim:
        expr = f"TRIM({expr})"
    return expr


def build_cast(alias: str, col: str, data_type: str, trim: bool) -> str:
    """Build a single CAST expression with prefix alias (p_/o_)."""
    prefix = alias[0]  # 'p' or 'o'
    cast_expr = build_cast_expr(col, data_type, trim, table_alias=alias)
    return f"{cast_expr} AS {prefix}_{col}"


def check_prefix_collision(cols: list) -> None:
    """Detect alias collisions caused by p_/o_ prefixing.
    Corner Case #1.
    """
    aliases = set()
    for col in cols:
        for prefix in ("p_", "o_"):
            alias = f"{prefix}{col}"
            if alias in aliases:
                print(
                    f"[ERROR] Alias collision detected: '{alias}' would be generated "
                    f"more than once. Rename the conflicting column before proceeding.",
                    file=sys.stderr,
                )
                sys.exit(1)
            aliases.add(alias)

    # Warn if any column name itself starts with p_ or o_ and its unprefixed
    # sibling is also in the column list
    col_set = set(cols)
    for col in cols:
        if f"p_{col}" in col_set or f"o_{col}" in col_set:
            print(
                f"[WARN] Column '{col}' may produce alias collision with another "
                f"column named 'p_{col}' or 'o_{col}'. "
                f"Review generated aliases carefully.",
                file=sys.stderr,
            )


def build_direct_query(
    table_name: str,
    id_columns: list,
    common_col_meta: list,
    exclude_cols: list,
    exclude_suffix,
    trim_strings: bool,
    pg_schema: str = "curated",
    ora_schema: str = "curated",
    source_catalog: str = "postgres",
    target_catalog: str = "oracle",
) -> str:
    """Assemble the monolithic Trino diff query (Single-pass FULL OUTER JOIN)."""
    common_cols = [c["name"] for c in common_col_meta]

    # ---- JOIN conditions (supports composite keys) ----
    join_parts = "\n        AND ".join(
        f"p.{quote(ic)} = o.{quote(ic)}" for ic in id_columns
    )

    # ---- COALESCE for each id column ----
    coalesce_parts = ",\n        ".join(
        f"COALESCE(p.{quote(ic)}, o.{quote(ic)}) AS {ic}" for ic in id_columns
    )

    # ---- row_diff_type CASE ----
    ic0 = id_columns[0]
    diff_case = (
        f"CASE\n"
        f"            WHEN p.{quote(ic0)} IS NULL THEN 'ONLY_IN_TARGET'\n"
        f"            WHEN o.{quote(ic0)} IS NULL THEN 'ONLY_IN_SOURCE'\n"
        f"            ELSE 'VALUE_MISMATCH'\n"
        f"        END AS row_diff_type"
    )
    null_where_p = f"p.{quote(ic0)} IS NULL"
    null_where_o = f"o.{quote(ic0)} IS NULL"

    # ---- Source + Target SELECT casts ----
    p_cast_lines = ["        " + build_cast("p", c["name"], c["data_type"], trim_strings) + "," for c in common_col_meta]
    o_cast_lines = ["        " + build_cast("o", c["name"], c["data_type"], trim_strings) + "," for c in common_col_meta]
    if p_cast_lines:
        p_cast_lines[-1] = p_cast_lines[-1].rstrip(",")
    if o_cast_lines:
        o_cast_lines[-1] = o_cast_lines[-1].rstrip(",")
    p_casts = "\n".join(p_cast_lines)
    o_casts = "\n".join(o_cast_lines)

    # ---- ROW() comparison — identical ordering on both sides ----
    p_row_cols = ", ".join(f"p.{quote(c)}" for c in common_cols)
    o_row_cols = ", ".join(f"o.{quote(c)}" for c in common_cols)

    # ---- UNNEST arrays — must match common_cols order exactly ----
    col_name_array = ",\n            ".join(f"'{c}'" for c in common_cols)
    p_val_array = ",\n            ".join(f"d.p_{c}" for c in common_cols)
    o_val_array = ",\n            ".join(f"d.o_{c}" for c in common_cols)

    # ---- WHERE clause extra conditions for VALUE_MISMATCH branch ----
    mismatch_extra_conds = []
    if exclude_cols:
        quoted_list = ", ".join(f"'{c.strip().lower()}'" for c in exclude_cols)
        mismatch_extra_conds.append(f"AND lower(u.column_name) NOT IN ({quoted_list})")
    if exclude_suffix:
        mismatch_extra_conds.append(f"AND lower(u.column_name) NOT LIKE '%{exclude_suffix.strip().lower()}'")
    mismatch_extra_conditions = (
        "\n        " + "\n        ".join(mismatch_extra_conds)
    ) if mismatch_extra_conds else ""

    sentinel_col = common_cols[0]
    id_select = ",\n        ".join(f"d.{ic}" for ic in id_columns)

    query = f"""\
WITH diff_data AS (
    SELECT
        {coalesce_parts},
        {diff_case},

        -- Source values cast to VARCHAR for uniform unpivoting
{p_casts},

        -- Target values cast to VARCHAR for uniform unpivoting
{o_casts}
    FROM {source_catalog}.{pg_schema}.{table_name} p
    FULL OUTER JOIN {target_catalog}.{ora_schema}.{table_name} o
        ON {join_parts}
    WHERE (
        {null_where_p}
        OR {null_where_o}
        OR ROW({p_row_cols})
           IS DISTINCT FROM
           ROW({o_row_cols})
    )
)
SELECT
    {id_select},
    d.row_diff_type,
    CASE WHEN d.row_diff_type = 'VALUE_MISMATCH' THEN u.column_name    ELSE CAST(NULL AS VARCHAR) END AS column_name,
    CASE WHEN d.row_diff_type = 'VALUE_MISMATCH' THEN u.postgres_value ELSE CAST(NULL AS VARCHAR) END AS postgres_value,
    CASE WHEN d.row_diff_type = 'VALUE_MISMATCH' THEN u.oracle_value   ELSE CAST(NULL AS VARCHAR) END AS oracle_value
FROM diff_data d
CROSS JOIN UNNEST(
    ARRAY[
        {col_name_array}
    ],
    ARRAY[
        {p_val_array}
    ],
    ARRAY[
        {o_val_array}
    ]
) AS u(column_name, postgres_value, oracle_value)
WHERE
    (
        d.row_diff_type = 'VALUE_MISMATCH'
        AND u.postgres_value IS DISTINCT FROM u.oracle_value{mismatch_extra_conditions}
    )
    OR (
        d.row_diff_type IN ('ONLY_IN_TARGET', 'ONLY_IN_SOURCE')
        AND u.column_name = '{sentinel_col}'
    )
"""
    return query


# Alias for backward compatibility
build_query = build_direct_query


# ---------------------------------------------------------------------------
# Iceberg Staged Execution Pipeline Builders
# ---------------------------------------------------------------------------

def build_iceberg_stage_table_names(table_name: str, run_id: str) -> tuple:
    """Generate unique temporary table names for Iceberg staging."""
    clean_tbl = table_name.replace(".", "_")
    clean_run = run_id.replace("-", "_").replace(".", "_")
    src_temp = f"tmp_src_{clean_tbl}_{clean_run}"
    tgt_temp = f"tmp_tgt_{clean_tbl}_{clean_run}"
    mismatch_temp = f"tmp_mismatch_{clean_tbl}_{clean_run}"
    return src_temp, tgt_temp, mismatch_temp


def build_iceberg_stage1_ctas(
    catalog: str,
    schema: str,
    table_name: str,
    id_columns: list,
    common_col_meta: list,
    trim_strings: bool,
    iceberg_catalog: str,
    iceberg_schema: str,
    target_temp_table: str,
) -> str:
    """Generate CTAS statement to ingest source or target into an Iceberg staging table with row hash.
    
    Optimizations:
    1. Single-pass CTE ensures CAST and TRIM expressions are evaluated only once per column.
    2. xxhash64 row checksum references the pre-casted CTE columns directly with COALESCE.
    3. sorted_by table property on ID columns enables Parquet row-group min/max statistics for pruning.
    """
    id_select = ",\n        ".join(f"{quote(ic)}" for ic in id_columns)
    sorted_by_list = ", ".join(f"'{ic}'" for ic in id_columns)
    
    col_casts = ",\n        ".join(
        f"{build_cast_expr(c['name'], c['data_type'], trim_strings)} AS {quote(c['name'])}"
        for c in common_col_meta
    )
    
    hash_elements = ",\n            ".join(
        f"COALESCE({quote(c['name'])}, CHR(0))"
        for c in common_col_meta
    )

    query = f"""\
CREATE TABLE {iceberg_catalog}.{iceberg_schema}.{target_temp_table}
WITH (
    format = 'PARQUET',
    sorted_by = ARRAY[{sorted_by_list}]
) AS
WITH casted AS (
    SELECT
        {id_select},
        {col_casts}
    FROM {catalog}.{schema}.{table_name}
)
SELECT
    *,
    xxhash64(to_utf8(CONCAT_WS(CHR(31),
        {hash_elements}
    ))) AS row_hash
FROM casted
"""
    return query


def build_iceberg_stage2_missing_keys(
    id_columns: list,
    iceberg_catalog: str,
    iceberg_schema: str,
    src_temp_tbl: str,
    tgt_temp_tbl: str,
    diff_type: str,  # 'ONLY_IN_SOURCE' or 'ONLY_IN_TARGET'
) -> str:
    """Generate anti-join query to find missing records between Iceberg staging tables."""
    if diff_type == "ONLY_IN_SOURCE":
        primary_tbl, foreign_tbl = src_temp_tbl, tgt_temp_tbl
    else:
        primary_tbl, foreign_tbl = tgt_temp_tbl, src_temp_tbl

    id_select = ",\n    ".join(f"p.{quote(ic)}" for ic in id_columns)
    join_cond = " AND ".join(f"p.{quote(ic)} = f.{quote(ic)}" for ic in id_columns)

    query = f"""\
SELECT
    {id_select},
    '{diff_type}' AS row_diff_type,
    CAST(NULL AS VARCHAR) AS column_name,
    CAST(NULL AS VARCHAR) AS postgres_value,
    CAST(NULL AS VARCHAR) AS oracle_value
FROM {iceberg_catalog}.{iceberg_schema}.{primary_tbl} p
WHERE NOT EXISTS (
    SELECT 1 FROM {iceberg_catalog}.{iceberg_schema}.{foreign_tbl} f
    WHERE {join_cond}
)
"""
    return query


def build_iceberg_stage3_mismatch_keys_ctas(
    id_columns: list,
    iceberg_catalog: str,
    iceberg_schema: str,
    src_temp_tbl: str,
    tgt_temp_tbl: str,
    mismatch_temp_tbl: str,
) -> str:
    """Generate CTAS statement isolating mismatched keys via row hash comparison (retained for backward compatibility)."""
    id_select = ",\n    ".join(f"s.{quote(ic)}" for ic in id_columns)
    join_cond = " AND ".join(f"s.{quote(ic)} = t.{quote(ic)}" for ic in id_columns)
    query = f"""\
CREATE TABLE {iceberg_catalog}.{iceberg_schema}.{mismatch_temp_tbl}
WITH (
    format = 'PARQUET'
) AS
SELECT
    {id_select}
FROM {iceberg_catalog}.{iceberg_schema}.{src_temp_tbl} s
JOIN {iceberg_catalog}.{iceberg_schema}.{tgt_temp_tbl} t
    ON {join_cond}
WHERE s.row_hash != t.row_hash
"""
    return query


def build_iceberg_stage4_mismatch_unnest(
    id_columns: list,
    common_col_meta: list,
    exclude_cols: list,
    exclude_suffix,
    iceberg_catalog: str,
    iceberg_schema: str,
    src_temp_tbl: str,
    tgt_temp_tbl: str,
    mismatch_temp_tbl: str = None,
) -> str:
    """Generate targeted UNNEST query for keys with a hash mismatch.
    
    Optimizations:
    1. Pre-filters excluded columns in Python before building the UNNEST arrays,
       avoiding exploding rows for columns that are excluded.
    2. Inlines the row_hash comparison (s.row_hash != t.row_hash) directly into the join,
       eliminating the need for an intermediate mismatch table when mismatch_temp_tbl is None.
    """
    excluded_set = {c.strip().lower() for c in (exclude_cols or [])}
    suffix_lower = exclude_suffix.strip().lower() if exclude_suffix else None

    filtered_col_meta = []
    for c in common_col_meta:
        col_lower = c["name"].lower()
        if col_lower in excluded_set:
            continue
        if suffix_lower and col_lower.endswith(suffix_lower):
            continue
        filtered_col_meta.append(c)

    active_cols = [c["name"] for c in (filtered_col_meta or common_col_meta)]
    id_select = ",\n    ".join(f"s.{quote(ic)}" for ic in id_columns)
    join_cond_st = " AND ".join(f"s.{quote(ic)} = t.{quote(ic)}" for ic in id_columns)

    col_name_array = ",\n        ".join(f"'{c}'" for c in active_cols)
    s_val_array = ",\n        ".join(f"s.{quote(c)}" for c in active_cols)
    t_val_array = ",\n        ".join(f"t.{quote(c)}" for c in active_cols)

    if mismatch_temp_tbl:
        join_cond_sm = " AND ".join(f"s.{quote(ic)} = m.{quote(ic)}" for ic in id_columns)
        from_clause = f"""FROM {iceberg_catalog}.{iceberg_schema}.{src_temp_tbl} s
JOIN {iceberg_catalog}.{iceberg_schema}.{tgt_temp_tbl} t
    ON {join_cond_st}
JOIN {iceberg_catalog}.{iceberg_schema}.{mismatch_temp_tbl} m
    ON {join_cond_sm}"""
    else:
        from_clause = f"""FROM {iceberg_catalog}.{iceberg_schema}.{src_temp_tbl} s
JOIN {iceberg_catalog}.{iceberg_schema}.{tgt_temp_tbl} t
    ON {join_cond_st}
    AND s.row_hash != t.row_hash"""

    query = f"""\
SELECT
    {id_select},
    'VALUE_MISMATCH' AS row_diff_type,
    u.column_name,
    u.postgres_value,
    u.oracle_value
{from_clause}
CROSS JOIN UNNEST(
    ARRAY[
        {col_name_array}
    ],
    ARRAY[
        {s_val_array}
    ],
    ARRAY[
        {t_val_array}
    ]
) AS u(column_name, postgres_value, oracle_value)
WHERE
    u.postgres_value IS DISTINCT FROM u.oracle_value
"""
    return query


def build_iceberg_cleanup_queries(
    iceberg_catalog: str,
    iceberg_schema: str,
    src_temp_tbl: str,
    tgt_temp_tbl: str,
    mismatch_temp_tbl: str = None,
) -> list:
    """Generate list of DROP TABLE statements for temporary Iceberg staging tables."""
    queries = [
        f"DROP TABLE IF EXISTS {iceberg_catalog}.{iceberg_schema}.{src_temp_tbl}",
        f"DROP TABLE IF EXISTS {iceberg_catalog}.{iceberg_schema}.{tgt_temp_tbl}",
    ]
    if mismatch_temp_tbl:
        queries.append(f"DROP TABLE IF EXISTS {iceberg_catalog}.{iceberg_schema}.{mismatch_temp_tbl}")
    return queries


def build_iceberg_pipeline_preview_sql(
    table_name: str,
    id_columns: list,
    common_col_meta: list,
    exclude_cols: list,
    exclude_suffix,
    trim_strings: bool,
    pg_schema: str = "curated",
    ora_schema: str = "curated",
    source_catalog: str = "postgres",
    target_catalog: str = "oracle",
    iceberg_catalog: str = "iceberg",
    iceberg_schema: str = "staging",
    run_id: str = "preview",
) -> str:
    """Generate full annotated SQL script displaying the optimized multi-stage Iceberg execution plan."""
    src_temp, tgt_temp, _ = build_iceberg_stage_table_names(table_name, run_id)
    
    q_src_ctas = build_iceberg_stage1_ctas(
        catalog=source_catalog, schema=pg_schema, table_name=table_name,
        id_columns=id_columns, common_col_meta=common_col_meta, trim_strings=trim_strings,
        iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_schema, target_temp_table=src_temp
    )
    q_tgt_ctas = build_iceberg_stage1_ctas(
        catalog=target_catalog, schema=ora_schema, table_name=table_name,
        id_columns=id_columns, common_col_meta=common_col_meta, trim_strings=trim_strings,
        iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_schema, target_temp_table=tgt_temp
    )
    q_mis_src = build_iceberg_stage2_missing_keys(
        id_columns=id_columns, iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_schema,
        src_temp_tbl=src_temp, tgt_temp_tbl=tgt_temp, diff_type="ONLY_IN_SOURCE"
    )
    q_mis_tgt = build_iceberg_stage2_missing_keys(
        id_columns=id_columns, iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_schema,
        src_temp_tbl=src_temp, tgt_temp_tbl=tgt_temp, diff_type="ONLY_IN_TARGET"
    )
    q_unnest = build_iceberg_stage4_mismatch_unnest(
        id_columns=id_columns, common_col_meta=common_col_meta, exclude_cols=exclude_cols,
        exclude_suffix=exclude_suffix, iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_schema,
        src_temp_tbl=src_temp, tgt_temp_tbl=tgt_temp, mismatch_temp_tbl=None
    )
    cleanup = build_iceberg_cleanup_queries(iceberg_catalog, iceberg_schema, src_temp, tgt_temp)

    preview = f"""\
-- =============================================================================
-- ICEBERG STAGED DIFF PIPELINE PLAN: {table_name}
-- Engine: ICEBERG_STAGED | Staging: {iceberg_catalog}.{iceberg_schema}
-- =============================================================================

-- -----------------------------------------------------------------------------
-- STAGE 1A: Ingest Source Table into Iceberg Columnar Staging with xxhash64 (Runs Concurrently with Stage 1B)
-- -----------------------------------------------------------------------------
{q_src_ctas.strip()};

-- -----------------------------------------------------------------------------
-- STAGE 1B: Ingest Target Table into Iceberg Columnar Staging with xxhash64 (Runs Concurrently with Stage 1A)
-- -----------------------------------------------------------------------------
{q_tgt_ctas.strip()};

-- -----------------------------------------------------------------------------
-- STAGE 2A: Query Missing Records in Target (ONLY_IN_SOURCE - Runs Concurrently with Stage 2B)
-- -----------------------------------------------------------------------------
{q_mis_src.strip()};

-- -----------------------------------------------------------------------------
-- STAGE 2B: Query Missing Records in Source (ONLY_IN_TARGET - Runs Concurrently with Stage 2A)
-- -----------------------------------------------------------------------------
{q_mis_tgt.strip()};

-- -----------------------------------------------------------------------------
-- STAGE 3: Targeted Column UNNEST (Inlined Hash Filter s.row_hash != t.row_hash)
-- -----------------------------------------------------------------------------
{q_unnest.strip()};

-- -----------------------------------------------------------------------------
-- STAGE 4: Cleanup Temporary Iceberg Staging Tables
-- -----------------------------------------------------------------------------
{cleanup[0]};
{cleanup[1]};
"""
    return preview


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Trino column-level diff query between "
            "<source_catalog>.<schema>.<table> and <target_catalog>.<schema>.<table>."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--table-name", required=True,
        help="Table name (without schema/catalog prefix, or with schema prefix e.g. rdm.ref_table).",
    )
    parser.add_argument(
        "--schema", default=None,
        help="Schema name (e.g. 'curated' or 'rdm'). If omitted, automatically checks 'curated' then 'rdm'.",
    )
    parser.add_argument(
        "--source-catalog", "--postgres-catalog", dest="source_catalog",
        default=DEFAULT_SOURCE_CATALOG,
        help=f"Source catalog name (default: '{DEFAULT_SOURCE_CATALOG}').",
    )
    parser.add_argument(
        "--target-catalog", "--oracle-catalog", dest="target_catalog",
        default=DEFAULT_TARGET_CATALOG,
        help=f"Target catalog name (default: '{DEFAULT_TARGET_CATALOG}').",
    )
    parser.add_argument(
        "--id-column", action="append", dest="id_columns", required=True,
        metavar="COL",
        help=(
            "Primary key column(s). Use the flag multiple times for composite keys. "
            "Example: --id-column transaction_id --id-column company_code"
        ),
    )
    parser.add_argument(
        "--exclude-columns", default="",
        metavar="COL1,COL2,...",
        help="Comma-separated column names to exclude from the final result (e.g. as_of_date,extraction_timestamp).",
    )
    parser.add_argument(
        "--exclude-suffix", default="",
        metavar="SUFFIX",
        help="Exclude columns whose name ends with this suffix (e.g. 'key' to exclude all *_key columns).",
    )
    parser.add_argument(
        "--trim-strings", action="store_true",
        help=(
            "Wrap all CAST expressions in TRIM() to normalise Oracle CHAR column "
            "trailing-space padding. Addresses false-positive mismatches."
        ),
    )
    parser.add_argument(
        "--engine", choices=["iceberg", "direct"], default="iceberg",
        help="Diff execution engine: 'iceberg' (staged multi-step breakdown) or 'direct' (monolithic query). Default: 'iceberg'.",
    )
    parser.add_argument(
        "--iceberg-catalog", default="iceberg",
        help="Iceberg catalog name in Trino (default: 'iceberg').",
    )
    parser.add_argument(
        "--iceberg-schema", default="staging",
        help="Iceberg staging schema in Trino (default: 'staging').",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print metadata, gap report, type warnings, and column counts before the query.",
    )
    parser.add_argument(
        "--output", default=None,
        metavar="FILE",
        help="Write the generated SQL to this file. If omitted, prints to stdout.",
    )

    args = parser.parse_args()

    table_name = args.table_name
    schema = args.schema
    source_catalog = args.source_catalog
    target_catalog = args.target_catalog

    # If table_name contains a schema prefix (e.g. 'rdm.ref_something'), extract it
    if "." in table_name:
        parts = table_name.split(".", 1)
        if not schema:
            schema = parts[0]
        table_name = parts[1]

    id_columns = args.id_columns  # list[str], supports composite keys
    exclude_cols = [c.strip() for c in args.exclude_columns.split(",") if c.strip()]
    exclude_suffix = args.exclude_suffix.strip() or None
    trim_strings = args.trim_strings
    verbose = args.verbose
    engine = args.engine
    iceberg_catalog = args.iceberg_catalog
    iceberg_schema = args.iceberg_schema

    # ------------------------------------------------------------------
    # Connect and fetch metadata concurrently
    # ------------------------------------------------------------------
    if verbose:
        print(f"[INFO] Connecting to Trino at {TRINO_HOST}:{TRINO_PORT} as '{TRINO_USER}'")
        print(f"[INFO] Fetching columns concurrently for {source_catalog} & {target_catalog} ({schema or 'auto'}.{table_name}) ...")

    def _fetch_meta_concurrent(cat):
        c = get_trino_connection()
        cur = c.cursor()
        try:
            return fetch_columns(
                cur, cat, table_name, schema,
                exclude_cols=exclude_cols,
                exclude_suffix=exclude_suffix,
                id_columns=id_columns
            )
        finally:
            try:
                cur.close()
                c.close()
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=2) as executor:
        fut_pg = executor.submit(_fetch_meta_concurrent, source_catalog)
        fut_ora = executor.submit(_fetch_meta_concurrent, target_catalog)
        pg_schema, pg_cols = fut_pg.result()
        ora_schema, ora_cols = fut_ora.result()

    # ------------------------------------------------------------------
    # Corner Case #5: Fail fast if either catalog returns no columns
    # ------------------------------------------------------------------
    schema_label = schema or "/".join(DEFAULT_SCHEMAS)
    if not pg_cols:
        print(
            f"[ERROR] Table '{source_catalog}.{schema_label}.{table_name}' returned no columns.\n"
            "        Check the table name, schema, catalog, and your Trino connection.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not ora_cols:
        print(
            f"[ERROR] Table '{target_catalog}.{schema_label}.{table_name}' returned no columns.\n"
            "        Check the table name, schema, catalog, and your Trino connection.",
            file=sys.stderr,
        )
        sys.exit(1)

    if verbose:
        print(f"[INFO] Source ({source_catalog}) schema: {pg_schema} (columns: {len(pg_cols)})")
        print(f"[INFO] Target ({target_catalog}) schema: {ora_schema} (columns: {len(ora_cols)})")

    # ------------------------------------------------------------------
    # Corner Case #6: Always print schema gap report
    # ------------------------------------------------------------------
    print_gap_report(pg_cols, ora_cols, id_columns)

    # ------------------------------------------------------------------
    # Compute intersection, exclude id columns, sort deterministically
    # Corner Cases #2 (id column excluded), #4 (sort for stable ordering)
    # ------------------------------------------------------------------
    pg_name_map = {c["name"]: c for c in pg_cols}
    ora_name_map = {c["name"]: c for c in ora_cols}
    id_col_set = set(id_columns)

    common_names = sorted(
        (set(pg_name_map.keys()) & set(ora_name_map.keys())) - id_col_set
    )

    if not common_names:
        print(
            f"[ERROR] No common columns found between {source_catalog} and {target_catalog} "
            "(after excluding id columns). Cannot generate a useful query.",
            file=sys.stderr,
        )
        sys.exit(1)

    if verbose:
        print(f"[INFO] Common columns to compare: {len(common_names)}")
        for c in common_names:
            print(f"         {c}")
        print()

    # ------------------------------------------------------------------
    # Corner Case #12: ROW() field limit warning
    # ------------------------------------------------------------------
    if len(common_names) > ROW_FIELD_LIMIT_WARNING and engine == "direct":
        print(
            f"[WARN] {len(common_names)} columns will be placed into the ROW() comparison struct "
            f"(connector hard limit is typically ~{ROW_FIELD_HARD_LIMIT} fields). "
            f"If you see 'Too many fields in row type' errors, switch to --engine iceberg "
            f"or reduce column count with --exclude-columns.\n"
        )

    # ------------------------------------------------------------------
    # Corner Case #1: Prefix collision detection
    # ------------------------------------------------------------------
    check_prefix_collision(common_names)

    # ------------------------------------------------------------------
    # Corner Cases #8 & #9: Type-based false-mismatch warnings
    # ------------------------------------------------------------------
    common_col_meta = [
        {"name": n, "data_type": pg_name_map[n]["data_type"]}
        for n in common_names
    ]
    warn_type_issues(common_col_meta)

    # ------------------------------------------------------------------
    # Build and output the query
    # ------------------------------------------------------------------
    if engine == "iceberg":
        query = build_iceberg_pipeline_preview_sql(
            table_name=table_name,
            id_columns=id_columns,
            common_col_meta=common_col_meta,
            exclude_cols=exclude_cols,
            exclude_suffix=exclude_suffix,
            trim_strings=trim_strings,
            pg_schema=pg_schema,
            ora_schema=ora_schema,
            source_catalog=source_catalog,
            target_catalog=target_catalog,
            iceberg_catalog=iceberg_catalog,
            iceberg_schema=iceberg_schema,
        )
    else:
        query = build_direct_query(
            table_name=table_name,
            id_columns=id_columns,
            common_col_meta=common_col_meta,
            exclude_cols=exclude_cols,
            exclude_suffix=exclude_suffix,
            trim_strings=trim_strings,
            pg_schema=pg_schema,
            ora_schema=ora_schema,
            source_catalog=source_catalog,
            target_catalog=target_catalog,
        )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(query)
        print(f"[INFO] Query written to: {args.output}")
    else:
        print("\n" + "=" * 70)
        print(f"GENERATED TRINO DIFF PLAN ({engine.upper()} ENGINE)")
        print("=" * 70 + "\n")
        print(query)


if __name__ == "__main__":
    main()

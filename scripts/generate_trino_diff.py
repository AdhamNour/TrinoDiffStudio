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
python generate_trino_diff.py \\
    --table-name fct_product_financial_transactions \\
    --id-column transaction_id \\
    --exclude-columns as_of_date,extraction_timestamp,date_time \\
    --exclude-suffix key \\
    --trim-strings \\
    --verbose \\
    --output diff_query.sql
"""

import argparse
import sys
import os

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
ROW_FIELD_LIMIT_WARNING = 30  # warn if column count exceeds this

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


def fetch_columns(cursor, catalog: str, table_name: str, schema: str = None) -> tuple:
    """
    Fetch column metadata (name + data_type) from information_schema.
    If schema is not specified, tries DEFAULT_SCHEMAS ('curated', 'rdm') in order.
    Returns a tuple: (schema_found, [{'name': str, 'data_type': str}, ...])
    """
    schemas_to_try = [schema] if schema else DEFAULT_SCHEMAS
    for sch in schemas_to_try:
        sql = (
            "SELECT column_name, data_type "
            f"FROM {catalog}.information_schema.columns "
            f"WHERE table_schema = '{sch}' "
            f"  AND table_name   = '{table_name}' "
            "ORDER BY ordinal_position"
        )
        cursor.execute(sql)
        rows = cursor.fetchall()
        if rows:
            return sch, [{"name": row[0], "data_type": row[1].lower()} for row in rows]
    return (schema or schemas_to_try[0]), []


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
# Query Builder
# ---------------------------------------------------------------------------

def build_cast(alias: str, col: str, data_type: str, trim: bool) -> str:
    """Build a single CAST expression."""
    qcol = quote(col)
    prefix = alias[0]  # 'p' or 'o'
    
    if "timestamp" in data_type or data_type == "date":
        cast_expr = f"CAST(CAST({alias}.{qcol} AS TIMESTAMP(0)) AS VARCHAR)"
    else:
        cast_expr = f"CAST({alias}.{qcol} AS VARCHAR)"

    if trim:
        cast_expr = f"TRIM({cast_expr})"
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


def build_query(
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
    """Assemble the full Trino diff query.

    ONLY_IN_ORACLE / ONLY_IN_POSTGRES rows produce a single summary row per
    missing record (key columns + row_diff_type; column_name/postgres_value/
    oracle_value are NULL).  VALUE_MISMATCH rows are still expanded per-column
    via UNNEST so individual differing columns are surfaced.
    """
    common_cols = [c["name"] for c in common_col_meta]

    # ---- JOIN conditions (supports composite keys) ----
    # Corner Case #3: multi-column id
    join_parts = "\n        AND ".join(
        f"p.{quote(ic)} = o.{quote(ic)}" for ic in id_columns
    )

    # ---- COALESCE for each id column ----
    coalesce_parts = ",\n        ".join(
        f"COALESCE(p.{quote(ic)}, o.{quote(ic)}) AS {ic}" for ic in id_columns
    )

    # ---- row_diff_type CASE ----
    # Use the first id column for the NULL side detection
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
    # Remove trailing comma from last line
    if p_cast_lines:
        p_cast_lines[-1] = p_cast_lines[-1].rstrip(",")
    if o_cast_lines:
        o_cast_lines[-1] = o_cast_lines[-1].rstrip(",")
    p_casts = "\n".join(p_cast_lines)
    o_casts = "\n".join(o_cast_lines)

    # ---- ROW() comparison — identical ordering on both sides ----
    # Corner Case #4: column ordering must be deterministic and identical
    p_row_cols = ", ".join(f"p.{quote(c)}" for c in common_cols)
    o_row_cols = ", ".join(f"o.{quote(c)}" for c in common_cols)

    # ---- UNNEST arrays — must match common_cols order exactly ----
    # Corner Case #2: id column is NOT in these arrays
    col_name_array = ",\n            ".join(f"'{c}'" for c in common_cols)
    p_val_array = ",\n            ".join(f"d.p_{c}" for c in common_cols)
    o_val_array = ",\n            ".join(f"d.o_{c}" for c in common_cols)

    # ---- WHERE clause for VALUE_MISMATCH branch ----
    # Corner Case #11: dynamic exclude-columns and exclude-suffix
    # row_diff_type filter is the first condition so there is exactly one WHERE keyword.
    mismatch_where_parts = [
        "d.row_diff_type = 'VALUE_MISMATCH'",
        "u.postgres_value IS DISTINCT FROM u.oracle_value",
    ]
    if exclude_cols:
        quoted_list = ", ".join(f"'{c}'" for c in exclude_cols)
        mismatch_where_parts.append(f"u.column_name NOT IN ({quoted_list})")
    if exclude_suffix:
        mismatch_where_parts.append(f"u.column_name NOT LIKE '%{exclude_suffix}'")

    mismatch_where_clause = "\n    WHERE\n        " + "\n        AND ".join(mismatch_where_parts)

    # ---- SELECT id columns in final result ----
    id_select = ",\n        ".join(f"d.{ic}" for ic in id_columns)

    # id columns for the missing-record branch (no alias needed — same names)
    id_select_missing = ",\n        ".join(f"d.{ic}" for ic in id_columns)

    # ---- ORDER BY ordinal positions ----
    order_by = ", ".join(str(i + 1) for i in range(len(id_columns) + 1))  # +1 for column_name

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
),
final_result AS (
    -- VALUE_MISMATCH: expand per-column so each differing column gets its own row
    SELECT
        {id_select},
        d.row_diff_type,
        u.column_name,
        u.postgres_value,
        u.oracle_value
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
    ) AS u(column_name, postgres_value, oracle_value){mismatch_where_clause}

    UNION ALL

    -- ONLY_IN_TARGET / ONLY_IN_SOURCE: emit a single summary row per missing record
    SELECT
        {id_select_missing},
        d.row_diff_type,
        CAST(NULL AS VARCHAR) AS column_name,
        CAST(NULL AS VARCHAR) AS postgres_value,
        CAST(NULL AS VARCHAR) AS oracle_value
    FROM diff_data d
    WHERE d.row_diff_type IN ('ONLY_IN_TARGET', 'ONLY_IN_SOURCE', 'ONLY_IN_ORACLE', 'ONLY_IN_POSTGRES')
)
SELECT *
FROM final_result
ORDER BY {order_by};
"""
    return query


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

    # ------------------------------------------------------------------
    # Connect and fetch metadata
    # ------------------------------------------------------------------
    if verbose:
        print(f"[INFO] Connecting to Trino at {TRINO_HOST}:{TRINO_PORT} as '{TRINO_USER}'")

    conn = get_trino_connection()
    cursor = conn.cursor()

    if verbose:
        print(f"[INFO] Fetching columns for {source_catalog}.{schema or 'auto'}.{table_name} ...")
    pg_schema, pg_cols = fetch_columns(cursor, source_catalog, table_name, schema)

    if verbose:
        print(f"[INFO] Fetching columns for {target_catalog}.{schema or 'auto'}.{table_name} ...")
    ora_schema, ora_cols = fetch_columns(cursor, target_catalog, table_name, schema)

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
    if len(common_names) > ROW_FIELD_LIMIT_WARNING:
        print(
            f"[WARN] {len(common_names)} columns will be placed into ROW() structs. "
            f"Trino may have connector-specific field limits (typically ~32). "
            f"If you encounter 'Too many fields in row type' errors, "
            f"consider splitting the comparison into multiple CTEs.\n"
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
    query = build_query(
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
        print("GENERATED TRINO DIFF QUERY")
        print("=" * 70 + "\n")
        print(query)


if __name__ == "__main__":
    main()

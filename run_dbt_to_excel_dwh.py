"""
Run a dbt command and export per-model results to Excel.

How it works
------------
1. Builds and executes the dbt command (streams output to the console).
2. After dbt finishes, reads the structured `target/run_results.json`
   artifact that dbt always writes.
3. Produces an Excel file with one row per model showing the model name,
   status, execution time, full error message for any failure, and an
   auto-derived Category / Root cause / Suggested fix for each error.
4. Adds a "Summary" sheet with overall totals and error counts per category.

Requirements
------------
    pip install openpyxl
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Configuration -- edit these as needed
# ---------------------------------------------------------------------------
PROJECT_DIR = r"C:\Users\anhassan\airflow-dags\dbt"
PROFILES_DIR = r"C:\Users\anhassan\airflow-dags\dbt"
PROFILE = "company_lakehouse_pg"
TARGET = "postgres_curated"
SELECT_TAG = "tag:run_dwh"

# Shared parameter values for every model listed below
AS_OF_DATE = "20260329"
EXTRACTION_TIME_SLOT = 3

MODELS_IN_VARS = [
    "ref_app_device_os_type",
    "ref_app_biometrics_type",
    "dim_app_registered_users",
    "ref_app_user_status_type",
    "ref_app_device_status_type",
    "ref_app_transaction_error",
    "dim_crm_system_user",
    "dim_app_registered_user_devices",
    "fct_app_registered_user_sessions",
    "ref_app_reset_passcode_status_type",
]

# Where to write the report (next to this script, timestamped)
OUTPUT_XLSX = Path(__file__).with_name(
    f"dbt_run_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
)


# ---------------------------------------------------------------------------
# dbt command
# ---------------------------------------------------------------------------
def build_command() -> list[str]:
    parameter_config = {
        model: {
            "as_of_date": AS_OF_DATE,
            "extraction_time_slot": EXTRACTION_TIME_SLOT,
        }
        for model in MODELS_IN_VARS
    }
    vars_payload = json.dumps({"parameter_config": parameter_config})

    return [
        "dbt", "run",
        "--select", SELECT_TAG,
        # "--exclude", "dim_customer+",
        "--vars", vars_payload,
        "--project-dir", PROJECT_DIR,
        "--profiles-dir", PROFILES_DIR,
        "--profile", PROFILE,
        "--target", TARGET,
        "--no-static-parser",
    ]


def run_dbt(command: list[str]) -> int:
    """Stream dbt output to the console and return the exit code."""
    print(">>", " ".join(command), flush=True)
    print("-" * 80, flush=True)
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
    return proc.wait()


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------
def load_run_results(project_dir: str) -> list[dict]:
    path = Path(project_dir) / "target" / "run_results.json"
    if not path.exists():
        raise FileNotFoundError(f"Could not find dbt artifact: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f).get("results", [])


def model_name_from(unique_id: str) -> str:
    # e.g. "model.my_project.dim_app_registered_users" -> "dim_app_registered_users"
    return unique_id.split(".")[-1] if unique_id else ""


def node_kind_from(unique_id: str) -> str:
    # "model", "seed", "snapshot", "test", ...
    return unique_id.split(".")[0] if unique_id else ""


# ---------------------------------------------------------------------------
# Error categorization
# ---------------------------------------------------------------------------
# Background fill (hex, no leading #) per category. Used to colour the Category
# cell on error rows so the most common buckets are scannable at a glance.
CATEGORY_FILLS: dict[str, str] = {
    "Type mismatch — text vs timestamp": "FFF2CC",
    "Type mismatch — bigint vs varchar": "FFF2CC",
    "Type mismatch — other":             "FFF2CC",
    "UNION type mismatch":               "FFF2CC",
    "Schema drift — column missing":     "FCE4D6",
    "Missing staging table":             "F8CBAD",
    "SQL syntax error":                  "D9E1F2",
    "NOT NULL constraint violation":     "E2EFDA",
    "Unique constraint violation":       "E2EFDA",
    "MERGE — duplicate target row":      "E2EFDA",
    "Ambiguous column reference":        "EDEDED",
    "Operator type mismatch":            "EDEDED",
    "Duplicate column in SELECT":        "EDEDED",
    "Invalid numeric cast":              "EDEDED",
    "Uncategorized":                     "FFFFFF",
}


def categorize_error(message: str) -> tuple[str, str, str]:
    """
    Inspect a dbt/Postgres error message and return
    (category, root_cause, suggested_fix).

    Patterns are ordered most-specific first so generic fallbacks
    don't swallow more precise matches.
    """
    if not message:
        return ("", "", "")

    # ---- Missing upstream relation -----------------------------------------
    m = re.search(r'relation "([^"]+)" does not exist', message)
    if m:
        rel = m.group(1)
        return (
            "Missing staging table",
            f"Upstream {rel} not built",
            "Run staging layer before curated; verify model exists in project",
        )

    # ---- NOT NULL constraint -----------------------------------------------
    m = re.search(
        r'null value in column "([^"]+)" of relation "[^"]+" '
        r'violates not-null constraint',
        message,
    )
    if m:
        col = m.group(1)
        return (
            "NOT NULL constraint violation",
            f"Null {col} in source row",
            "Filter nulls in WHERE or fix surrogate key generation",
        )

    # ---- Unique key duplicate ----------------------------------------------
    m = re.search(
        r'duplicate key value violates unique constraint.*?'
        r'Key \(([^)]+)\)=\(([^)]+)\) already exists',
        message,
        re.DOTALL,
    )
    if m:
        col, val = m.group(1), m.group(2)
        return (
            "Unique constraint violation",
            f"Duplicate {col}={val} in source",
            "Deduplicate source or use incremental unique_key logic",
        )

    # ---- Type mismatch: target column vs expression ------------------------
    # Specific buckets first, then a generic fallback that still extracts
    # both types from the message.
    m = re.search(
        r'column "([^"]+)" is of type timestamp[^"]*? '
        r'but expression is of type text',
        message,
    )
    if m:
        col = m.group(1)
        return (
            "Type mismatch — text vs timestamp",
            f"{col} cast issue (text → timestamp)",
            f"Add ::timestamp cast to the {col} expression",
        )

    m = re.search(
        r'column "([^"]+)" is of type bigint '
        r'but expression is of type character varying',
        message,
    )
    if m:
        col = m.group(1)
        return (
            "Type mismatch — bigint vs varchar",
            f"{col} type mismatch (varchar → bigint)",
            f"Cast {col} to ::bigint or align column types",
        )

    m = re.search(
        r'column "([^"]+)" is of type (\S+).*? '
        r'but expression is of type (\S+)',
        message,
    )
    if m:
        col, target_type, expr_type = m.group(1), m.group(2), m.group(3)
        return (
            "Type mismatch — other",
            f"{col} type mismatch ({expr_type} → {target_type})",
            f"Add explicit cast on {col} to {target_type}",
        )

    # ---- UNION type mismatch -----------------------------------------------
    m = re.search(r'UNION types (.+?) and (.+?) cannot be matched', message)
    if m:
        t1, t2 = m.group(1), m.group(2)
        return (
            "UNION type mismatch",
            f"{t1} vs {t2} in UNION branches",
            "Cast both branches of the UNION to the same type",
        )

    # ---- MERGE matched the same target row twice ---------------------------
    if "MERGE command cannot affect row a second time" in message:
        return (
            "MERGE — duplicate target row",
            "Source has duplicates causing MERGE to match twice",
            "Deduplicate source or refine unique_key in incremental config",
        )

    # ---- Ambiguous column --------------------------------------------------
    m = re.search(r'column reference "([^"]+)" is ambiguous', message)
    if m:
        col = m.group(1)
        return (
            "Ambiguous column reference",
            f'Column "{col}" ambiguous in multi-table query',
            f"Qualify {col} with a table alias",
        )

    # ---- Invalid cast for a specific type ----------------------------------
    m = re.search(r'invalid input syntax for type (\S+): "([^"]+)"', message)
    if m:
        typ, val = m.group(1), m.group(2)
        return (
            f"Invalid {typ} cast",
            f'Value "{val}" cannot be cast to {typ}',
            f"Remove the {typ} cast or filter non-{typ} values upstream",
        )

    # ---- Operator does not exist (e.g. regex on timestamp) -----------------
    m = re.search(r'operator does not exist: ([^\n]+)', message)
    if m:
        sig = m.group(1).strip()
        return (
            "Operator type mismatch",
            f"Operator mismatch: {sig}",
            "Add explicit type casts so the operator can resolve",
        )

    # ---- Duplicate column in SELECT ----------------------------------------
    m = re.search(r'column "([^"]+)" specified more than once', message)
    if m:
        col = m.group(1)
        return (
            "Duplicate column in SELECT",
            f"{col} selected twice",
            f"Remove duplicate {col} from the SELECT list",
        )

    # ---- SQL syntax error --------------------------------------------------
    m = re.search(r'syntax error at or near "([^"]+)"', message)
    if m:
        near = m.group(1)
        return (
            "SQL syntax error",
            f'Syntax error near "{near}"',
            "Inspect compiled SQL — often a broken macro or missing CTE alias",
        )

    # ---- Schema drift: column does not exist (LAST so it doesn't shadow) ---
    # Quoted form: column "foo" does not exist
    # Unquoted form: column a.date does not exist
    m = re.search(r'column "([^"]+)" does not exist', message)
    if not m:
        m = re.search(r'column (\S+) does not exist', message)
    if m:
        col = m.group(1)
        hint = re.search(
            r'Perhaps you meant to reference the column "([^"]+)"', message
        )
        if hint:
            suggestion = hint.group(1).split(".")[-1]
            return (
                "Schema drift — column missing",
                f"Column {col} renamed (Postgres suggests {suggestion})",
                "Update column reference per Postgres hint",
            )
        return (
            "Schema drift — column missing",
            f"Column {col} no longer in source",
            "Check current staging schema; update column reference",
        )

    return ("Uncategorized", "", "Review manually")


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
def write_excel(results: list[dict], output_path: Path) -> tuple[int, int, int, dict[str, int]]:
    wb = Workbook()
    ws = wb.active
    ws.title = "dbt run results"

    headers = [
        "#", "Type", "Model", "Status", "Succeeded?", "Execution time (s)",
        "Error message", "Category", "Root cause", "Suggested fix",
    ]
    ws.append(headers)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="305496")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    success_fill = PatternFill("solid", fgColor="C6EFCE")  # green
    error_fill   = PatternFill("solid", fgColor="FFC7CE")  # red
    skipped_fill = PatternFill("solid", fgColor="FFEB9C")  # yellow

    successes = failures = skipped = 0
    category_counts: dict[str, int] = {}

    for idx, r in enumerate(results, start=1):
        unique_id = r.get("unique_id", "")
        status = (r.get("status") or "").lower()
        exec_time = r.get("execution_time") or 0
        message = r.get("message") or ""

        if status == "success":
            successes += 1
            succeeded = "YES"
            fill = success_fill
        elif status == "skipped":
            skipped += 1
            succeeded = "SKIPPED"
            fill = skipped_fill
        else:
            failures += 1
            succeeded = "NO"
            fill = error_fill

        # Only categorize actual failures
        if status not in ("success", "skipped"):
            category, root_cause, suggested_fix = categorize_error(message)
            category_counts[category] = category_counts.get(category, 0) + 1
        else:
            category, root_cause, suggested_fix = "", "", ""

        ws.append([
            idx,
            node_kind_from(unique_id),
            model_name_from(unique_id),
            status,
            succeeded,
            round(float(exec_time), 3),
            message,
            category,
            root_cause,
            suggested_fix,
        ])

        row_idx = ws.max_row
        # Highlight the status + succeeded cells
        ws.cell(row=row_idx, column=4).fill = fill
        ws.cell(row=row_idx, column=5).fill = fill

        # Colour the Category cell by category for error rows
        if category:
            color = CATEGORY_FILLS.get(category, "FFFFFF")
            ws.cell(row=row_idx, column=8).fill = PatternFill("solid", fgColor=color)

    # Column widths
    widths = [5, 10, 40, 12, 12, 18, 90, 36, 50, 50]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    # Wrap the long text columns: error message, root cause, suggested fix
    for col_letter in ("G", "I", "J"):
        for row in ws.iter_rows(
            min_row=2,
            min_col=ws[col_letter + "1"].column,
            max_col=ws[col_letter + "1"].column,
        ):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    _write_summary_sheet(wb, successes, failures, skipped, category_counts)

    wb.save(output_path)
    return successes, failures, skipped, category_counts


def _write_summary_sheet(
    wb: Workbook,
    successes: int,
    failures: int,
    skipped: int,
    category_counts: dict[str, int],
) -> None:
    """Add a Summary sheet with overall totals and per-category error counts."""
    ws = wb.create_sheet("Summary", 0)  # insert as first sheet

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="305496")
    section_font = Font(bold=True, size=11)

    # --- Overall totals ---
    ws.append(["dbt run — overall results"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Metric", "Value"])
    for col_idx in (1, 2):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    total = successes + failures + skipped
    ws.append(["Total models", total])
    ws.append(["Succeeded", successes])
    ws.append(["Errored", failures])
    ws.append(["Skipped (downstream)", skipped])
    ws.append(["Error categories", len(category_counts)])

    # --- Errors by category ---
    ws.append([])
    ws.append(["Errors by category"])
    ws.cell(row=ws.max_row, column=1).font = section_font
    ws.append(["Category", "Count", "% of errors"])
    header_row = ws.max_row
    for col_idx in (1, 2, 3):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    sorted_cats = sorted(
        category_counts.items(), key=lambda kv: (-kv[1], kv[0])
    )
    for cat, count in sorted_cats:
        pct = (count / failures * 100) if failures else 0
        ws.append([cat, count, round(pct, 1)])
        row = ws.max_row
        color = CATEGORY_FILLS.get(cat, "FFFFFF")
        for col_idx in (1, 2, 3):
            ws.cell(row=row, column=col_idx).fill = PatternFill(
                "solid", fgColor=color
            )

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 14


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    command = build_command()

    try:
        exit_code = run_dbt(command)
    except FileNotFoundError:
        print("ERROR: 'dbt' executable not found on PATH.", file=sys.stderr)
        return 127

    print("-" * 80)
    print(f"dbt exited with code {exit_code}")

    try:
        results = load_run_results(PROJECT_DIR)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("No results found in run_results.json (nothing was selected to run).")
        return exit_code

    successes, failures, skipped, category_counts = write_excel(results, OUTPUT_XLSX)

    print(f"Report written to: {OUTPUT_XLSX.resolve()}")
    print(
        f"Summary: {successes} succeeded | {failures} failed | "
        f"{skipped} skipped | {len(results)} total"
    )
    if category_counts:
        print("Error categories:")
        for cat, count in sorted(
            category_counts.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            print(f"  {count:>3}  {cat}")

    # Non-zero exit if dbt failed or any model errored
    return 0 if failures == 0 and exit_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
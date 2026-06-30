"""
Run a dbt command and export per-model results to Excel.

How it works
------------
1. Builds and executes the dbt command (streams output to the console).
2. After dbt finishes, reads the structured `target/run_results.json`
   artifact that dbt always writes.
3. Produces an Excel file with one row per model showing the model name,
   status, execution time, and the full error message for any failure.

Requirements
------------
    pip install openpyxl
"""

from __future__ import annotations

import json
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
SELECT_TAG = "tag:run_stg_t24"

# Run-level variables passed via --vars
DBT_VARS: dict[str, str] = {
    "as_of_date":           "20260329",
    "batch_number":         "manual__2026-05-01T14:15:23.051466+00:00",
    "batch_start_date":     "2026-05-01",
    "extraction_time_slot": "4",
    "global_batch_number":  "20260329235959",
    "ingestion_ts":         "2026-05-01 14:15:20",
}

# Where to write the report (next to this script, timestamped)
OUTPUT_XLSX = Path(__file__).with_name(
    f"dbt_run_report_{datetime.now():%Y%m%d_%H%M%S}_t24.xlsx"
)


# ---------------------------------------------------------------------------
# dbt command
# ---------------------------------------------------------------------------
def build_command() -> list[str]:
    return [
        "dbt", "run",
        "--select", SELECT_TAG,
        "--vars", json.dumps(DBT_VARS),
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
    # e.g. "model.my_project.stg_t24_accounts" -> "stg_t24_accounts"
    return unique_id.split(".")[-1] if unique_id else ""


def node_kind_from(unique_id: str) -> str:
    # "model", "seed", "snapshot", "test", ...
    return unique_id.split(".")[0] if unique_id else ""


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
def write_excel(results: list[dict], output_path: Path) -> tuple[int, int, int]:
    wb = Workbook()
    ws = wb.active
    ws.title = "dbt run results"

    headers = ["#", "Type", "Model", "Status", "Succeeded?", "Execution time (s)", "Error message"]
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

        ws.append([
            idx,
            node_kind_from(unique_id),
            model_name_from(unique_id),
            status,
            succeeded,
            round(float(exec_time), 3),
            message,
        ])

        row_idx = ws.max_row
        # Highlight the status + succeeded cells
        ws.cell(row=row_idx, column=4).fill = fill
        ws.cell(row=row_idx, column=5).fill = fill

    # Column widths
    widths = [5, 10, 40, 12, 12, 18, 90]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    # Wrap the error-message column
    for row in ws.iter_rows(min_row=2, min_col=7, max_col=7):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    wb.save(output_path)
    return successes, failures, skipped


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

    successes, failures, skipped = write_excel(results, OUTPUT_XLSX)

    print(f"Report written to: {OUTPUT_XLSX.resolve()}")
    print(
        f"Summary: {successes} succeeded | {failures} failed | "
        f"{skipped} skipped | {len(results)} total"
    )

    # Non-zero exit if dbt failed or any model errored
    return 0 if failures == 0 and exit_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
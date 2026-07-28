import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOGS_DIR = r"C:\Users\anhassan\nera_automations\logs"

OUTPUT_XLSX = Path(__file__).with_name(
    f"airflow_logs_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
)

# Background fill for categories
CATEGORY_FILLS: dict[str, str] = {
    "NOT NULL constraint violation":     "E2EFDA",
    "Unique constraint violation":       "E2EFDA",
    "Invalid cast":                      "EDEDED",
    "Uncategorized":                     "FFFFFF",
}

# ---------------------------------------------------------------------------
# Error categorization
# ---------------------------------------------------------------------------
def categorize_error(message: str) -> tuple[str, str, str]:
    if not message:
        return ("", "", "")

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
            "Filter nulls in WHERE or fix mapping logic",
        )

    # ---- Unique key duplicate ----------------------------------------------
    m = re.search(
        r'duplicate key value violates unique constraint "([^"]+)".*?'
        r'Key \(([^)]+)\)=\(([^)]+)\) already exists',
        message,
        re.DOTALL,
    )
    if m:
        constraint, col, val = m.group(1), m.group(2), m.group(3)
        return (
            "Unique constraint violation",
            f"Duplicate {col}={val} for constraint {constraint}",
            "Deduplicate source or use incremental unique_key/upsert logic",
        )

    m = re.search(r'duplicate key value violates unique constraint "([^"]+)"', message)
    if m:
        constraint = m.group(1)
        return (
            "Unique constraint violation",
            f"Duplicate key for constraint {constraint}",
            "Deduplicate source or use incremental unique_key/upsert logic",
        )

    # ---- Invalid cast for a specific type ----------------------------------
    m = re.search(r'invalid input syntax for type (\S+): "([^"]+)"', message)
    if m:
        typ, val = m.group(1), m.group(2)
        return (
            "Invalid cast",
            f'Value "{val}" cannot be cast to {typ}',
            f"Remove the {typ} cast or filter non-{typ} values upstream",
        )

    return ("Uncategorized", "", "Review manually")

# ---------------------------------------------------------------------------
# Log Parsing
# ---------------------------------------------------------------------------
def parse_logs(logs_dir: str) -> list[dict]:
    results = {}
    
    for root, _, files in os.walk(logs_dir):
        for file in files:
            if not file.endswith('.log'):
                continue
                
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, logs_dir)
            parts = rel_path.split(os.sep)
            
            run_id = "unknown_run"
            task_id = "unknown_task"
            map_index = ""
            attempt = "1"
            
            for part in parts:
                if part.startswith("run_id="):
                    run_id = part.replace("run_id=", "")
                elif part.startswith("task_id="):
                    task_id = part.replace("task_id=", "")
                elif part.startswith("map_index="):
                    map_index = part.replace("map_index=", "")
                elif part.startswith("attempt="):
                    attempt = part.replace("attempt=", "").replace(".log", "")
                    
            task_key = f"{run_id}__{task_id}__{map_index}"
            
            # Skip if we already parsed a higher attempt for this task
            if task_key in results and int(attempt) < int(results[task_key].get("attempt", 0)):
                continue

            status = "success"
            error_message = ""
            table_name = ""
            exec_time_str = "0"
            
            start_time = None
            end_time = None
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            log_entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                            
                        # Extract timestamps for duration
                        ts = log_entry.get("timestamp")
                        if ts:
                            try:
                                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                if not start_time:
                                    start_time = dt
                                end_time = dt
                            except ValueError:
                                pass

                        level = log_entry.get("level", "").lower()
                        event = log_entry.get("event", "")
                        
                        # Find table name from specific log events
                        if "Map index rendered as" in event:
                            table_name = event.split("Map index rendered as")[-1].strip()
                        elif "Starting execution of" in event and "for table:" in event:
                            table_name = event.split("for table:")[-1].strip()
                            
                        if level == "error":
                            status = "failed"
                            # Avoid overwriting with generic "Task failed with exception" if we already have a detailed error
                            if "Task failed with exception" not in event or not error_message:
                                error_message = event
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                
            if start_time and end_time:
                exec_time_str = str((end_time - start_time).total_seconds())

            if not table_name:
                table_name = f"{task_id} (index: {map_index})" if map_index else task_id
                
            category, root_cause, suggested_fix = "", "", ""
            if status == "failed":
                category, root_cause, suggested_fix = categorize_error(error_message)

            results[task_key] = {
                "run_id": run_id,
                "task_id": task_id,
                "map_index": map_index,
                "attempt": attempt,
                "table_name": table_name,
                "status": status,
                "exec_time": exec_time_str,
                "error_message": error_message,
                "category": category,
                "root_cause": root_cause,
                "suggested_fix": suggested_fix
            }
            
    return list(results.values())


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
def write_excel(results: list[dict], output_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Airflow Sync Results"

    headers = [
        "#", "Run ID", "Task ID", "Table / Index", "Status", "Succeeded?", 
        "Execution time (s)", "Error message", "Category", "Root cause", "Suggested fix"
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
    category_counts: dict[str, int] = defaultdict(int)
    
    # Sort results by run_id, task_id, table_name
    results.sort(key=lambda x: (x["run_id"], x["task_id"], x["table_name"]))

    for idx, r in enumerate(results, start=1):
        status = r.get("status", "success")
        
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
            category = r.get("category", "")
            if category:
                category_counts[category] += 1

        exec_time = float(r.get("exec_time", 0))

        ws.append([
            idx,
            r.get("run_id"),
            r.get("task_id"),
            r.get("table_name"),
            status,
            succeeded,
            round(exec_time, 3),
            r.get("error_message"),
            r.get("category"),
            r.get("root_cause"),
            r.get("suggested_fix"),
        ])

        row_idx = ws.max_row
        
        # Highlight the status + succeeded cells
        ws.cell(row=row_idx, column=5).fill = fill
        ws.cell(row=row_idx, column=6).fill = fill

        # Colour the Category cell by category for error rows
        category = r.get("category")
        if category:
            color = CATEGORY_FILLS.get(category, "FFFFFF")
            ws.cell(row=row_idx, column=9).fill = PatternFill("solid", fgColor=color)

    # Column widths
    widths = [5, 30, 30, 40, 12, 12, 18, 90, 36, 50, 50]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    # Wrap the long text columns: error message, root cause, suggested fix
    for col_letter in ("H", "J", "K"):
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
):
    ws = wb.create_sheet("Summary", 0)  # insert as first sheet

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="305496")
    section_font = Font(bold=True, size=11)

    # --- Overall totals ---
    ws.append(["Airflow Run — overall results"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Metric", "Value"])
    for col_idx in (1, 2):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    total = successes + failures + skipped
    ws.append(["Total tasks", total])
    ws.append(["Succeeded", successes])
    ws.append(["Errored", failures])
    ws.append(["Skipped", skipped])
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

    sorted_cats = sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for cat, count in sorted_cats:
        pct = (count / failures * 100) if failures else 0
        ws.append([cat, count, round(pct, 1)])
        row = ws.max_row
        color = CATEGORY_FILLS.get(cat, "FFFFFF")
        for col_idx in (1, 2, 3):
            ws.cell(row=row, column=col_idx).fill = PatternFill("solid", fgColor=color)

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 14


def main():
    print(f"Parsing logs from: {LOGS_DIR}")
    results = parse_logs(LOGS_DIR)
    
    if not results:
        print("No log results found.")
        return 0

    successes, failures, skipped, category_counts = write_excel(results, OUTPUT_XLSX)

    print(f"Report written to: {OUTPUT_XLSX.resolve()}")
    print(f"Summary: {successes} succeeded | {failures} failed | {skipped} skipped | {len(results)} total")
    
    if category_counts:
        print("Error categories:")
        for cat, count in sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {count:>3}  {cat}")
            
    return 0

if __name__ == "__main__":
    sys.exit(main())

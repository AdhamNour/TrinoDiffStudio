import subprocess
import trino
import pandas as pd
import sys
import os
from datetime import datetime

# Resolve directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR) in ("scripts", "src") else SCRIPT_DIR

# Directory to store generated SQL scripts and Excel files
WORKING_DIR = os.path.join(PROJECT_ROOT, "output")

# ---------------------------------------------------------------------------
# Excel config source
# ---------------------------------------------------------------------------

def _find_excel_config() -> str:
    """Find the Excel mapping file in current or parent directory."""
    candidates = [
        os.path.join(SCRIPT_DIR, "Oracle_to_Postgre_Business_Columns 2.xlsx"),
        os.path.join(PROJECT_ROOT, "Oracle_to_Postgre_Business_Columns 2.xlsx"),
        os.path.join(os.getcwd(), "Oracle_to_Postgre_Business_Columns 2.xlsx"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[1]

EXCEL_CONFIG_PATH = _find_excel_config()


def load_tables_config_from_excel(excel_path: str) -> list:
    """Read table / column config from the Excel mapping file.

    Each unique value in "Table Name" becomes one entry in TABLES_CONFIG.
    All "Business Column" values for that table are collected as id_columns.

    Returns a list of dicts compatible with the TABLES_CONFIG format used by
    the rest of this script, e.g.:
        [
            {
                "table_name": "fct_customer_blocks",
                "id_columns": ["customer_id", "account_number", ...],
            },
            ...
        ]
    """
    if not os.path.exists(excel_path):
        print(f"[ERROR] Excel config file not found: {excel_path}")
        sys.exit(1)

    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"[ERROR] Could not read Excel file '{excel_path}': {e}")
        sys.exit(1)

    # Normalise column names so minor casing/spacing differences are tolerated
    df.columns = [c.strip() for c in df.columns]

    required_cols = {"Table Name", "Business Column"}
    missing = required_cols - set(df.columns)
    if missing:
        print(
            f"[ERROR] Excel file is missing expected column(s): {missing}\n"
            f"        Found columns: {list(df.columns)}"
        )
        sys.exit(1)

    # Drop rows where either key column is blank
    df = df.dropna(subset=["Table Name", "Business Column"])

    # Normalise values to lowercase strings and strip whitespace
    df["Table Name"]      = df["Table Name"].astype(str).str.strip().str.lower()
    df["Business Column"] = df["Business Column"].astype(str).str.strip().str.lower()

    # Group columns by table name (preserving the original order)
    tables_config = []
    seen_tables: dict = {}

    for _, row in df.iterrows():
        tbl = str(row["Table Name"]).strip().lower()
        cols_str = str(row["Business Column"]).strip()

        # Split comma-separated columns and clean up each column name
        cols = [c.strip().lower() for c in cols_str.split(",") if c.strip()]

        if tbl not in seen_tables:
            entry = {"table_name": tbl, "id_columns": []}
            tables_config.append(entry)
            seen_tables[tbl] = entry

        for col in cols:
            if col not in seen_tables[tbl]["id_columns"]:
                seen_tables[tbl]["id_columns"].append(col)

    return tables_config


TRINO_HOST = "localhost"
TRINO_PORT = 8080
TRINO_USER = "admin"

# ---------------------------------------------------------------------------
# Excel styling helpers
# ---------------------------------------------------------------------------

def _apply_header(ws, headers: list, header_fill_hex: str = "1F3864"):
    """Write and style the header row."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
        cell.fill = PatternFill("solid", fgColor=header_fill_hex)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[1].height = 30


def _style_data_rows(ws, df: pd.DataFrame):
    """
    Apply conditional colouring by row_diff_type + alternate banding,
    and a thin border on every cell.
    Highlight differing postgres_value / oracle_value cells in deep amber.
    """
    from openpyxl.styles import PatternFill, Alignment, Border, Side, Font

    DIFF_FILLS = {
        "VALUE_MISMATCH":   "FFF2CC",   # amber
        "ONLY_IN_POSTGRES": "D9E1F2",   # blue-grey
        "ONLY_IN_ORACLE":   "FCE4D6",   # salmon
    }
    BAND_EVEN = "F2F2F2"   # very light grey for alternating rows
    MISMATCH_CELL = "FFCC00"  # deep amber for differing value cells

    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    base_font = Font(name="Calibri", size=10)

    columns = list(df.columns)
    diff_type_idx  = columns.index("row_diff_type") + 1  if "row_diff_type"  in columns else None
    pg_val_idx     = columns.index("postgres_value") + 1 if "postgres_value" in columns else None
    ora_val_idx    = columns.index("oracle_value") + 1   if "oracle_value"   in columns else None

    for row_offset, row_data in enumerate(df.itertuples(index=False), start=2):
        row_dict = row_data._asdict()
        diff_type = row_dict.get("row_diff_type", "")

        if diff_type in DIFF_FILLS:
            row_fill = PatternFill("solid", fgColor=DIFF_FILLS[diff_type])
        elif row_offset % 2 == 0:
            row_fill = PatternFill("solid", fgColor=BAND_EVEN)
        else:
            row_fill = None

        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=row_offset, column=col_idx)
            cell.font = base_font
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=False)
            if row_fill:
                cell.fill = row_fill

        # Highlight mismatched value cells in deeper amber
        if diff_type == "VALUE_MISMATCH" and pg_val_idx and ora_val_idx:
            pg_val  = ws.cell(row=row_offset, column=pg_val_idx).value
            ora_val = ws.cell(row=row_offset, column=ora_val_idx).value
            if pg_val != ora_val:
                for cidx in (pg_val_idx, ora_val_idx):
                    ws.cell(row=row_offset, column=cidx).fill = \
                        PatternFill("solid", fgColor=MISMATCH_CELL)


def _auto_column_widths(ws, df: pd.DataFrame, max_width: int = 60, min_width: int = 12):
    """Set column widths based on max content length."""
    from openpyxl.utils import get_column_letter

    for col_idx, col_name in enumerate(df.columns, start=1):
        header_len = len(str(col_name))
        max_data_len = int(df[col_name].astype(str).str.len().max()) if len(df) > 0 else 0
        width = min(max(header_len, max_data_len, min_width) + 4, max_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _freeze_and_filter(ws):
    """Freeze header row and enable autofilter."""
    ws.freeze_panes = ws.cell(row=2, column=1)
    ws.auto_filter.ref = ws.dimensions


def _add_diff_legend(ws, start_row: int):
    """Add a small colour legend below the data."""
    from openpyxl.styles import PatternFill, Font, Alignment

    legend = [
        ("VALUE_MISMATCH",   "FFF2CC", "Row exists in both but at least one column differs"),
        ("ONLY_IN_POSTGRES", "D9E1F2", "Row exists only in Postgres"),
        ("ONLY_IN_ORACLE",   "FCE4D6", "Row exists only in Oracle"),
        ("Highlighted cell", "FFCC00", "Specific column value differs between sources"),
    ]

    ws.cell(row=start_row, column=1).value = "Colour Legend"
    ws.cell(row=start_row, column=1).font = Font(bold=True, name="Calibri", size=10)

    for i, (label, colour, desc) in enumerate(legend, start=start_row + 1):
        label_cell = ws.cell(row=i, column=1, value=label)
        label_cell.fill = PatternFill("solid", fgColor=colour)
        label_cell.font = Font(name="Calibri", size=10)
        label_cell.alignment = Alignment(horizontal="center")

        ws.cell(row=i, column=2, value=desc).font = Font(name="Calibri", size=10, italic=True)


# ---------------------------------------------------------------------------
# Summary sheet
# ---------------------------------------------------------------------------

def _write_summary_sheet(wb, table_name: str, df: pd.DataFrame,
                          id_cols: list, run_ts: str):
    """Create a nicely formatted Summary sheet as the first sheet."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    ws = wb.create_sheet("Summary", 0)
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 14

    TITLE_FILL = PatternFill("solid", fgColor="1F3864")
    SECT_FILL  = PatternFill("solid", fgColor="2E75B6")
    ALT_FILL   = PatternFill("solid", fgColor="EBF3FB")
    WHITE_FILL = PatternFill("solid", fgColor="FFFFFF")

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # ---- Title block ----
    ws.append([f"Diff Report - {table_name}", "", ""])
    r = ws.max_row
    ws.cell(r, 1).font = Font(bold=True, color="FFFFFF", name="Calibri", size=14)
    ws.cell(r, 1).fill = TITLE_FILL
    ws.cell(r, 1).alignment = Alignment(horizontal="left", vertical="center")
    for c in (1, 2, 3):
        ws.cell(r, c).fill = TITLE_FILL
    ws.row_dimensions[r].height = 28
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)

    ws.append([f"Generated: {run_ts}", "", ""])
    r = ws.max_row
    ws.cell(r, 1).font = Font(italic=True, name="Calibri", size=10, color="555555")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)

    ws.append(["", "", ""])  # spacer

    # ---- Overall counts ----
    total    = len(df)
    mismatch = int((df["row_diff_type"] == "VALUE_MISMATCH").sum())   if "row_diff_type" in df.columns else 0
    only_pg  = int((df["row_diff_type"] == "ONLY_IN_POSTGRES").sum()) if "row_diff_type" in df.columns else 0
    only_ora = int((df["row_diff_type"] == "ONLY_IN_ORACLE").sum())   if "row_diff_type" in df.columns else 0

    ws.append(["Overall Summary", "", ""])
    r = ws.max_row
    for c in (1, 2, 3):
        ws.cell(r, c).font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
        ws.cell(r, c).fill = SECT_FILL
    ws.row_dimensions[r].height = 20

    summary_rows = [
        ("Total diff rows",       total,    None),
        ("VALUE_MISMATCH rows",   mismatch, "FFF2CC"),
        ("ONLY_IN_POSTGRES rows", only_pg,  "D9E1F2"),
        ("ONLY_IN_ORACLE rows",   only_ora, "FCE4D6"),
    ]
    for i, (label, val, colour) in enumerate(summary_rows):
        ws.append([label, val, ""])
        r = ws.max_row
        fill = PatternFill("solid", fgColor=colour) if colour else (ALT_FILL if i % 2 == 0 else WHITE_FILL)
        ws.cell(r, 1).font = Font(name="Calibri", size=10)
        ws.cell(r, 2).font = Font(bold=True, name="Calibri", size=10)
        for c in (1, 2, 3):
            ws.cell(r, c).fill   = fill
            ws.cell(r, c).border = border

    ws.append(["", "", ""])  # spacer

    # ---- Mismatches per column ----
    if "column_name" in df.columns and total > 0:
        ws.append(["Mismatches by Column", "", ""])
        r = ws.max_row
        for c in (1, 2, 3):
            ws.cell(r, c).font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
            ws.cell(r, c).fill = SECT_FILL
        ws.row_dimensions[r].height = 20

        ws.append(["Column Name", "Diff Count", "% of Total Rows"])
        r = ws.max_row
        for c_idx, hdr in enumerate(["Column Name", "Diff Count", "% of Total Rows"], start=1):
            cell = ws.cell(r, c_idx)
            cell.value     = hdr
            cell.font      = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
            cell.fill      = PatternFill("solid", fgColor="2E75B6")
            cell.alignment = Alignment(horizontal="center")
            cell.border    = border

        col_counts = (
            df[df["row_diff_type"] == "VALUE_MISMATCH"]["column_name"]
            .value_counts()
            .reset_index()
        )
        col_counts.columns = ["column_name", "count"]

        for i, row in col_counts.iterrows():
            pct = round(row["count"] / total * 100, 1) if total else 0
            fill = ALT_FILL if i % 2 == 0 else WHITE_FILL
            ws.append([row["column_name"], int(row["count"]), f"{pct}%"])
            r = ws.max_row
            ws.cell(r, 1).font = Font(name="Calibri", size=10)
            ws.cell(r, 2).font = Font(bold=True, name="Calibri", size=10)
            ws.cell(r, 3).font = Font(name="Calibri", size=10)
            ws.cell(r, 2).alignment = Alignment(horizontal="center")
            ws.cell(r, 3).alignment = Alignment(horizontal="center")
            for c in (1, 2, 3):
                ws.cell(r, c).fill   = fill
                ws.cell(r, c).border = border

    ws.append(["", "", ""])  # spacer

    # ---- Composite key columns used ----
    ws.append(["Composite Key Columns", "", ""])
    r = ws.max_row
    for c in (1, 2, 3):
        ws.cell(r, c).font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
        ws.cell(r, c).fill = SECT_FILL
    ws.row_dimensions[r].height = 20

    for i, col in enumerate(id_cols):
        fill = ALT_FILL if i % 2 == 0 else WHITE_FILL
        ws.append([col, "", ""])
        r = ws.max_row
        ws.cell(r, 1).font  = Font(name="Calibri", size=10)
        for c in (1, 2, 3):
            ws.cell(r, c).fill   = fill
            ws.cell(r, c).border = border


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def _write_missing_records_sheet(wb, sheet_name: str, df_missing: pd.DataFrame,
                                  id_cols: list, fill_hex: str):
    """Create a sheet listing records that exist only in one source.

    Only the composite key columns are shown -- column_name / postgres_value /
    oracle_value are NULL for these rows and are therefore omitted.
    """
    from openpyxl.styles import PatternFill, Alignment, Border, Side, Font

    ws = wb.create_sheet(sheet_name)

    if df_missing.empty:
        ws.append([f"No {sheet_name} records found."])
        ws.cell(1, 1).font = Font(italic=True, name="Calibri", size=10)
        return

    # Show only the key columns
    display_cols = [c for c in id_cols if c in df_missing.columns]
    _apply_header(ws, display_cols, header_fill_hex=fill_hex)

    row_fill = PatternFill("solid", fgColor="FCE4D6" if "ORACLE" in sheet_name else "D9E1F2")
    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    base_font = Font(name="Calibri", size=10)

    for row_tuple in df_missing[display_cols].itertuples(index=False):
        ws.append(list(row_tuple))

    for row_idx in range(2, len(df_missing) + 2):
        for col_idx in range(1, len(display_cols) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = base_font
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=False)
            cell.fill = row_fill

    _auto_column_widths(ws, df_missing[display_cols])
    _freeze_and_filter(ws)


def export_diff_to_excel(df: pd.DataFrame, xlsx_file: str,
                         table_name: str, id_cols: list):
    """Write the diff DataFrame to a styled Excel workbook."""
    from openpyxl import Workbook

    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    wb = Workbook()

    # Summary sheet (position 0)
    _write_summary_sheet(wb, table_name, df, id_cols, run_ts)

    # Diff data sheet (VALUE_MISMATCH rows, expanded per-column)
    ws = wb.create_sheet("Diff Data")

    headers = list(df.columns)
    _apply_header(ws, headers)

    for row_tuple in df.itertuples(index=False):
        ws.append(list(row_tuple))

    _style_data_rows(ws, df)
    _auto_column_widths(ws, df)
    _freeze_and_filter(ws)

    # Colour legend below data (2-row gap)
    _add_diff_legend(ws, len(df) + 4)

    # Dedicated sheets for missing records
    df_only_oracle   = df[df["row_diff_type"] == "ONLY_IN_ORACLE"].copy()
    df_only_postgres = df[df["row_diff_type"] == "ONLY_IN_POSTGRES"].copy()

    _write_missing_records_sheet(wb, "ONLY_IN_ORACLE",   df_only_oracle,   id_cols, "C00000")
    _write_missing_records_sheet(wb, "ONLY_IN_POSTGRES", df_only_postgres, id_cols, "2E75B6")

    # Remove default blank sheet created by openpyxl
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    wb.active = wb["Summary"]
    wb.save(xlsx_file)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    os.makedirs(WORKING_DIR, exist_ok=True)
    print(f"Working directory for output files: {WORKING_DIR}")
    print("Checking dependencies...")
    try:
        import openpyxl
    except ImportError:
        print("[ERROR] 'openpyxl' is required to export to Excel.")
        print("        Install it using: pip install openpyxl pandas trino")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Load TABLES_CONFIG dynamically from the Excel mapping file
    # -----------------------------------------------------------------------
    print(f"Loading table/column config from: {EXCEL_CONFIG_PATH}")
    TABLES_CONFIG = load_tables_config_from_excel(EXCEL_CONFIG_PATH)

    if not TABLES_CONFIG:
        print("[ERROR] No table configurations found in the Excel file. Exiting.")
        sys.exit(1)

    print(f"Found {len(TABLES_CONFIG)} table(s) to process:")
    for cfg in TABLES_CONFIG:
        print(f"  * {cfg['table_name']}  ({len(cfg['id_columns'])} id column(s))")

    # -----------------------------------------------------------------------
    # Connect to Trino
    # -----------------------------------------------------------------------
    print(f"\nConnecting to Trino at {TRINO_HOST}:{TRINO_PORT}...")
    try:
        conn = trino.dbapi.connect(
            host=TRINO_HOST,
            port=TRINO_PORT,
            user=TRINO_USER,
            http_scheme="http",
        )
    except Exception as e:
        print(f"[ERROR] Failed to connect to Trino: {e}")
        sys.exit(1)

    for config in TABLES_CONFIG:
        table_name = config["table_name"].lower()
        raw_id_cols = config.get("id_columns") or config.get("id_column")
        if isinstance(raw_id_cols, str):
            id_cols = [raw_id_cols.lower()]
        else:
            id_cols = [c.lower() for c in raw_id_cols]

        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = table_name.replace(".", "_")
        sql_file = f"{clean_name}_diff.sql"
        xlsx_file = os.path.join(WORKING_DIR, f"{clean_name}_diff_{run_ts}.xlsx")

        print(f"\n=============================================")
        print(f"Processing: {table_name}")
        print(f"=============================================")
        print(f"[{table_name}] Generating SQL query...")

        cmd = [
            sys.executable, os.path.join(SCRIPT_DIR, "generate_trino_diff.py"),
            "--table-name", table_name,
        ]
        for col in id_cols:
            cmd.extend(["--id-column", col])

        cmd.extend([
            "--exclude-columns", "extraction_timestamp",
            "--exclude-suffix", "key",
            "--trim-strings",
            "--output", os.path.join(WORKING_DIR, sql_file)
        ])

        try:
            subprocess.run(cmd, check=True, cwd=SCRIPT_DIR)
        except subprocess.CalledProcessError:
            print(f"[ERROR] Failed to generate SQL for {table_name}. Skipping.")
            continue

        print(f"[{table_name}] Executing query on Trino...")
        sql_path = os.path.join(WORKING_DIR, sql_file)
        with open(sql_path, "r", encoding="utf-8") as f:
            query = f.read()

        # Trino REST API rejects queries with trailing semicolons
        query = query.strip().rstrip(';')

        cursor = conn.cursor()
        try:
            cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            df = pd.DataFrame(rows, columns=columns)

            print(f"[{table_name}] Saving {len(df)} records to {xlsx_file}...")
            export_diff_to_excel(df, xlsx_file, table_name, id_cols)
            print(f"[{table_name}] Done! -> {xlsx_file}")

        except Exception as e:
            print(f"[ERROR] Trino execution or Excel export failed for {table_name}:\n{e}")
        finally:
            try:
                cursor.cancel()
            except Exception:
                pass
            cursor.close()


if __name__ == "__main__":
    main()

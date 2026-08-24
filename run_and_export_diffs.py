import subprocess
import trino
import pandas as pd
import sys
import os
from datetime import datetime

# Resolve the directory where this script lives so subprocess can always find
# generate_trino_diff.py regardless of the working directory the user launches from.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory to store generated SQL scripts and Excel files
WORKING_DIR = os.path.join(SCRIPT_DIR, "output")

# Based on the configuration provided, the tables and their ID columns
# Supports single string id_column or list of id_columns for composite keys
TABLES_CONFIG = [
    {
        "table_name": "fct_customer_blocks",
        "id_columns": [
            "customer_id",
            "account_number",
            "block_code",
            "system_name",
            "block_type",
            "entry_sequence",
        ],
    },
]

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

    if df.empty or len(df.columns) == 0:
        return
    for col_idx, col_name in enumerate(df.columns, start=1):
        header_len = len(str(col_name))
        try:
            lens = df[col_name].dropna().astype(str).str.len()
            max_val = lens.max() if len(lens) > 0 else 0
            max_data_len = int(max_val) if pd.notna(max_val) else 0
        except Exception:
            max_data_len = 0
        width = min(max(header_len, max_data_len, min_width) + 4, max_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _freeze_and_filter(ws):
    """Freeze header row and enable autofilter."""
    ws.freeze_panes = ws.cell(row=2, column=1)
    ws.auto_filter.ref = ws.dimensions


def _add_diff_legend(ws, start_row: int, source_catalog: str = "postgres", target_catalog: str = "oracle"):
    """Add a small colour legend below the data."""
    from openpyxl.styles import PatternFill, Font, Alignment

    src_desc = f"Row exists only in {source_catalog}" if source_catalog else "Row exists only in Source"
    tgt_desc = f"Row exists only in {target_catalog}" if target_catalog else "Row exists only in Target"

    legend = [
        ("VALUE_MISMATCH",   "FFF2CC", "Row exists in both but at least one column differs"),
        ("ONLY_IN_SOURCE",   "D9E1F2", src_desc),
        ("ONLY_IN_TARGET",   "FCE4D6", tgt_desc),
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
                          id_cols: list, run_ts: str,
                          source_catalog: str = "postgres", target_catalog: str = "oracle"):
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
    ws.append([f"Diff Report — {table_name}", "", ""])
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
    only_src = int((df["row_diff_type"].isin(["ONLY_IN_SOURCE", "ONLY_IN_POSTGRES"])).sum()) if "row_diff_type" in df.columns else 0
    only_tgt = int((df["row_diff_type"].isin(["ONLY_IN_TARGET", "ONLY_IN_ORACLE"])).sum())   if "row_diff_type" in df.columns else 0

    ws.append(["Overall Summary", "", ""])
    r = ws.max_row
    for c in (1, 2, 3):
        ws.cell(r, c).font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
        ws.cell(r, c).fill = SECT_FILL
    ws.row_dimensions[r].height = 20

    src_label = f"ONLY_IN_{source_catalog.upper()} rows" if source_catalog else "ONLY_IN_SOURCE rows"
    tgt_label = f"ONLY_IN_{target_catalog.upper()} rows" if target_catalog else "ONLY_IN_TARGET rows"

    summary_rows = [
        ("Total diff rows",       total,    None),
        ("VALUE_MISMATCH rows",   mismatch, "FFF2CC"),
        (src_label,               only_src, "D9E1F2"),
        (tgt_label,               only_tgt, "FCE4D6"),
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

        mismatch_df = df[df["row_diff_type"] == "VALUE_MISMATCH"]
        if not mismatch_df.empty:
            col_counts = (
                mismatch_df["column_name"]
                .dropna()
                .value_counts()
                .reset_index()
            )
            col_counts.columns = ["column_name", "count"]

            for i, row in col_counts.iterrows():
                cnt  = int(row["count"])
                pct  = round(cnt / total * 100, 1) if total else 0
                fill = ALT_FILL if i % 2 == 0 else WHITE_FILL

                ws.append([str(row["column_name"]), cnt, f"{pct}%"])
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

    # ---- Composite Key Columns ----
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
        ws.cell(r, 1).font = Font(name="Calibri", size=10)
        for c in (1, 2, 3):
            ws.cell(r, c).fill   = fill
            ws.cell(r, c).border = border


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def _write_missing_records_sheet(wb, sheet_name: str, df_missing: pd.DataFrame,
                                  id_cols: list, fill_hex: str, is_target: bool = False):
    """Create a sheet listing records that exist only in one source.

    Only the composite key columns are shown — column_name / postgres_value /
    oracle_value are NULL for these rows and are therefore omitted.
    """
    from openpyxl.styles import PatternFill, Alignment, Border, Side, Font

    safe_name = "".join(c for c in str(sheet_name) if c not in r'\/*?:[]')[:31].strip() or ("ONLY_IN_TARGET" if is_target else "ONLY_IN_SOURCE")
    if safe_name in wb.sheetnames:
        safe_name = f"{safe_name}_tgt" if is_target else f"{safe_name}_src"
        safe_name = safe_name[:31]

    ws = wb.create_sheet(safe_name)

    if df_missing.empty:
        ws.append([f"No {safe_name} records found."])
        ws.cell(1, 1).font = Font(italic=True, name="Calibri", size=10)
        return

    # Show only the key columns
    display_cols = [c for c in id_cols if c in df_missing.columns]
    if not display_cols:
        ws.append([f"No {safe_name} records found."])
        ws.cell(1, 1).font = Font(italic=True, name="Calibri", size=10)
        return

    _apply_header(ws, display_cols, header_fill_hex=fill_hex)

    row_fill = PatternFill("solid", fgColor="FCE4D6" if is_target else "D9E1F2")
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
                         table_name: str, id_cols: list,
                         source_catalog: str = "postgres", target_catalog: str = "oracle"):
    """Write the diff DataFrame to a styled Excel workbook."""
    from openpyxl import Workbook

    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    wb = Workbook()

    # Summary sheet (position 0)
    _write_summary_sheet(wb, table_name, df, id_cols, run_ts, source_catalog=source_catalog, target_catalog=target_catalog)

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
    _add_diff_legend(ws, len(df) + 4, source_catalog=source_catalog, target_catalog=target_catalog)

    # Dedicated sheets for missing records
    df_only_target = df[df["row_diff_type"].isin(["ONLY_IN_TARGET", "ONLY_IN_ORACLE"])].copy()
    df_only_source = df[df["row_diff_type"].isin(["ONLY_IN_SOURCE", "ONLY_IN_POSTGRES"])].copy()

    tgt_sheet = f"ONLY_IN_{target_catalog.upper().strip()}" if target_catalog else "ONLY_IN_TARGET"
    src_sheet = f"ONLY_IN_{source_catalog.upper().strip()}" if source_catalog else "ONLY_IN_SOURCE"
    if tgt_sheet.lower() == src_sheet.lower():
        tgt_sheet = f"{tgt_sheet}_TARGET"
        src_sheet = f"{src_sheet}_SOURCE"

    _write_missing_records_sheet(wb, tgt_sheet, df_only_target, id_cols, "C00000", is_target=True)
    _write_missing_records_sheet(wb, src_sheet, df_only_source, id_cols, "2E75B6", is_target=False)

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

    print(f"Connecting to Trino at {TRINO_HOST}:{TRINO_PORT}...")
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
            "--engine", "direct",
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
            print(f"[{table_name}] Done! → {xlsx_file}")

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

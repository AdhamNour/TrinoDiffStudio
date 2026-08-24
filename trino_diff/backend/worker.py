import os
import sys
import time
from datetime import datetime
import pandas as pd
from PySide6.QtCore import QObject, Signal, Slot

# Add project root to path so we can import generate_trino_diff and helpers
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
TRINO_DIFF_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(TRINO_DIFF_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import generate_trino_diff
from trino_diff.backend.trino_client import get_trino_connection
from trino_diff.backend.db_manager import DatabaseManager


# ---------------------------------------------------------------------------
# Excel styling helpers
# ---------------------------------------------------------------------------

def _apply_header(ws, headers: list, header_fill_hex: str = "1F3864"):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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
    from openpyxl.styles import PatternFill, Alignment, Border, Side, Font
    DIFF_FILLS = {
        "VALUE_MISMATCH":   "FFF2CC",
        "ONLY_IN_POSTGRES": "D9E1F2",
        "ONLY_IN_ORACLE":   "FCE4D6",
        "ONLY_IN_SOURCE":   "D9E1F2",
        "ONLY_IN_TARGET":   "FCE4D6",
    }
    BAND_EVEN = "F2F2F2"
    MISMATCH_CELL = "FFCC00"

    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    base_font = Font(name="Calibri", size=10)

    columns = list(df.columns)
    diff_type_idx  = columns.index("row_diff_type") + 1 if "row_diff_type" in columns else None
    pg_val_idx     = columns.index("postgres_value") + 1 if "postgres_value" in columns else None
    ora_val_idx    = columns.index("oracle_value") + 1 if "oracle_value" in columns else None

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

        if diff_type == "VALUE_MISMATCH" and pg_val_idx and ora_val_idx:
            pg_val  = ws.cell(row=row_offset, column=pg_val_idx).value
            ora_val = ws.cell(row=row_offset, column=ora_val_idx).value
            if pg_val != ora_val:
                for cidx in (pg_val_idx, ora_val_idx):
                    ws.cell(row=row_offset, column=cidx).fill = PatternFill("solid", fgColor=MISMATCH_CELL)


def _auto_column_widths(ws, df: pd.DataFrame, max_width: int = 60, min_width: int = 12):
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
    ws.freeze_panes = ws.cell(row=2, column=1)
    ws.auto_filter.ref = ws.dimensions


def _add_diff_legend(ws, start_row: int, source_catalog: str = "source", target_catalog: str = "target"):
    from openpyxl.styles import PatternFill, Font, Alignment
    src_desc = f"Row exists only in {source_catalog} catalog" if source_catalog else "Row exists only in Source catalog"
    tgt_desc = f"Row exists only in {target_catalog} catalog" if target_catalog else "Row exists only in Target catalog"
    src_code = f"ONLY_IN_{source_catalog.upper().strip()}" if source_catalog else "ONLY_IN_SOURCE"
    tgt_code = f"ONLY_IN_{target_catalog.upper().strip()}" if target_catalog else "ONLY_IN_TARGET"
    legend = [
        ("VALUE_MISMATCH",   "FFF2CC", "Row exists in both but at least one column differs"),
        (src_code,           "D9E1F2", src_desc),
        (tgt_code,           "FCE4D6", tgt_desc),
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


def _safe_int(val, default: int = 0) -> int:
    try:
        if pd.isna(val):
            return default
        return int(val)
    except Exception:
        return default


def _write_summary_sheet(wb, table_name: str, df: pd.DataFrame, id_cols: list, run_ts: str,
                         source_catalog: str = "source", target_catalog: str = "target"):
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

    ws.append([f"Diff Report - {table_name}", "", ""])
    r = ws.max_row
    ws.cell(r, 1).font = Font(bold=True, color="FFFFFF", name="Calibri", size=14)
    ws.cell(r, 1).fill = TITLE_FILL
    for c in (1, 2, 3):
        ws.cell(r, c).fill = TITLE_FILL
    ws.row_dimensions[r].height = 28
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)

    ws.append([f"Generated: {run_ts}", "", ""])
    r = ws.max_row
    ws.cell(r, 1).font = Font(italic=True, name="Calibri", size=10, color="555555")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    ws.append(["", "", ""])

    total    = len(df)
    mismatch = _safe_int((df["row_diff_type"] == "VALUE_MISMATCH").sum()) if "row_diff_type" in df.columns else 0
    only_src = _safe_int((df["row_diff_type"].isin(["ONLY_IN_SOURCE", "ONLY_IN_POSTGRES"])).sum()) if "row_diff_type" in df.columns else 0
    only_tgt = _safe_int((df["row_diff_type"].isin(["ONLY_IN_TARGET", "ONLY_IN_ORACLE"])).sum()) if "row_diff_type" in df.columns else 0

    ws.append(["Overall Summary", "", ""])
    r = ws.max_row
    for c in (1, 2, 3):
        ws.cell(r, c).font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
        ws.cell(r, c).fill = SECT_FILL
    ws.row_dimensions[r].height = 20

    src_label = f"ONLY_IN_{source_catalog.upper().strip()} rows" if source_catalog else "ONLY_IN_SOURCE rows"
    tgt_label = f"ONLY_IN_{target_catalog.upper().strip()} rows" if target_catalog else "ONLY_IN_TARGET rows"

    summary_rows = [
        ("Total diff rows",      total,    None),
        ("VALUE_MISMATCH rows",  mismatch, "FFF2CC"),
        (src_label,              only_src, "D9E1F2"),
        (tgt_label,              only_tgt, "FCE4D6"),
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

    ws.append(["", "", ""])

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
                cnt = _safe_int(row["count"])
                pct = round(cnt / total * 100, 1) if total else 0
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

    ws.append(["", "", ""])
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


def _write_missing_records_sheet(wb, sheet_name: str, df_missing: pd.DataFrame, id_cols: list, fill_hex: str, is_target: bool = False):
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


def export_diff_to_excel(df: pd.DataFrame, xlsx_file: str, table_name: str, id_cols: list,
                         source_catalog: str = "postgres", target_catalog: str = "oracle"):
    from openpyxl import Workbook
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    wb = Workbook()
    _write_summary_sheet(wb, table_name, df, id_cols, run_ts, source_catalog=source_catalog, target_catalog=target_catalog)

    ws = wb.create_sheet("Diff Data")
    headers = list(df.columns)
    _apply_header(ws, headers)

    for row_tuple in df.itertuples(index=False):
        ws.append(list(row_tuple))

    _style_data_rows(ws, df)
    _auto_column_widths(ws, df)
    _freeze_and_filter(ws)
    _add_diff_legend(ws, len(df) + 4, source_catalog=source_catalog, target_catalog=target_catalog)

    df_only_target = df[df["row_diff_type"].isin(["ONLY_IN_TARGET", "ONLY_IN_ORACLE"])].copy()
    df_only_source = df[df["row_diff_type"].isin(["ONLY_IN_SOURCE", "ONLY_IN_POSTGRES"])].copy()

    tgt_sheet = f"ONLY_IN_{target_catalog.upper().strip()}" if target_catalog else "ONLY_IN_TARGET"
    src_sheet = f"ONLY_IN_{source_catalog.upper().strip()}" if source_catalog else "ONLY_IN_SOURCE"
    if tgt_sheet.lower() == src_sheet.lower():
        tgt_sheet = f"{tgt_sheet}_TARGET"
        src_sheet = f"{src_sheet}_SOURCE"

    _write_missing_records_sheet(wb, tgt_sheet, df_only_target, id_cols, "C00000", is_target=True)
    _write_missing_records_sheet(wb, src_sheet, df_only_source, id_cols, "2E75B6", is_target=False)

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    wb.active = wb["Summary"]
    wb.save(xlsx_file)


MAX_EXCEL_ROWS = 1048576


def export_diff_to_parquet(df: pd.DataFrame, parquet_file: str, table_name: str, id_cols: list):
    """
    Export DataFrame to Apache Parquet format for large datasets exceeding Excel's 1,048,576 row limit.
    """
    try:
        df.to_parquet(parquet_file, index=False)
    except Exception as e:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            table = pa.Table.from_pandas(df)
            pq.write_table(table, parquet_file)
        except Exception as pa_err:
            raise RuntimeError(f"Could not export Parquet file: {e}. (PyArrow error: {pa_err})")


# ---------------------------------------------------------------------------
# Worker Object
# ---------------------------------------------------------------------------

class TrinoDiffWorker(QObject):
    """
    Background worker executed inside a QThread for processing batch diffs or single table diffs.
    """
    logEmitted = Signal(str, str)             # (level, message)
    progressUpdated = Signal(int, int, str)   # (current, total, current_table_name)
    tableStatusUpdated = Signal(str, str, int)# (table_name, status, diff_count)
    tableFinished = Signal(str, str, str)     # (table_name, sql_file, xlsx_file)
    tableErrorOccurred = Signal(str, str, str)# (table_name, error_message, failed_query)
    allFinished = Signal(int, int)            # (success_count, error_count)

    def __init__(self, tasks: list, config: dict, batch_id: str = "", batch_type: str = "BATCH"):
        super().__init__()
        self.tasks = tasks
        self.config = config
        self.batch_id = batch_id or f"BATCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.batch_type = batch_type
        self._is_cancelled = False
        self.db = DatabaseManager()

    def cancel(self):
        self._is_cancelled = True

    @Slot()
    def run(self):
        host = self.config.get("trino_host", "localhost")
        port = int(self.config.get("trino_port", 8080))
        user = self.config.get("trino_user", "admin")
        scheme = self.config.get("http_scheme", "http")
        source_catalog = self.config.get("source_catalog", "postgres")
        target_catalog = self.config.get("target_catalog", "oracle")
        output_dir = self.config.get("output_dir", os.path.join(PROJECT_ROOT, "output"))
        exclude_columns = self.config.get("exclude_columns", "")
        exclude_suffix = self.config.get("exclude_suffix", "")
        trim_strings = self.config.get("trim_strings", True)

        os.makedirs(output_dir, exist_ok=True)

        self.logEmitted.emit("INFO", f"Starting execution for {len(self.tasks)} table(s) [Batch: {self.batch_id}]")
        self.logEmitted.emit("INFO", f"Trino: {host}:{port} ({user}) | Catalogs: {source_catalog} -> {target_catalog}")

        total_tasks = len(self.tasks)
        self.db.create_batch(
            batch_id=self.batch_id,
            batch_type=self.batch_type,
            source_catalog=source_catalog,
            target_catalog=target_catalog,
            output_dir=output_dir,
            total_tables=total_tasks,
            excel_path=self.config.get("excel_path", ""),
            config_snapshot=self.config
        )

        try:
            conn = get_trino_connection(host=host, port=port, user=user, http_scheme=scheme)
        except Exception as e:
            self.logEmitted.emit("ERROR", f"Failed to connect to Trino: {e}")
            self.db.finish_batch(self.batch_id, "FAILED", 0, total_tasks, 0)
            self.allFinished.emit(0, len(self.tasks))
            return

        success_count = 0
        error_count = 0
        total_diffs = 0

        diff_engine = self.config.get("diff_engine", "iceberg").lower()
        iceberg_catalog = self.config.get("iceberg_catalog", "iceberg")
        iceberg_staging_schema = self.config.get("iceberg_staging_schema", "staging")
        iceberg_cleanup_on_error = self.config.get("iceberg_cleanup_on_error", True)

        self.logEmitted.emit("INFO", f"Engine: {diff_engine.upper()} | Trino: {host}:{port} ({user}) | Catalogs: {source_catalog} -> {target_catalog}")
        if diff_engine == "iceberg":
            self.logEmitted.emit("INFO", f"Iceberg Staging Target: {iceberg_catalog}.{iceberg_staging_schema}")

        total_tasks = len(self.tasks)
        self.db.create_batch(
            batch_id=self.batch_id,
            batch_type=self.batch_type,
            source_catalog=source_catalog,
            target_catalog=target_catalog,
            output_dir=output_dir,
            total_tables=total_tasks,
            excel_path=self.config.get("excel_path", ""),
            config_snapshot=self.config
        )

        try:
            conn = get_trino_connection(host=host, port=port, user=user, http_scheme=scheme)
        except Exception as e:
            self.logEmitted.emit("ERROR", f"Failed to connect to Trino: {e}")
            self.db.finish_batch(self.batch_id, "FAILED", 0, total_tasks, 0)
            self.allFinished.emit(0, len(self.tasks))
            return

        success_count = 0
        error_count = 0
        total_diffs = 0

        exclude_cols = [c.strip().lower() for c in exclude_columns.split(",") if c.strip()]
        exclude_suf = exclude_suffix.strip().lower() or None

        for idx, task in enumerate(self.tasks, start=1):
            if self._is_cancelled:
                self.logEmitted.emit("WARN", "Batch execution stopped by user.")
                break

            table_name = task["table_name"]
            id_cols = task.get("id_columns", [])
            schema_override = task.get("schema", None)
            tbl_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.progressUpdated.emit(idx, total_tasks, table_name)
            self.tableStatusUpdated.emit(table_name, "Running", 0)
            self.logEmitted.emit("INFO", f"[{idx}/{total_tasks}] Processing table: {table_name}")

            clean_name = table_name.replace(".", "_")
            run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            sql_file = os.path.join(output_dir, f"{clean_name}_diff.sql")
            query = ""
            created_temp_tables = []

            try:
                cursor = conn.cursor()

                # Fetch column metadata from source and target
                pg_schema, pg_cols = generate_trino_diff.fetch_columns(cursor, source_catalog, table_name, schema_override)
                ora_schema, ora_cols = generate_trino_diff.fetch_columns(cursor, target_catalog, table_name, schema_override)

                if not pg_cols:
                    raise ValueError(f"Table '{source_catalog}.{schema_override or 'curated/rdm'}.{table_name}' returned no columns.")
                if not ora_cols:
                    raise ValueError(f"Table '{target_catalog}.{schema_override or 'curated/rdm'}.{table_name}' returned no columns.")

                pg_name_map = {c["name"]: c for c in pg_cols}
                ora_name_map = {c["name"]: c for c in ora_cols}
                id_col_set = set(id_cols)
                common_names = sorted((set(pg_name_map.keys()) & set(ora_name_map.keys())) - id_col_set)

                if not common_names:
                    raise ValueError(f"No common columns found between {source_catalog} and {target_catalog} after excluding ID columns.")

                common_col_meta = [{"name": n, "data_type": pg_name_map[n]["data_type"]} for n in common_names]

                # Enable session spill-to-disk
                try:
                    cursor.execute("SET SESSION spill_enabled = true")
                except Exception as _spill_err:
                    self.logEmitted.emit("WARN", f"[{table_name}] Could not set session spill_enabled: {_spill_err}")

                df = pd.DataFrame()

                if diff_engine == "iceberg":
                    # =========================================================
                    # ICEBERG STAGED MULTI-QUERY BREAKDOWN PIPELINE
                    # =========================================================
                    run_id = f"{int(time.time())}_{idx}"
                    src_temp, tgt_temp, mismatch_temp = generate_trino_diff.build_iceberg_stage_table_names(table_name, run_id)
                    created_temp_tables = [src_temp, tgt_temp, mismatch_temp]

                    # Save full multi-stage SQL plan to output file
                    query = generate_trino_diff.build_iceberg_pipeline_preview_sql(
                        table_name=table_name,
                        id_columns=id_cols,
                        common_col_meta=common_col_meta,
                        exclude_cols=exclude_cols,
                        exclude_suffix=exclude_suf,
                        trim_strings=trim_strings,
                        pg_schema=pg_schema,
                        ora_schema=ora_schema,
                        source_catalog=source_catalog,
                        target_catalog=target_catalog,
                        iceberg_catalog=iceberg_catalog,
                        iceberg_schema=iceberg_staging_schema,
                        run_id=run_id,
                    )
                    with open(sql_file, "w", encoding="utf-8") as f:
                        f.write(query)

                    self.db.record_output_file(self.batch_id, table_name, sql_file, "SQL")
                    self.logEmitted.emit("INFO", f"[{table_name}] Generated Iceberg Plan → {os.path.basename(sql_file)}")

                    # Ensure staging schema exists in Iceberg catalog
                    try:
                        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {iceberg_catalog}.{iceberg_staging_schema}")
                    except Exception as _sch_err:
                        self.logEmitted.emit("DEBUG", f"[{table_name}] Schema check ({iceberg_catalog}.{iceberg_staging_schema}): {_sch_err}")

                    # Stage 1A: Ingest Source into Iceberg Staging
                    self.logEmitted.emit("INFO", f"[{table_name}] [Stage 1A/4] Ingesting {source_catalog} -> {iceberg_catalog}.{iceberg_staging_schema}.{src_temp}...")
                    q_src_ctas = generate_trino_diff.build_iceberg_stage1_ctas(
                        catalog=source_catalog, schema=pg_schema, table_name=table_name,
                        id_columns=id_cols, common_col_meta=common_col_meta, trim_strings=trim_strings,
                        iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_staging_schema, target_temp_table=src_temp
                    )
                    try:
                        cursor.execute(q_src_ctas.strip().rstrip(';'))
                    except Exception as _ctas_err:
                        if "No factory for location" in str(_ctas_err) or "file:" in str(_ctas_err):
                            self.logEmitted.emit("ERROR", f"[{table_name}] Trino Iceberg Server Configuration Error: Trino cannot write to local file path without 'fs.native-local.enabled=true' in {iceberg_catalog}.properties on the Trino server.")
                        raise

                    # Stage 1B: Ingest Target into Iceberg Staging
                    if self._is_cancelled:
                        raise InterruptedError("Execution cancelled by user.")
                    self.logEmitted.emit("INFO", f"[{table_name}] [Stage 1B/4] Ingesting {target_catalog} -> {iceberg_catalog}.{iceberg_staging_schema}.{tgt_temp}...")
                    q_tgt_ctas = generate_trino_diff.build_iceberg_stage1_ctas(
                        catalog=target_catalog, schema=ora_schema, table_name=table_name,
                        id_columns=id_cols, common_col_meta=common_col_meta, trim_strings=trim_strings,
                        iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_staging_schema, target_temp_table=tgt_temp
                    )
                    cursor.execute(q_tgt_ctas.strip().rstrip(';'))

                    # Stage 2A: Query ONLY_IN_SOURCE
                    if self._is_cancelled:
                        raise InterruptedError("Execution cancelled by user.")
                    self.logEmitted.emit("INFO", f"[{table_name}] [Stage 2A/4] Checking for ONLY_IN_SOURCE records...")
                    q_mis_src = generate_trino_diff.build_iceberg_stage2_missing_keys(
                        id_columns=id_cols, iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_staging_schema,
                        src_temp_tbl=src_temp, tgt_temp_tbl=tgt_temp, diff_type="ONLY_IN_SOURCE"
                    )
                    cursor.execute(q_mis_src.strip().rstrip(';'))
                    col_names = [d[0] for d in cursor.description]
                    _chunks = []
                    while True:
                        _batch = cursor.fetchmany(5000)
                        if not _batch:
                            break
                        _chunks.append(pd.DataFrame(_batch, columns=col_names))
                    df_only_src = pd.concat(_chunks, ignore_index=True) if _chunks else pd.DataFrame(columns=col_names)
                    self.logEmitted.emit("INFO", f"[{table_name}] Found {len(df_only_src)} ONLY_IN_SOURCE record(s)")

                    # Stage 2B: Query ONLY_IN_TARGET
                    if self._is_cancelled:
                        raise InterruptedError("Execution cancelled by user.")
                    self.logEmitted.emit("INFO", f"[{table_name}] [Stage 2B/4] Checking for ONLY_IN_TARGET records...")
                    q_mis_tgt = generate_trino_diff.build_iceberg_stage2_missing_keys(
                        id_columns=id_cols, iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_staging_schema,
                        src_temp_tbl=src_temp, tgt_temp_tbl=tgt_temp, diff_type="ONLY_IN_TARGET"
                    )
                    cursor.execute(q_mis_tgt.strip().rstrip(';'))
                    col_names = [d[0] for d in cursor.description]
                    _chunks = []
                    while True:
                        _batch = cursor.fetchmany(5000)
                        if not _batch:
                            break
                        _chunks.append(pd.DataFrame(_batch, columns=col_names))
                    df_only_tgt = pd.concat(_chunks, ignore_index=True) if _chunks else pd.DataFrame(columns=col_names)
                    self.logEmitted.emit("INFO", f"[{table_name}] Found {len(df_only_tgt)} ONLY_IN_TARGET record(s)")

                    # Stage 3: Isolate Mismatches by Row Checksum Hash
                    if self._is_cancelled:
                        raise InterruptedError("Execution cancelled by user.")
                    self.logEmitted.emit("INFO", f"[{table_name}] [Stage 3/4] Isolating value mismatches via row hash checksums...")
                    q_mismatch_ctas = generate_trino_diff.build_iceberg_stage3_mismatch_keys_ctas(
                        id_columns=id_cols, iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_staging_schema,
                        src_temp_tbl=src_temp, tgt_temp_tbl=tgt_temp, mismatch_temp_tbl=mismatch_temp
                    )
                    cursor.execute(q_mismatch_ctas.strip().rstrip(';'))

                    # Stage 4: Targeted Column UNNEST (Only on Mismatched Keys)
                    if self._is_cancelled:
                        raise InterruptedError("Execution cancelled by user.")
                    self.logEmitted.emit("INFO", f"[{table_name}] [Stage 4/4] Unnesting columns for differing records only...")
                    q_unnest = generate_trino_diff.build_iceberg_stage4_mismatch_unnest(
                        id_columns=id_cols, common_col_meta=common_col_meta, exclude_cols=exclude_cols,
                        exclude_suffix=exclude_suf, iceberg_catalog=iceberg_catalog, iceberg_schema=iceberg_staging_schema,
                        src_temp_tbl=src_temp, tgt_temp_tbl=tgt_temp, mismatch_temp_tbl=mismatch_temp
                    )
                    cursor.execute(q_unnest.strip().rstrip(';'))
                    col_names = [d[0] for d in cursor.description]
                    _chunks = []
                    while True:
                        _batch = cursor.fetchmany(5000)
                        if not _batch:
                            break
                        _chunks.append(pd.DataFrame(_batch, columns=col_names))
                    df_mismatches = pd.concat(_chunks, ignore_index=True) if _chunks else pd.DataFrame(columns=col_names)
                    self.logEmitted.emit("INFO", f"[{table_name}] Found {len(df_mismatches)} VALUE_MISMATCH diff row(s)")

                    # Merge diff sections
                    df = pd.concat([df_only_src, df_only_tgt, df_mismatches], ignore_index=True)

                else:
                    # =========================================================
                    # DIRECT MONOLITHIC FULL OUTER JOIN
                    # =========================================================
                    query = generate_trino_diff.build_direct_query(
                        table_name=table_name,
                        id_columns=id_cols,
                        common_col_meta=common_col_meta,
                        exclude_cols=exclude_cols,
                        exclude_suffix=exclude_suf,
                        trim_strings=trim_strings,
                        pg_schema=pg_schema,
                        ora_schema=ora_schema,
                        source_catalog=source_catalog,
                        target_catalog=target_catalog,
                    )
                    with open(sql_file, "w", encoding="utf-8") as f:
                        f.write(query)

                    self.db.record_output_file(self.batch_id, table_name, sql_file, "SQL")
                    self.logEmitted.emit("INFO", f"[{table_name}] Generated SQL → {os.path.basename(sql_file)}")

                    query_clean = query.strip().rstrip(';')
                    cursor.execute(query_clean)
                    col_names = [desc[0] for desc in cursor.description]

                    _FETCH_CHUNK = 5_000
                    _chunks: list = []
                    while True:
                        _batch = cursor.fetchmany(_FETCH_CHUNK)
                        if not _batch:
                            break
                        _chunks.append(pd.DataFrame(_batch, columns=col_names))
                    df = (
                        pd.concat(_chunks, ignore_index=True)
                        if _chunks
                        else pd.DataFrame(columns=col_names)
                    )

                # Client-side deterministic sort
                if not df.empty:
                    _sort_cols = [ic for ic in id_cols if ic in df.columns] + [
                        c for c in ("row_diff_type",) if c in df.columns
                    ]
                    if _sort_cols:
                        df = df.sort_values(_sort_cols, ignore_index=True)

                diff_count = len(df)
                total_diffs += diff_count
                self.logEmitted.emit("INFO", f"[{table_name}] Query returned {diff_count} total diff row(s)")

                # Export to Parquet (if > 1,048,576 rows) or Excel
                if diff_count > MAX_EXCEL_ROWS:
                    report_file = os.path.join(output_dir, f"{clean_name}_diff_{run_ts}.parquet")
                    self.logEmitted.emit("WARN", f"[{table_name}] Result row count ({diff_count:,}) exceeds Excel limit. Saving Parquet format.")
                    export_diff_to_parquet(df, report_file, table_name, id_cols)
                    self.db.record_output_file(self.batch_id, table_name, report_file, "Parquet")
                    self.logEmitted.emit("SUCCESS", f"[{table_name}] Saved Parquet report → {os.path.basename(report_file)}")
                else:
                    report_file = os.path.join(output_dir, f"{clean_name}_diff_{run_ts}.xlsx")
                    export_diff_to_excel(df, report_file, table_name, id_cols, source_catalog=source_catalog, target_catalog=target_catalog)
                    self.db.record_output_file(self.batch_id, table_name, report_file, "Excel")
                    self.logEmitted.emit("SUCCESS", f"[{table_name}] Saved Excel report → {os.path.basename(report_file)}")

                tbl_finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.db.record_table_result(
                    batch_id=self.batch_id,
                    table_name=table_name,
                    status="Completed",
                    diff_count=diff_count,
                    id_columns=id_cols,
                    schema_name=pg_schema or ora_schema or schema_override,
                    sql_file_path=sql_file,
                    report_file_path=report_file,
                    report_file_type="PARQUET" if diff_count > MAX_EXCEL_ROWS else "EXCEL",
                    started_at=tbl_started_at,
                    finished_at=tbl_finished_at
                )

                self.tableStatusUpdated.emit(table_name, "Completed", diff_count)
                self.tableFinished.emit(table_name, sql_file, report_file)
                success_count += 1

            except Exception as ex:
                error_msg = str(ex)
                tbl_finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.db.record_table_result(
                    batch_id=self.batch_id,
                    table_name=table_name,
                    status="Error",
                    diff_count=0,
                    id_columns=id_cols,
                    schema_name=schema_override,
                    sql_file_path=sql_file if os.path.exists(sql_file) else None,
                    error_message=error_msg,
                    failed_query=query,
                    started_at=tbl_started_at,
                    finished_at=tbl_finished_at
                )
                self.logEmitted.emit("ERROR", f"[{table_name}] Error: {error_msg}")
                self.tableStatusUpdated.emit(table_name, "Error", 0)
                self.tableErrorOccurred.emit(table_name, error_msg, query)
                error_count += 1

            finally:
                # Stage 5: Cleanup temporary Iceberg staging tables
                if diff_engine == "iceberg" and created_temp_tables:
                    if error_count == 0 or iceberg_cleanup_on_error or self._is_cancelled:
                        try:
                            clean_cursor = conn.cursor()
                            for tbl in created_temp_tables:
                                try:
                                    clean_cursor.execute(f"DROP TABLE IF EXISTS {iceberg_catalog}.{iceberg_staging_schema}.{tbl}")
                                except Exception as _drp_e:
                                    self.logEmitted.emit("WARN", f"[{table_name}] Could not drop staging table {tbl}: {_drp_e}")
                            clean_cursor.close()
                            self.logEmitted.emit("INFO", f"[{table_name}] Cleaned up temporary Iceberg staging tables.")
                        except Exception as _clean_ex:
                            self.logEmitted.emit("WARN", f"[{table_name}] Staging table cleanup encountered: {_clean_ex}")
                try:
                    cursor.close()
                except Exception:
                    pass

        try:
            conn.close()
        except Exception:
            pass

        final_status = "CANCELLED" if self._is_cancelled else ("COMPLETED" if error_count == 0 else ("FAILED" if success_count == 0 else "PARTIAL"))
        self.db.finish_batch(self.batch_id, final_status, success_count, error_count, total_diffs)

        self.logEmitted.emit("INFO", f"Execution finished [Batch: {self.batch_id}]. Succeeded: {success_count}, Failed: {error_count}")
        self.allFinished.emit(success_count, error_count)

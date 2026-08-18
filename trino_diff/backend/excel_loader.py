import os
import pandas as pd
from typing import List, Dict, Any, Tuple
try:
    from trino_diff.backend.db_manager import DatabaseManager
except ImportError:
    from backend.db_manager import DatabaseManager


def load_tables_from_excel(excel_path: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Read table names and business (ID) columns from the specified Excel file,
    and persist the parsed mapping into the SQLite database.
    
    Returns:
        (success: bool, tables: list[dict], message: str)
    """
    db = DatabaseManager()

    if not os.path.exists(excel_path):
        # Check if we have previously cached mapping in SQLite
        cached = db.get_latest_excel_mapping()
        if cached:
            _, tables = cached
            return True, tables, f"Loaded {len(tables)} tables from SQLite cache (file not found on disk: {excel_path})"
        return False, [], f"Excel file not found: {excel_path}"

    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        # Check SQLite fallback
        cached = db.get_latest_excel_mapping()
        if cached:
            _, tables = cached
            return True, tables, f"Loaded {len(tables)} tables from SQLite cache (Excel read error: {e})"
        return False, [], f"Failed to read Excel file: {e}"

    # Clean header names
    df.columns = [str(c).strip() for c in df.columns]

    # Look for table name column and business column
    tbl_col = None
    bus_col = None

    for c in df.columns:
        clow = c.lower()
        if "table" in clow and "name" in clow:
            tbl_col = c
        elif "business" in clow or "id" in clow or "column" in clow:
            if not bus_col:
                bus_col = c

    if not tbl_col or not bus_col:
        # Fallback to exact column names if present
        if "Table Name" in df.columns:
            tbl_col = "Table Name"
        if "Business Column" in df.columns:
            bus_col = "Business Column"

    if not tbl_col or not bus_col:
        return False, [], f"Required columns ('Table Name', 'Business Column') not found. Columns: {list(df.columns)}"

    # Filter out empty rows
    df = df.dropna(subset=[tbl_col, bus_col])

    tables_config = []
    seen_tables = {}

    for _, row in df.iterrows():
        tbl_raw = str(row[tbl_col]).strip()
        cols_raw = str(row[bus_col]).strip()

        if not tbl_raw or not cols_raw or tbl_raw.lower() == "nan" or cols_raw.lower() == "nan":
            continue

        tbl = tbl_raw.lower()
        cols = [c.strip().lower() for c in cols_raw.split(",") if c.strip() and c.strip().lower() != "nan"]

        if tbl not in seen_tables:
            entry = {
                "table_name": tbl,
                "display_name": tbl_raw,
                "id_columns": [],
                "status": "Ready",
                "selected": True,
                "diff_count": 0,
                "last_run": "",
            }
            tables_config.append(entry)
            seen_tables[tbl] = entry

        for col in cols:
            if col not in seen_tables[tbl]["id_columns"]:
                seen_tables[tbl]["id_columns"].append(col)

    # Persist mapping to SQLite database
    db.save_excel_mapping(excel_path, tables_config)

    return True, tables_config, f"Successfully loaded {len(tables_config)} tables"

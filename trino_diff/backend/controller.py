import os
import sys
import subprocess
import threading
import urllib.parse
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot, Property, QThread

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
TRINO_DIFF_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(TRINO_DIFF_DIR)

from trino_diff.backend.config_manager import load_config, save_config
from trino_diff.backend.trino_client import test_trino_connection, fetch_trino_catalogs, get_trino_connection
from trino_diff.backend.excel_loader import load_tables_from_excel
from trino_diff.backend.worker import TrinoDiffWorker
from trino_diff.backend.notifier import WindowsNotifier
from trino_diff.backend.ollama_client import query_ollama, extract_sql_from_response, test_ollama_connection
from trino_diff.backend.db_manager import DatabaseManager
import generate_trino_diff


class BackendController(QObject):
    """
    Main Qt Bridge Controller exposing properties and slots to QML.
    """

    # Signals
    catalogsChanged = Signal()
    tablesChanged = Signal()
    logsChanged = Signal()
    outputFilesChanged = Signal()
    batchesChanged = Signal()
    currentBatchIdChanged = Signal()
    configChanged = Signal()
    runningStateChanged = Signal()
    progressChanged = Signal()
    statusTextChanged = Signal()
    sqlPreviewReady = Signal(str, str)  # (table_name, sql_text)
    notificationEmitted = Signal(str, str)  # (type: 'success'|'error'|'info'|'warning', message)
    aiDiagnosisReady = Signal(str, str, str)  # (table_name, explanation_markdown, suggested_sql)
    aiDiagnosisFailed = Signal(str, str)      # (table_name, error_message)
    aiDiagnosisLoading = Signal(str, bool)    # (table_name, is_loading)
    ollamaTestFinished = Signal(bool, str)    # (success, message)

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self._config = load_config()
        self._notifier = WindowsNotifier()
        self._catalogs = ["postgres", "oracle"]
        self._tables = []
        self._logs = []
        self._output_files = []
        self._batches = self.db.get_batches_list()
        self._current_batch_id = ""
        self._selected_batch_filter = ""
        self._table_errors = {}
        self._is_running = False
        self._progress_val = 0
        self._progress_max = 100
        self._status_text = "Ready"
        self._worker_thread = None
        self._worker = None
        self._ai_thread = None
        self._ai_worker = None

        # Initial startup log
        self.appendLog("INFO", "Trino Diff Studio initialized. System ready.")

        # Load initial excel if present
        excel_path = self._config.get("excel_path", "")
        if excel_path and os.path.exists(excel_path):
            self.loadExcel(excel_path)

        # Refresh output files
        self.refreshOutputFiles()

    # -----------------------------------------------------------------------
    # Q_PROPERTY Bindings
    # -----------------------------------------------------------------------

    @Property(list, notify=catalogsChanged)
    def catalogs(self):
        return self._catalogs

    @Property(list, notify=tablesChanged)
    def tables(self):
        return self._tables

    @Property(list, notify=logsChanged)
    def logs(self):
        return self._logs

    @Property(list, notify=outputFilesChanged)
    def outputFiles(self):
        return self._output_files

    @Property(list, notify=batchesChanged)
    def batches(self):
        return self._batches

    @Property(str, notify=currentBatchIdChanged)
    def currentBatchId(self):
        return self._current_batch_id

    @Property(dict, notify=configChanged)
    def config(self):
        return self._config

    @Property(bool, notify=runningStateChanged)
    def isRunning(self):
        return self._is_running

    @Property(int, notify=progressChanged)
    def progressPercent(self):
        if self._progress_max == 0:
            return 0
        return int((self._progress_val / self._progress_max) * 100)

    @Property(str, notify=statusTextChanged)
    def statusText(self):
        return self._status_text

    # -----------------------------------------------------------------------
    # Logging helper
    # -----------------------------------------------------------------------

    @Slot(str, str)
    def appendLog(self, level: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message,
        }
        self._logs.append(entry)
        if len(self._logs) > 500:
            self._logs.pop(0)
        self.logsChanged.emit()

    @Slot()
    def clearLogs(self):
        self._logs = []
        self.logsChanged.emit()

    # -----------------------------------------------------------------------
    # Trino Connection & Catalogs
    # -----------------------------------------------------------------------

    @Slot(result=str)
    def testConnection(self) -> str:
        host = self._config.get("trino_host", "localhost")
        port = int(self._config.get("trino_port", 8080))
        user = self._config.get("trino_user", "admin")
        scheme = self._config.get("http_scheme", "http")

        self.appendLog("INFO", f"Testing Trino connection to {host}:{port} ({user})...")
        success, msg = test_trino_connection(host=host, port=port, user=user, http_scheme=scheme)

        if success:
            self.appendLog("SUCCESS", "Trino connection verified successfully.")
            self.refreshCatalogs()
            self.notificationEmitted.emit("success", "Connection successful! Catalogs refreshed.")
            return "SUCCESS"
        else:
            self.appendLog("ERROR", f"Trino connection failed: {msg}")
            self.notificationEmitted.emit("error", f"Connection failed: {msg}")
            self._notifier.notify("Trino Connection Failed", f"Could not connect to Trino: {msg}", level="error")
            return f"ERROR: {msg}"

    @Slot()
    def refreshCatalogs(self):
        host = self._config.get("trino_host", "localhost")
        port = int(self._config.get("trino_port", 8080))
        user = self._config.get("trino_user", "admin")
        scheme = self._config.get("http_scheme", "http")

        success, cats, msg = fetch_trino_catalogs(host=host, port=port, user=user, http_scheme=scheme)
        if success and cats:
            self._catalogs = cats
            self.appendLog("INFO", f"Discovered catalogs: {', '.join(cats)}")
        else:
            self._catalogs = ["postgres", "oracle"]
            self.appendLog("WARN", f"Could not query catalogs dynamically: {msg}. Using defaults: postgres, oracle")
        self.catalogsChanged.emit()

    # -----------------------------------------------------------------------
    # Excel Loading
    # -----------------------------------------------------------------------

    @Slot(str)
    def loadExcel(self, file_path: str):
        # Remove file:/// URL prefix if passed from QML FileDialog and decode %20 spaces
        clean_path = urllib.parse.unquote(file_path).replace("file:///", "").replace("file://", "")
        if sys.platform == "win32" and clean_path.startswith("/") and len(clean_path) > 2 and clean_path[2] == ":":
            clean_path = clean_path[1:]

        self.appendLog("INFO", f"Loading Excel mapping from: {clean_path}")
        success, tables, msg = load_tables_from_excel(clean_path)

        if success:
            self._tables = tables
            self._config["excel_path"] = clean_path
            save_config(self._config)
            self.configChanged.emit()
            self.tablesChanged.emit()
            self.appendLog("SUCCESS", msg)
            self.notificationEmitted.emit("success", f"Loaded {len(tables)} tables from Excel.")
        else:
            self.appendLog("ERROR", msg)
            self.notificationEmitted.emit("error", msg)
            self._notifier.notify("Excel Load Failed", f"Could not load Excel mapping: {msg}", level="error")

    @Slot(str, bool)
    def toggleTableSelection(self, table_name: str, selected: bool):
        for t in self._tables:
            if t["table_name"] == table_name:
                t["selected"] = selected
                break
        self.tablesChanged.emit()

    @Slot(bool)
    def selectAllTables(self, selected: bool):
        for t in self._tables:
            t["selected"] = selected
        self.tablesChanged.emit()

    # -----------------------------------------------------------------------
    # Batch & Single Diff Execution
    # -----------------------------------------------------------------------

    @Slot(bool)
    def startBatch(self, selected_only: bool = True):
        if self._is_running:
            return

        if selected_only:
            tasks = [t for t in self._tables if t.get("selected", True)]
        else:
            tasks = list(self._tables)

        if not tasks:
            self.notificationEmitted.emit("warning", "No tables selected to process.")
            return

        self._is_running = True
        self._progress_val = 0
        self._progress_max = len(tasks)
        self._status_text = f"Processing 0/{len(tasks)} tables..."
        batch_id = f"BATCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._current_batch_id = batch_id
        self.currentBatchIdChanged.emit()
        self.runningStateChanged.emit()
        self.progressChanged.emit()
        self.statusTextChanged.emit()

        # Create worker & thread
        self._worker_thread = QThread()
        self._worker = TrinoDiffWorker(tasks, self._config, batch_id=batch_id, batch_type="BATCH")
        self._worker.moveToThread(self._worker_thread)

        self._worker.logEmitted.connect(self.appendLog)
        self._worker.progressUpdated.connect(self._onWorkerProgress)
        self._worker.tableStatusUpdated.connect(self._onWorkerTableStatus)
        self._worker.tableFinished.connect(self._onWorkerTableFinished)
        self._worker.tableErrorOccurred.connect(self._onWorkerTableError)
        self._worker.allFinished.connect(self._onWorkerAllFinished)

        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    @Slot(str, str, str, str, str)
    def runSingleTable(self, table_name: str, schema: str, id_cols_str: str, source_cat: str, target_cat: str):
        if self._is_running:
            return

        clean_table = table_name.strip().lower()
        if not clean_table:
            self.notificationEmitted.emit("warning", "Please provide a valid table name.")
            return

        id_cols = [c.strip().lower() for c in id_cols_str.split(",") if c.strip()]
        if not id_cols:
            self.notificationEmitted.emit("warning", "Please specify at least one ID / Business Column.")
            return

        task = {
            "table_name": clean_table,
            "id_columns": id_cols,
            "schema": schema.strip().lower() if schema and schema.lower() != "auto" else None,
        }

        cfg_copy = self._config.copy()
        if source_cat:
            cfg_copy["source_catalog"] = source_cat
        if target_cat:
            cfg_copy["target_catalog"] = target_cat

        batch_id = f"ADHOC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._current_batch_id = batch_id
        self.currentBatchIdChanged.emit()

        self._is_running = True
        self._progress_val = 0
        self._progress_max = 1
        self._status_text = f"Processing {clean_table}..."
        self.runningStateChanged.emit()
        self.progressChanged.emit()
        self.statusTextChanged.emit()

        self._worker_thread = QThread()
        self._worker = TrinoDiffWorker([task], cfg_copy, batch_id=batch_id, batch_type="ADHOC")
        self._worker.moveToThread(self._worker_thread)

        self._worker.logEmitted.connect(self.appendLog)
        self._worker.progressUpdated.connect(self._onWorkerProgress)
        self._worker.tableStatusUpdated.connect(self._onWorkerTableStatus)
        self._worker.tableFinished.connect(self._onWorkerTableFinished)
        self._worker.tableErrorOccurred.connect(self._onWorkerTableError)
        self._worker.allFinished.connect(self._onWorkerAllFinished)

        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    @Slot()
    def stopBatch(self):
        if self._worker:
            self._worker.cancel()
            self._status_text = "Stopping..."
            self.statusTextChanged.emit()

    # -----------------------------------------------------------------------
    # Worker callbacks
    # -----------------------------------------------------------------------

    def _onWorkerProgress(self, current: int, total: int, current_table: str):
        self._progress_val = current
        self._progress_max = total
        self._status_text = f"[{current}/{total}] {current_table}"
        self.progressChanged.emit()
        self.statusTextChanged.emit()

    def _onWorkerTableError(self, table_name: str, error_msg: str, query: str):
        enable_ai = self._config.get("enable_ai_diagnosis", True)
        auto_ai = enable_ai and self._config.get("auto_ai_diagnosis", True)
        self._table_errors[table_name] = {
            "error": error_msg,
            "query": query,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "explanation": "",
            "suggested_sql": "",
            "prompt": "",
            "diagnosed_error": ""
        }
        for t in self._tables:
            if t["table_name"] == table_name:
                t["error_message"] = error_msg
                t["failed_query"] = query
                t["ai_status"] = "Diagnosing" if auto_ai else ("Disabled" if not enable_ai else "Idle")
                t["ai_explanation"] = ""
                t["suggested_sql"] = ""
                t["ai_prompt"] = ""
                break
        self.tablesChanged.emit()

        # Automatically start AI error diagnosis in parallel with ongoing Trino processing
        if auto_ai:
            self.appendLog("INFO", f"[AI Assistant] Initiating parallel background AI diagnosis for {table_name}...")
            self._runAsyncAiDiagnosis(table_name, error_msg, query, notify_ui=False)

    def _onWorkerTableStatus(self, table_name: str, status: str, diff_count: int):
        for t in self._tables:
            if t["table_name"] == table_name:
                t["status"] = status
                if status == "Completed":
                    t["diff_count"] = diff_count
                    t["last_run"] = datetime.now().strftime("%H:%M:%S")
                break
        self.tablesChanged.emit()

        # Windows Notification for individual table completion or failure
        if self._config.get("notify_table_complete", True):
            if status == "Completed":
                if diff_count == 0:
                    msg = "0 diffs found (datasets are fully in sync)."
                    level = "success"
                else:
                    msg = f"Completed with {diff_count:,} diff row(s). Report generated."
                    level = "warning"
                self._notifier.notify(f"Diff Complete: {table_name}", msg, level=level)
            elif status == "Error":
                self._notifier.notify(
                    f"Diff Failed: {table_name}",
                    f"Encountered an error comparing {table_name}. Check logs for details.",
                    level="error"
                )

    def _onWorkerTableFinished(self, table_name: str, sql_file: str, xlsx_file: str):
        self.refreshOutputFiles(self._selected_batch_filter)

    def _onWorkerAllFinished(self, success_cnt: int, error_cnt: int):
        self._is_running = False
        self._status_text = f"Finished: {success_cnt} succeeded, {error_cnt} failed"
        self.runningStateChanged.emit()
        self.statusTextChanged.emit()

        # Refresh batches from SQLite and reload output files
        self._batches = self.db.get_batches_list()
        self.batchesChanged.emit()
        self.refreshOutputFiles(self._selected_batch_filter)

        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None

        if error_cnt == 0:
            self.notificationEmitted.emit("success", f"Execution complete: {success_cnt} table(s) processed.")
        else:
            self.notificationEmitted.emit("warning", f"Finished with {error_cnt} error(s). Check logs for details.")

        # Windows Notification for batch completion
        if self._config.get("notify_batch_complete", True):
            total = success_cnt + error_cnt
            if error_cnt == 0:
                self._notifier.notify(
                    "Trino Batch Completed",
                    f"All {success_cnt} table diff(s) completed successfully.",
                    level="success"
                )
            else:
                self._notifier.notify(
                    "Trino Batch Alert: Failures Detected",
                    f"Processed {total} table(s): {success_cnt} succeeded, {error_cnt} failed.",
                    level="error"
                )

    # -----------------------------------------------------------------------
    # SQL Preview Generation
    # -----------------------------------------------------------------------

    @Slot(str, str, str, str, str)
    def generateSqlPreview(self, table_name: str, schema: str, id_cols_str: str, source_cat: str, target_cat: str):
        clean_table = table_name.strip().lower()
        if not clean_table:
            self.notificationEmitted.emit("warning", "Please provide a table name.")
            return

        id_cols = [c.strip().lower() for c in id_cols_str.split(",") if c.strip()]
        if not id_cols:
            self.notificationEmitted.emit("warning", "Please specify at least one ID column.")
            return

        sch = schema.strip().lower() if schema and schema.lower() != "auto" else None
        src = source_cat.strip().lower() or self._config.get("source_catalog", "postgres")
        tgt = target_cat.strip().lower() or self._config.get("target_catalog", "oracle")

        host = self._config.get("trino_host", "localhost")
        port = int(self._config.get("trino_port", 8080))
        user = self._config.get("trino_user", "admin")
        scheme = self._config.get("http_scheme", "http")

        self.appendLog("INFO", f"Generating SQL Preview for {clean_table}...")

        try:
            conn = get_trino_connection(host=host, port=port, user=user, http_scheme=scheme)
            cursor = conn.cursor()
            pg_sch, pg_cols = generate_trino_diff.fetch_columns(cursor, src, clean_table, sch)
            ora_sch, ora_cols = generate_trino_diff.fetch_columns(cursor, tgt, clean_table, sch)

            if not pg_cols or not ora_cols:
                raise ValueError(f"Table columns could not be found in {src} or {tgt}.")

            pg_name_map = {c["name"]: c for c in pg_cols}
            ora_name_map = {c["name"]: c for c in ora_cols}
            id_col_set = set(id_cols)
            common_names = sorted((set(pg_name_map.keys()) & set(ora_name_map.keys())) - id_col_set)

            if not common_names:
                raise ValueError("No common comparison columns found.")

            common_col_meta = [{"name": n, "data_type": pg_name_map[n]["data_type"]} for n in common_names]

            exclude_cols = [c.strip() for c in self._config.get("exclude_columns", "").split(",") if c.strip()]
            exclude_suf = self._config.get("exclude_suffix", "").strip() or None
            trim_strings = self._config.get("trim_strings", True)

            query = generate_trino_diff.build_query(
                table_name=clean_table,
                id_columns=id_cols,
                common_col_meta=common_col_meta,
                exclude_cols=exclude_cols,
                exclude_suffix=exclude_suf,
                trim_strings=trim_strings,
                pg_schema=pg_sch,
                ora_schema=ora_sch,
                source_catalog=src,
                target_catalog=tgt,
            )
            cursor.close()
            conn.close()

            self.sqlPreviewReady.emit(clean_table, query)
            self.appendLog("SUCCESS", f"SQL query generated for {clean_table}")

        except Exception as e:
            self.appendLog("ERROR", f"SQL preview error: {e}")
            self.notificationEmitted.emit("error", f"Could not generate SQL preview: {e}")
            self._notifier.notify("SQL Preview Failed", f"Could not generate SQL preview for {clean_table}: {e}", level="error")

    # -----------------------------------------------------------------------
    # Output Files & Batch History Management
    # -----------------------------------------------------------------------

    @Slot(str)
    def filterOutputByBatch(self, batch_id: str):
        self._selected_batch_filter = batch_id.strip() if batch_id and batch_id != "ALL" else ""
        self.refreshOutputFiles(self._selected_batch_filter)

    @Slot(result=list)
    def getBatchesList(self) -> list:
        self._batches = self.db.get_batches_list()
        self.batchesChanged.emit()
        return self._batches

    @Slot(str, result='QVariantMap')
    def getBatchDetails(self, batch_id: str) -> dict:
        return self.db.get_batch_details(batch_id) or {}

    @Slot()
    @Slot(str)
    def refreshOutputFiles(self, batch_id: str = ""):
        output_dir = self._config.get("output_dir", os.path.join(PROJECT_ROOT, "output"))
        clean_batch_id = batch_id.strip() if batch_id and batch_id != "ALL" else self._selected_batch_filter

        # If a specific batch is requested, query SQLite output_files directly
        if clean_batch_id:
            files = self.db.get_output_files_by_batch(clean_batch_id)
            self._output_files = files
            self.outputFilesChanged.emit()
            return

        # Otherwise, scan disk directory and synchronize with SQLite
        files = []
        if os.path.exists(output_dir):
            for fn in sorted(os.listdir(output_dir), reverse=True):
                fp = os.path.join(output_dir, fn)
                if os.path.isfile(fp):
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in (".xlsx", ".sql", ".parquet"):
                        st = os.stat(fp)
                        size_kb = round(st.st_size / 1024, 1)
                        mod_time = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        if ext == ".xlsx":
                            ftype = "Excel"
                        elif ext == ".parquet":
                            ftype = "Parquet"
                        else:
                            ftype = "SQL"

                        # Index into SQLite if missing
                        self.db.record_output_file(None, None, fp, ftype)

                        files.append({
                            "name": fn,
                            "path": fp,
                            "type": ftype,
                            "size": f"{size_kb} KB" if size_kb < 1024 else f"{round(size_kb / 1024, 1)} MB",
                            "modified": mod_time,
                        })

        self._output_files = files
        self.outputFilesChanged.emit()
        self._batches = self.db.get_batches_list()
        self.batchesChanged.emit()

    @Slot(str)
    def openFile(self, path: str):
        clean_path = urllib.parse.unquote(path).replace("file:///", "").replace("file://", "")
        if sys.platform == "win32" and clean_path.startswith("/") and len(clean_path) > 2 and clean_path[2] == ":":
            clean_path = clean_path[1:]

        if not os.path.exists(clean_path):
            self.notificationEmitted.emit("error", f"File not found: {clean_path}")
            self._notifier.notify("File Not Found", f"Could not find file: {clean_path}", level="error")
            return
        try:
            ext = os.path.splitext(clean_path)[1].lower()
            if sys.platform == "win32":
                if ext == ".sql":
                    # Prefer Notepad++, fallback to standard Notepad
                    import shutil
                    npp_candidates = [
                        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Notepad++", "notepad++.exe"),
                        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Notepad++", "notepad++.exe"),
                        os.path.expandvars("%LOCALAPPDATA%\\Programs\\Notepad++\\notepad++.exe"),
                    ]
                    npp_path = None
                    which_npp = shutil.which("notepad++.exe") or shutil.which("notepad++")
                    if which_npp and os.path.exists(which_npp):
                        npp_path = which_npp
                    else:
                        for cand in npp_candidates:
                            if os.path.exists(cand):
                                npp_path = cand
                                break

                    if npp_path:
                        subprocess.Popen([npp_path, clean_path])
                    else:
                        subprocess.Popen(["notepad.exe", clean_path])
                else:
                    os.startfile(clean_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", clean_path])
            else:
                subprocess.run(["xdg-open", clean_path])
        except Exception as e:
            self.notificationEmitted.emit("error", f"Could not open file: {e}")
            self._notifier.notify("Open File Failed", f"Could not open {os.path.basename(clean_path)}: {e}", level="error")

    @Slot(str)
    def openFolder(self, path: str):
        clean_path = urllib.parse.unquote(path).replace("file:///", "").replace("file://", "")
        if sys.platform == "win32" and clean_path.startswith("/") and len(clean_path) > 2 and clean_path[2] == ":":
            clean_path = clean_path[1:]

        folder = clean_path if os.path.isdir(clean_path) else os.path.dirname(clean_path)
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception as e:
            self.notificationEmitted.emit("error", f"Could not open folder: {e}")

    @Slot(str)
    def deleteOutputFile(self, path: str):
        clean_path = urllib.parse.unquote(path).replace("file:///", "").replace("file://", "")
        if sys.platform == "win32" and clean_path.startswith("/") and len(clean_path) > 2 and clean_path[2] == ":":
            clean_path = clean_path[1:]

        if os.path.exists(clean_path):
            try:
                os.remove(clean_path)
                self.appendLog("INFO", f"Deleted: {os.path.basename(clean_path)}")
                self.refreshOutputFiles()
            except Exception as e:
                self.notificationEmitted.emit("error", f"Could not delete file: {e}")

    # -----------------------------------------------------------------------
    # AI Diagnosis (Qwen 2.5 Coder via Ollama)
    # -----------------------------------------------------------------------

    def _runAsyncAiDiagnosis(self, table_name: str, error_msg: str, failed_query: str, notify_ui: bool = False):
        if not self._config.get("enable_ai_diagnosis", True):
            if notify_ui:
                self.notificationEmitted.emit("warning", "AI Diagnosis is currently disabled in Settings.")
            return

        clean_name = table_name.strip()
        config_copy = self._config.copy()
        effort = config_copy.get("ai_effort", "High")
        effort_lower = effort.lower()

        if notify_ui:
            self.aiDiagnosisLoading.emit(clean_name, True)

        def _ai_task():
            try:
                ollama_url = config_copy.get("ollama_url", "http://localhost:11434")
                model = config_copy.get("ollama_model", "qwen2.5-coder:1.5b")

                if "low" in effort_lower:
                    system_prompt = (
                        "You are an expert Trino SQL database engineer. "
                        "Diagnose the Trino query error quickly and output a clean, corrected Trino SQL query."
                    )
                    user_prompt = f"""### Target Table: `{clean_name}`

#### Trino Error Message:
```
{error_msg}
```

#### Executed Trino SQL Query:
```sql
{failed_query if failed_query else "-- (Query could not be generated due to metadata error)"}
```

#### Instructions:
1. **Root Cause**: Briefly state why the error occurred.
2. **Corrected Query**: Provide the corrected Trino SQL query enclosed in a ```sql ... ``` code block."""

                elif "med" in effort_lower:
                    system_prompt = (
                        "You are an expert Trino SQL database engineer and performance specialist. "
                        "Your task is to diagnose Trino query failures, explain the specific root cause based strictly "
                        "on the provided Trino error and failed query, and provide the exact corrected, executable Trino SQL query."
                    )
                    user_prompt = f"""### Target Table: `{clean_name}`

#### Trino Error Message:
```
{error_msg}
```

#### Executed Trino SQL Query:
```sql
{failed_query if failed_query else "-- (Query could not be generated due to metadata error)"}
```

#### Instructions:
Please provide a structured Markdown diagnosis:
- **Root Cause**: Identify and explain the exact cause of this specific Trino error in the query.
- **Fix Strategy**: Outline the necessary SQL adjustments (e.g. correct type casting, date formatting, column qualification).
- **Corrected Query**: Provide the complete, valid, executable Trino SQL query enclosed in a ```sql ... ``` code block."""

                else:  # High / Deep Multi-Step Validation
                    system_prompt = (
                        "You are a principal Trino SQL compiler engineer and database performance auditor. "
                        "Your task is to perform an exhaustive root-cause analysis and rigorous multi-point self-validation "
                        "on the failed Trino SQL query. You must critically audit data types, CAST operations, catalog qualifications, "
                        "and Trino ANSI SQL syntax rules before producing the final validated query."
                    )
                    user_prompt = f"""### Target Table: `{clean_name}`

#### Trino Error Message:
```
{error_msg}
```

#### Executed Trino SQL Query:
```sql
{failed_query if failed_query else "-- (Query could not be generated due to metadata error)"}
```

#### In-Depth Analysis & Multi-Point Self-Validation Instructions:
Perform an exhaustive diagnosis and validation formatted cleanly in Markdown:

1. **Root Cause & Line-by-Line Fault Analysis**:
   - Quote the exact Trino error message and identify the exact clause (`SELECT`, `FROM`, `JOIN`, `WHERE`, `EXCEPT`, or `CAST`) causing failure.
   - Explain why this construction is invalid in Trino SQL across Oracle and PostgreSQL catalogs.

2. **Data Type & Schema Compatibility Audit**:
   - Audit all columns involved in the error (check data types: `VARCHAR`, `TIMESTAMP`, `DECIMAL`, `BIGINT`, `DATE`, etc.).
   - Detail explicit `CAST(...)` or `TRY_CAST(...)` conversions and timezone/format rules needed for cross-database equality.

3. **Self-Validation & Sanity Checklist**:
   - Verify that all catalog/schema qualifications (`<catalog>.<schema>.<table>`) are correct.
   - Verify that column aliases and ID column joins match identically on both sides.
   - Confirm that reserved keywords are properly quoted or formatted according to Trino ANSI SQL syntax.
   - Self-check that the query will execute without syntax errors, missing columns, or type mismatch exceptions.

4. **Verified Corrected Trino SQL Query**:
   - Provide the complete, fully corrected, validated, executable Trino SQL query enclosed in a ```sql ... ``` code block."""

                full_logged_prompt = f"--- [System Prompt (Effort: {effort})] ---\n{system_prompt}\n\n--- [User Prompt] ---\n{user_prompt}"

                print(f"\n--- [PROMPT PASSED TO QWEN ({model}) (Effort: {effort}) FOR {clean_name}] ---\n{full_logged_prompt}\n----------------------------------------\n")
                
                # Log full prompt to the UI logging screen
                self.appendLog("INFO", f"[AI Assistant] Prompt sent to {model} (Effort: {effort}) for '{clean_name}':\n{user_prompt}")

                # Store prompt in cache
                if clean_name in self._table_errors:
                    self._table_errors[clean_name]["prompt"] = full_logged_prompt
                    self._table_errors[clean_name]["diagnosed_error"] = error_msg
                for t in self._tables:
                    if t["table_name"] == clean_name:
                        t["ai_prompt"] = full_logged_prompt
                        break

                res = query_ollama(
                    prompt=user_prompt,
                    system=system_prompt,
                    model=model,
                    base_url=ollama_url,
                    timeout=120,
                    effort=effort
                )

                if res["success"]:
                    explanation = res["response"]
                    suggested_sql = extract_sql_from_response(explanation)
                    self._onAiDiagnosisFinished(clean_name, explanation, suggested_sql, notify_ui)
                else:
                    self._onAiDiagnosisFailed(clean_name, res["error"], notify_ui)
            except Exception as ex:
                self._onAiDiagnosisFailed(clean_name, f"Unexpected error during AI diagnosis: {ex}", notify_ui)

        worker_thread = threading.Thread(target=_ai_task, daemon=True)
        worker_thread.start()

    def _onAiDiagnosisFinished(self, table_name: str, explanation: str, suggested_sql: str, notify_ui: bool):
        if table_name in self._table_errors:
            self._table_errors[table_name]["explanation"] = explanation
            self._table_errors[table_name]["suggested_sql"] = suggested_sql

        for t in self._tables:
            if t["table_name"] == table_name:
                t["ai_status"] = "Ready"
                t["ai_explanation"] = explanation
                t["suggested_sql"] = suggested_sql
                break
        self.tablesChanged.emit()
        self.appendLog("SUCCESS", f"[AI Assistant] Diagnosis ready for '{table_name}':\n{explanation}")

        if notify_ui:
            self.aiDiagnosisLoading.emit(table_name, False)
            self.aiDiagnosisReady.emit(table_name, explanation, suggested_sql)

    def _onAiDiagnosisFailed(self, table_name: str, error_msg: str, notify_ui: bool):
        for t in self._tables:
            if t["table_name"] == table_name:
                t["ai_status"] = "Failed"
                t["ai_error"] = error_msg
                break
        self.tablesChanged.emit()
        self.appendLog("ERROR", f"[AI Assistant] Background diagnosis failed for {table_name}: {error_msg}")

        if notify_ui:
            self.aiDiagnosisLoading.emit(table_name, False)
            self.aiDiagnosisFailed.emit(table_name, error_msg)
            self.notificationEmitted.emit("error", f"AI Diagnosis failed: {error_msg}")

    @Slot(str)
    @Slot(str, bool)
    def explainTableError(self, table_name: str, force: bool = False):
        if not self._config.get("enable_ai_diagnosis", True):
            self.notificationEmitted.emit("warning", "AI Diagnosis is currently disabled in Settings.")
            self.appendLog("WARN", "[AI Assistant] Cannot run AI diagnosis: AI feature is disabled in Settings.")
            return

        clean_name = table_name.strip()
        err_info = self._table_errors.get(clean_name, {})
        error_msg = err_info.get("error", "")
        failed_query = err_info.get("query", "")
        explanation = err_info.get("explanation", "")
        suggested_sql = err_info.get("suggested_sql", "")
        diagnosed_error = err_info.get("diagnosed_error", "")
        ai_status = ""

        for t in self._tables:
            if t["table_name"] == clean_name:
                if not error_msg:
                    error_msg = t.get("error_message", "")
                    failed_query = t.get("failed_query", "")
                if not explanation and t.get("ai_explanation"):
                    explanation = t.get("ai_explanation", "")
                    suggested_sql = t.get("suggested_sql", "")
                ai_status = t.get("ai_status", "")
                break

        # If not forcing re-analysis, and an existing diagnosis matches the error, deliver immediately
        if not force and explanation and (not diagnosed_error or diagnosed_error == error_msg):
            self.aiDiagnosisLoading.emit(clean_name, False)
            self.aiDiagnosisReady.emit(clean_name, explanation, suggested_sql)
            return

        # If currently being diagnosed in parallel and not forcing, open dialog in loading mode
        if not force and ai_status == "Diagnosing":
            self.aiDiagnosisLoading.emit(clean_name, True)
            return

        # Clear cached diagnosis for a fresh run
        if clean_name in self._table_errors:
            self._table_errors[clean_name]["explanation"] = ""
            self._table_errors[clean_name]["suggested_sql"] = ""
            self._table_errors[clean_name]["prompt"] = ""
            self._table_errors[clean_name]["diagnosed_error"] = ""

        for t in self._tables:
            if t["table_name"] == clean_name:
                t["ai_status"] = "Diagnosing"
                t["ai_explanation"] = ""
                t["suggested_sql"] = ""
                t["ai_prompt"] = ""
                break
        self.tablesChanged.emit()

        if not error_msg:
            error_msg = "Unknown error occurred during Trino execution."

        # Trigger new diagnosis with UI feedback
        self.aiDiagnosisLoading.emit(clean_name, True)
        self.appendLog("INFO", f"[AI Assistant] Asking Ollama to analyze Trino error for {clean_name}...")
        self._runAsyncAiDiagnosis(clean_name, error_msg, failed_query, notify_ui=True)

    @Slot(str, result=str)
    def getTableErrorMessage(self, table_name: str) -> str:
        clean_name = table_name.strip()
        if clean_name in self._table_errors:
            return self._table_errors[clean_name].get("error", "")
        for t in self._tables:
            if t["table_name"] == clean_name:
                return t.get("error_message", "")
        return ""

    @Slot(str, result=str)
    def getTableFailedQuery(self, table_name: str) -> str:
        clean_name = table_name.strip()
        if clean_name in self._table_errors:
            return self._table_errors[clean_name].get("query", "")
        for t in self._tables:
            if t["table_name"] == clean_name:
                return t.get("failed_query", "")
        return ""

    @Slot(str, result=str)
    def getTableAiExplanation(self, table_name: str) -> str:
        clean_name = table_name.strip()
        if clean_name in self._table_errors:
            return self._table_errors[clean_name].get("explanation", "")
        for t in self._tables:
            if t["table_name"] == clean_name:
                return t.get("ai_explanation", "")
        return ""

    @Slot(str, result=str)
    def getTableSuggestedSql(self, table_name: str) -> str:
        clean_name = table_name.strip()
        if clean_name in self._table_errors:
            return self._table_errors[clean_name].get("suggested_sql", "")
        for t in self._tables:
            if t["table_name"] == clean_name:
                return t.get("suggested_sql", "")
        return ""

    @Slot(str, result=str)
    def getTableAiPrompt(self, table_name: str) -> str:
        clean_name = table_name.strip()
        if clean_name in self._table_errors:
            return self._table_errors[clean_name].get("prompt", "")
        for t in self._tables:
            if t["table_name"] == clean_name:
                return t.get("ai_prompt", "")
        return ""

    @Slot(str, str)
    def testOllamaConnectionAsync(self, base_url: str, model: str):
        url = base_url.strip() or self._config.get("ollama_url", "http://localhost:11434")
        mdl = model.strip() or self._config.get("ollama_model", "qwen2.5-coder:1.5b")
        self.appendLog("INFO", f"[Ollama] Testing connection to {url} ({mdl})...")

        def _test_task():
            ok, msg = test_ollama_connection(url, mdl)
            if ok:
                self.appendLog("SUCCESS", f"[Ollama] {msg}")
                self.notificationEmitted.emit("success", msg)
            else:
                self.appendLog("ERROR", f"[Ollama] {msg}")
                self.notificationEmitted.emit("error", msg)
            self.ollamaTestFinished.emit(ok, msg)

        threading.Thread(target=_test_task, daemon=True).start()

    @Slot(str, str, result=str)
    def testOllamaConnection(self, base_url: str, model: str) -> str:
        self.testOllamaConnectionAsync(base_url, model)
        return "Testing..."

    # -----------------------------------------------------------------------
    # Settings
    # -----------------------------------------------------------------------

    @Slot(str, int, str, str, str, str, str, str, str, bool, bool, bool, bool, str, str, str, bool)
    @Slot(str, int, str, str, str, str, str, str, str, bool, bool, bool, str, str, str, bool)
    def updateSettings(
        self,
        host: str,
        port: int,
        user: str,
        scheme: str,
        source_cat: str,
        target_cat: str,
        output_dir: str,
        exclude_cols: str,
        exclude_suf: str,
        trim_strings: bool,
        notify_table: bool = True,
        notify_batch: bool = True,
        enable_ai_diagnosis: bool = True,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:1.5b",
        ai_effort: str = "High",
        auto_ai: bool = True
    ):
        if isinstance(enable_ai_diagnosis, str):
            # Called with old 16-parameter overload (where arg 13 was ollama_url)
            real_enable_ai = True
            real_ollama_url = enable_ai_diagnosis.strip() or "http://localhost:11434"
            real_ollama_model = ollama_url.strip() or "qwen2.5-coder:1.5b"
            real_ai_effort = ollama_model.strip() or "High"
            real_auto_ai = bool(ai_effort) if not isinstance(ai_effort, str) else True
        else:
            real_enable_ai = bool(enable_ai_diagnosis)
            real_ollama_url = ollama_url.strip() or "http://localhost:11434"
            real_ollama_model = ollama_model.strip() or "qwen2.5-coder:1.5b"
            real_ai_effort = ai_effort.strip() or "High"
            real_auto_ai = bool(auto_ai)

        self._config["trino_host"] = host.strip()
        self._config["trino_port"] = port
        self._config["trino_user"] = user.strip()
        self._config["http_scheme"] = scheme.strip()
        self._config["source_catalog"] = source_cat.strip()
        self._config["target_catalog"] = target_cat.strip()
        self._config["output_dir"] = output_dir.strip()
        self._config["exclude_columns"] = exclude_cols.strip()
        self._config["exclude_suffix"] = exclude_suf.strip()
        self._config["trim_strings"] = trim_strings
        self._config["notify_table_complete"] = bool(notify_table)
        self._config["notify_batch_complete"] = bool(notify_batch)
        self._config["enable_ai_diagnosis"] = real_enable_ai
        self._config["ollama_url"] = real_ollama_url
        self._config["ollama_model"] = real_ollama_model
        self._config["ai_effort"] = real_ai_effort
        self._config["auto_ai_diagnosis"] = real_auto_ai

        save_config(self._config)
        self.configChanged.emit()
        self.notificationEmitted.emit("success", "Settings saved successfully.")
        self.appendLog("INFO", "Configuration updated and saved.")

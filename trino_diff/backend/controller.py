import os
import sys
import subprocess
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot, Property, QThread

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
TRINO_DIFF_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(TRINO_DIFF_DIR)

from trino_diff.backend.config_manager import load_config, save_config
from trino_diff.backend.trino_client import test_trino_connection, fetch_trino_catalogs, get_trino_connection
from trino_diff.backend.excel_loader import load_tables_from_excel
from trino_diff.backend.worker import TrinoDiffWorker
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
    configChanged = Signal()
    runningStateChanged = Signal()
    progressChanged = Signal()
    statusTextChanged = Signal()
    sqlPreviewReady = Signal(str, str)  # (table_name, sql_text)
    notificationEmitted = Signal(str, str)  # (type: 'success'|'error'|'info'|'warning', message)

    def __init__(self):
        super().__init__()
        self._config = load_config()
        self._catalogs = ["postgres", "oracle"]
        self._tables = []
        self._logs = []
        self._output_files = []
        self._is_running = False
        self._progress_val = 0
        self._progress_max = 100
        self._status_text = "Ready"
        self._worker_thread = None
        self._worker = None

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
        # Remove file:/// URL prefix if passed from QML FileDialog
        clean_path = file_path.replace("file:///", "").replace("file://", "")
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
        self.runningStateChanged.emit()
        self.progressChanged.emit()
        self.statusTextChanged.emit()

        # Create worker & thread
        self._worker_thread = QThread()
        self._worker = TrinoDiffWorker(tasks, self._config)
        self._worker.moveToThread(self._worker_thread)

        self._worker.logEmitted.connect(self.appendLog)
        self._worker.progressUpdated.connect(self._onWorkerProgress)
        self._worker.tableStatusUpdated.connect(self._onWorkerTableStatus)
        self._worker.tableFinished.connect(self._onWorkerTableFinished)
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

        self._is_running = True
        self._progress_val = 0
        self._progress_max = 1
        self._status_text = f"Processing {clean_table}..."
        self.runningStateChanged.emit()
        self.progressChanged.emit()
        self.statusTextChanged.emit()

        self._worker_thread = QThread()
        self._worker = TrinoDiffWorker([task], cfg_copy)
        self._worker.moveToThread(self._worker_thread)

        self._worker.logEmitted.connect(self.appendLog)
        self._worker.progressUpdated.connect(self._onWorkerProgress)
        self._worker.tableStatusUpdated.connect(self._onWorkerTableStatus)
        self._worker.tableFinished.connect(self._onWorkerTableFinished)
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

    def _onWorkerTableStatus(self, table_name: str, status: str, diff_count: int):
        for t in self._tables:
            if t["table_name"] == table_name:
                t["status"] = status
                if status == "Completed":
                    t["diff_count"] = diff_count
                    t["last_run"] = datetime.now().strftime("%H:%M:%S")
                break
        self.tablesChanged.emit()

    def _onWorkerTableFinished(self, table_name: str, sql_file: str, xlsx_file: str):
        self.refreshOutputFiles()

    def _onWorkerAllFinished(self, success_cnt: int, error_cnt: int):
        self._is_running = False
        self._status_text = f"Finished: {success_cnt} succeeded, {error_cnt} failed"
        self.runningStateChanged.emit()
        self.statusTextChanged.emit()
        self.refreshOutputFiles()

        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None

        if error_cnt == 0:
            self.notificationEmitted.emit("success", f"Execution complete: {success_cnt} table(s) processed.")
        else:
            self.notificationEmitted.emit("warning", f"Finished with {error_cnt} error(s). Check logs for details.")

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

    # -----------------------------------------------------------------------
    # Output Files Management
    # -----------------------------------------------------------------------

    @Slot()
    def refreshOutputFiles(self):
        output_dir = self._config.get("output_dir", os.path.join(PROJECT_ROOT, "output"))
        files = []
        if os.path.exists(output_dir):
            for fn in sorted(os.listdir(output_dir), reverse=True):
                fp = os.path.join(output_dir, fn)
                if os.path.isfile(fp):
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in (".xlsx", ".sql"):
                        st = os.stat(fp)
                        size_kb = round(st.st_size / 1024, 1)
                        mod_time = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        files.append({
                            "name": fn,
                            "path": fp,
                            "type": "Excel" if ext == ".xlsx" else "SQL",
                            "size": f"{size_kb} KB",
                            "modified": mod_time,
                        })
        self._output_files = files
        self.outputFilesChanged.emit()

    @Slot(str)
    def openFile(self, path: str):
        if not os.path.exists(path):
            self.notificationEmitted.emit("error", f"File not found: {path}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            self.notificationEmitted.emit("error", f"Could not open file: {e}")

    @Slot(str)
    def openFolder(self, path: str):
        folder = path if os.path.isdir(path) else os.path.dirname(path)
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
        if os.path.exists(path):
            try:
                os.remove(path)
                self.appendLog("INFO", f"Deleted: {os.path.basename(path)}")
                self.refreshOutputFiles()
            except Exception as e:
                self.notificationEmitted.emit("error", f"Could not delete file: {e}")

    # -----------------------------------------------------------------------
    # Settings
    # -----------------------------------------------------------------------

    @Slot(str, int, str, str, str, str, str, str, str, bool)
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
        trim_strings: bool
    ):
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

        save_config(self._config)
        self.configChanged.emit()
        self.notificationEmitted.emit("success", "Settings saved successfully.")
        self.appendLog("INFO", "Configuration updated and saved.")

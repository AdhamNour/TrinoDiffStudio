import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import create_engine, event, desc
from sqlalchemy.orm import sessionmaker, scoped_session

try:
    from trino_diff.backend.db_models import (
        Base,
        AppConfigModel,
        ExcelMappingModel,
        ExcelMappingTableModel,
        BatchModel,
        BatchTableResultModel,
        OutputFileModel,
    )
except ImportError:
    from backend.db_models import (
        Base,
        AppConfigModel,
        ExcelMappingModel,
        ExcelMappingTableModel,
        BatchModel,
        BatchTableResultModel,
        OutputFileModel,
    )


def get_db_path() -> str:
    """Return the absolute path to the SQLite database in the user's Documents directory."""
    docs_dir = os.path.join(os.path.expanduser("~"), "Documents", "TrinoDiffStudio")
    os.makedirs(docs_dir, exist_ok=True)
    return os.path.join(docs_dir, "trino_diff.db")


class DatabaseManager:
    """
    SQLAlchemy ORM Database Manager for Trino Diff Studio.
    Provides ORM-mapped persistence for configuration history, Excel mapping models,
    batch lifecycle objects, individual table diff results, and output file links.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        if self._initialized:
            return
        self.db_path = db_path or get_db_path()
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"timeout": 30.0},
            pool_pre_ping=True,
            echo=False
        )

        # Configure SQLite WAL mode and foreign keys via connection listener
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.close()

        # Create all tables defined in SQLAlchemy ORM models
        Base.metadata.create_all(self.engine)

        self.SessionFactory = scoped_session(
            sessionmaker(bind=self.engine, autoflush=True, autocommit=False, expire_on_commit=False)
        )
        self._initialized = True

    def get_session(self):
        """Return a scoped SQLAlchemy session."""
        return self.SessionFactory()

    # =========================================================================
    # Configuration Management (ORM)
    # =========================================================================

    def save_app_config(self, config: dict) -> bool:
        """Persist a configuration snapshot into SQLite and mark it active."""
        session = self.get_session()
        try:
            # Mark all existing configs as inactive
            session.query(AppConfigModel).filter(AppConfigModel.is_active.is_(True)).update(
                {"is_active": False}
            )

            new_config = AppConfigModel(
                is_active=True,
                config_json=json.dumps(config),
                trino_host=config.get("trino_host", "localhost"),
                trino_port=int(config.get("trino_port", 8080)),
                trino_user=config.get("trino_user", "admin"),
                http_scheme=config.get("http_scheme", "http"),
                source_catalog=config.get("source_catalog", "postgres"),
                target_catalog=config.get("target_catalog", "oracle"),
                output_dir=config.get("output_dir", ""),
                excel_path=config.get("excel_path", ""),
                exclude_columns=config.get("exclude_columns", ""),
                exclude_suffix=config.get("exclude_suffix", ""),
                trim_strings=bool(config.get("trim_strings", True)),
                notify_table_complete=bool(config.get("notify_table_complete", True)),
                notify_batch_complete=bool(config.get("notify_batch_complete", True)),
                enable_ai_diagnosis=bool(config.get("enable_ai_diagnosis", True)),
                ollama_url=config.get("ollama_url", "http://localhost:11434"),
                ollama_model=config.get("ollama_model", "qwen2.5-coder:1.5b"),
                ai_effort=config.get("ai_effort", "High"),
                auto_ai_diagnosis=bool(config.get("auto_ai_diagnosis", True)),
            )
            session.add(new_config)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"[SQLAlchemy Error] save_app_config failed: {e}")
            return False
        finally:
            session.close()

    def get_latest_app_config(self) -> Optional[dict]:
        """Fetch the latest active configuration snapshot via ORM."""
        session = self.get_session()
        try:
            row = (
                session.query(AppConfigModel)
                .filter(AppConfigModel.is_active.is_(True))
                .order_by(desc(AppConfigModel.id))
                .first()
            )
            if row and row.config_json:
                return json.loads(row.config_json)
        except Exception as e:
            print(f"[SQLAlchemy Error] get_latest_app_config failed: {e}")
        finally:
            session.close()
        return None

    # =========================================================================
    # Excel Mapping Management (ORM)
    # =========================================================================

    def save_excel_mapping(self, excel_path: str, tables: List[Dict[str, Any]]) -> Optional[int]:
        """Persist mapping workbook and related table models via ORM relationship."""
        if not os.path.exists(excel_path):
            return None
        session = self.get_session()
        try:
            stat = os.stat(excel_path)
            file_size = stat.st_size
            file_mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            file_name = os.path.basename(excel_path)

            # Deactivate previous mappings
            session.query(ExcelMappingModel).filter(ExcelMappingModel.is_active.is_(True)).update(
                {"is_active": False}
            )

            mapping = ExcelMappingModel(
                excel_path=excel_path,
                excel_file_name=file_name,
                file_size=file_size,
                file_mtime=file_mtime,
                table_count=len(tables),
                is_active=True,
            )

            for t in tables:
                id_cols = t.get("id_columns", [])
                tbl_model = ExcelMappingTableModel(
                    table_name=t.get("table_name", "").lower(),
                    display_name=t.get("display_name", t.get("table_name", "")),
                    id_columns_json=json.dumps(id_cols),
                )
                mapping.tables.append(tbl_model)

            session.add(mapping)
            session.commit()
            return mapping.id
        except Exception as e:
            session.rollback()
            print(f"[SQLAlchemy Error] save_excel_mapping failed: {e}")
            return None
        finally:
            session.close()

    def get_latest_excel_mapping(self) -> Optional[Tuple[dict, List[dict]]]:
        """Fetch the active Excel mapping and all associated tables."""
        session = self.get_session()
        try:
            mapping = (
                session.query(ExcelMappingModel)
                .filter(ExcelMappingModel.is_active.is_(True))
                .order_by(desc(ExcelMappingModel.id))
                .first()
            )
            if not mapping:
                return None

            mapping_dict = {
                "id": mapping.id,
                "excel_path": mapping.excel_path,
                "excel_file_name": mapping.excel_file_name,
                "file_size": mapping.file_size,
                "file_mtime": mapping.file_mtime,
                "table_count": mapping.table_count,
            }

            tables = []
            for t in mapping.tables:
                tables.append({
                    "table_name": t.table_name,
                    "display_name": t.display_name,
                    "id_columns": json.loads(t.id_columns_json),
                    "status": "Ready",
                    "selected": True,
                    "diff_count": 0,
                    "last_run": "",
                })
            return mapping_dict, tables
        except Exception as e:
            print(f"[SQLAlchemy Error] get_latest_excel_mapping failed: {e}")
            return None
        finally:
            session.close()

    # =========================================================================
    # Batch Lifecycle Management (ORM)
    # =========================================================================

    def create_batch(
        self,
        batch_id: str,
        batch_type: str,
        source_catalog: str,
        target_catalog: str,
        output_dir: str,
        total_tables: int,
        excel_path: Optional[str] = None,
        config_snapshot: Optional[dict] = None
    ) -> bool:
        """Create a new BatchModel record via ORM."""
        session = self.get_session()
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            batch = BatchModel(
                batch_id=batch_id,
                batch_type=batch_type,
                source_catalog=source_catalog,
                target_catalog=target_catalog,
                excel_path=excel_path or "",
                output_dir=output_dir,
                status="RUNNING",
                total_tables=total_tables,
                success_count=0,
                error_count=0,
                total_diffs=0,
                started_at=now_str,
                config_snapshot_json=json.dumps(config_snapshot) if config_snapshot else "{}"
            )
            session.merge(batch)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"[SQLAlchemy Error] create_batch failed: {e}")
            return False
        finally:
            session.close()

    def finish_batch(
        self,
        batch_id: str,
        status: str,
        success_count: int,
        error_count: int,
        total_diffs: int
    ) -> bool:
        """Update batch status, completion timestamp, and duration."""
        session = self.get_session()
        try:
            batch = session.query(BatchModel).filter(BatchModel.batch_id == batch_id).first()
            if not batch:
                return False

            now = datetime.now()
            duration = 0.0
            if batch.started_at:
                try:
                    started = datetime.strptime(batch.started_at, "%Y-%m-%d %H:%M:%S")
                    duration = max(0.0, (now - started).total_seconds())
                except Exception:
                    pass

            batch.status = status
            batch.success_count = success_count
            batch.error_count = error_count
            batch.total_diffs = total_diffs
            batch.finished_at = now.strftime("%Y-%m-%d %H:%M:%S")
            batch.duration_seconds = duration

            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"[SQLAlchemy Error] finish_batch failed: {e}")
            return False
        finally:
            session.close()

    # =========================================================================
    # Table Results & Output Files (ORM)
    # =========================================================================

    def record_table_result(
        self,
        batch_id: str,
        table_name: str,
        status: str,
        diff_count: int = 0,
        id_columns: Optional[list] = None,
        schema_name: Optional[str] = None,
        sql_file_path: Optional[str] = None,
        report_file_path: Optional[str] = None,
        report_file_type: Optional[str] = None,
        error_message: Optional[str] = None,
        failed_query: Optional[str] = None,
        ai_status: Optional[str] = None,
        ai_explanation: Optional[str] = None,
        ai_suggested_sql: Optional[str] = None,
        ai_prompt: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None
    ) -> bool:
        """Persist a single table comparison result via ORM."""
        session = self.get_session()
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            duration = 0.0
            if started_at and finished_at:
                try:
                    s_dt = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
                    f_dt = datetime.strptime(finished_at, "%Y-%m-%d %H:%M:%S")
                    duration = max(0.0, (f_dt - s_dt).total_seconds())
                except Exception:
                    pass

            tbl_result = BatchTableResultModel(
                batch_id=batch_id,
                table_name=table_name,
                status=status,
                diff_count=diff_count,
                id_columns_json=json.dumps(id_columns or []),
                schema_name=schema_name or "",
                sql_file_path=sql_file_path or "",
                report_file_path=report_file_path or "",
                report_file_type=report_file_type or "",
                error_message=error_message or "",
                failed_query=failed_query or "",
                ai_status=ai_status or "Idle",
                ai_explanation=ai_explanation or "",
                ai_suggested_sql=ai_suggested_sql or "",
                ai_prompt=ai_prompt or "",
                started_at=started_at or now_str,
                finished_at=finished_at or now_str,
                duration_seconds=duration,
            )
            session.add(tbl_result)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"[SQLAlchemy Error] record_table_result failed: {e}")
            return False
        finally:
            session.close()

    def record_output_file(
        self,
        batch_id: Optional[str],
        table_name: Optional[str],
        file_path: str,
        file_type: str
    ) -> bool:
        """Upsert an output file record in SQLite via ORM."""
        if not os.path.exists(file_path):
            return False
        session = self.get_session()
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            existing = session.query(OutputFileModel).filter(OutputFileModel.file_path == file_path).first()
            if existing:
                if batch_id:
                    existing.batch_id = batch_id
                if table_name:
                    existing.table_name = table_name
                existing.file_size_bytes = file_size
                existing.created_at = datetime.utcnow()
            else:
                new_file = OutputFileModel(
                    batch_id=batch_id,
                    table_name=table_name or "",
                    file_name=file_name,
                    file_path=file_path,
                    file_type=file_type,
                    file_size_bytes=file_size,
                )
                session.add(new_file)

            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"[SQLAlchemy Error] record_output_file failed: {e}")
            return False
        finally:
            session.close()

    # =========================================================================
    # Query Methods for UI (ORM)
    # =========================================================================

    def get_batches_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return list of recent batches for UI dropdown and history."""
        session = self.get_session()
        try:
            batches = (
                session.query(BatchModel)
                .order_by(desc(BatchModel.started_at))
                .limit(limit)
                .all()
            )
            return [b.to_dict() for b in batches]
        except Exception as e:
            print(f"[SQLAlchemy Error] get_batches_list failed: {e}")
            return []
        finally:
            session.close()

    def get_batch_details(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full batch summary with related table results and output files."""
        session = self.get_session()
        try:
            batch = session.query(BatchModel).filter(BatchModel.batch_id == batch_id).first()
            if not batch:
                return None

            data = batch.to_dict()
            data["tables"] = [t.to_dict() for t in batch.table_results]
            data["files"] = [f.to_dict() for f in batch.output_files]
            return data
        except Exception as e:
            print(f"[SQLAlchemy Error] get_batch_details failed: {e}")
            return None
        finally:
            session.close()

    def get_output_files_by_batch(self, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query output files filtered by batch_id."""
        session = self.get_session()
        try:
            query = session.query(OutputFileModel)
            if batch_id and batch_id.strip() and batch_id != "ALL":
                query = query.filter(OutputFileModel.batch_id == batch_id.strip())

            records = query.order_by(desc(OutputFileModel.id)).all()
            files = []
            for r in records:
                fpath = r.file_path
                if os.path.exists(fpath):
                    item = r.to_dict()
                    mtime = os.path.getmtime(fpath)
                    item["modified"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    size_kb = os.path.getsize(fpath) / 1024
                    item["size"] = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"
                    files.append(item)
            return files
        except Exception as e:
            print(f"[SQLAlchemy Error] get_output_files_by_batch failed: {e}")
            return []
        finally:
            session.close()

    def get_latest_report_for_table(self, table_name: str, file_type: str = "Excel") -> Optional[str]:
        """Find the latest report file path for a table from SQLite records."""
        session = self.get_session()
        try:
            clean_tbl = table_name.strip().lower()
            clean_base = clean_tbl.replace(".", "_")
            tbl_only = clean_tbl.split(".")[-1]

            # 1. Check OutputFileModel (strictly .xlsx only)
            out_files = (
                session.query(OutputFileModel)
                .filter(
                    (
                        (OutputFileModel.table_name.in_([clean_tbl, clean_base, tbl_only, table_name])) |
                        (OutputFileModel.file_name.ilike(f"{clean_base}_diff%.xlsx")) |
                        (OutputFileModel.file_name.ilike(f"{clean_tbl}_diff%.xlsx")) |
                        (OutputFileModel.file_name.ilike(f"{tbl_only}_diff%.xlsx"))
                    ),
                    OutputFileModel.file_name.ilike("%.xlsx"),
                    OutputFileModel.file_path.ilike("%.xlsx")
                )
                .order_by(desc(OutputFileModel.id))
                .all()
            )
            for of in out_files:
                if of.file_path and of.file_path.lower().endswith(".xlsx") and os.path.isfile(of.file_path):
                    return of.file_path

            # 2. Check BatchTableResultModel (strictly .xlsx only)
            tbl_results = (
                session.query(BatchTableResultModel)
                .filter(
                    (
                        (BatchTableResultModel.table_name.in_([clean_tbl, clean_base, tbl_only, table_name])) |
                        (BatchTableResultModel.table_name.ilike(f"%{clean_base}%")) |
                        (BatchTableResultModel.table_name.ilike(f"%{tbl_only}%"))
                    ),
                    BatchTableResultModel.report_file_path.ilike("%.xlsx")
                )
                .order_by(desc(BatchTableResultModel.id))
                .all()
            )
            for tr in tbl_results:
                if tr.report_file_path and tr.report_file_path.lower().endswith(".xlsx") and os.path.isfile(tr.report_file_path):
                    return tr.report_file_path

            return None
        except Exception as e:
            print(f"[SQLAlchemy Error] get_latest_report_for_table failed: {e}")
            return None
        finally:
            session.close()

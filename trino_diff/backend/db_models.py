import os
import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey, Index, event
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class AppConfigModel(Base):
    """SQLAlchemy ORM Model for Application Configuration Snapshots."""
    __tablename__ = "app_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True, index=True)
    config_json = Column(Text, nullable=False)
    trino_host = Column(String(255))
    trino_port = Column(Integer)
    trino_user = Column(String(255))
    http_scheme = Column(String(50))
    source_catalog = Column(String(255))
    target_catalog = Column(String(255))
    output_dir = Column(Text)
    excel_path = Column(Text)
    exclude_columns = Column(Text)
    exclude_suffix = Column(String(255))
    trim_strings = Column(Boolean, default=True)
    notify_table_complete = Column(Boolean, default=True)
    notify_batch_complete = Column(Boolean, default=True)
    enable_ai_diagnosis = Column(Boolean, default=True)
    ollama_url = Column(String(255))
    ollama_model = Column(String(255))
    ai_effort = Column(String(50))
    auto_ai_diagnosis = Column(Boolean, default=True)


class ExcelMappingModel(Base):
    """SQLAlchemy ORM Model for Excel Mapping Workbooks."""
    __tablename__ = "excel_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loaded_at = Column(DateTime, default=datetime.utcnow)
    excel_path = Column(Text, nullable=False)
    excel_file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0)
    file_mtime = Column(String(50))
    table_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, index=True)

    tables = relationship(
        "ExcelMappingTableModel",
        back_populates="mapping",
        cascade="all, delete-orphan",
        lazy="joined"
    )


class ExcelMappingTableModel(Base):
    """SQLAlchemy ORM Model for Individual Tables within an Excel Mapping."""
    __tablename__ = "excel_mapping_tables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapping_id = Column(Integer, ForeignKey("excel_mappings.id", ondelete="CASCADE"), nullable=False, index=True)
    table_name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    id_columns_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    mapping = relationship("ExcelMappingModel", back_populates="tables")


class BatchModel(Base):
    """SQLAlchemy ORM Model for Diff Execution Batches."""
    __tablename__ = "batches"

    batch_id = Column(String(100), primary_key=True)
    batch_type = Column(String(50), default="BATCH")
    source_catalog = Column(String(255), nullable=False)
    target_catalog = Column(String(255), nullable=False)
    excel_path = Column(Text)
    mapping_id = Column(Integer, ForeignKey("excel_mappings.id", ondelete="SET NULL"), nullable=True)
    output_dir = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="RUNNING")
    total_tables = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    total_diffs = Column(Integer, default=0)
    started_at = Column(String(50), nullable=False, index=True)
    finished_at = Column(String(50), nullable=True)
    duration_seconds = Column(Float, default=0.0)
    config_snapshot_json = Column(Text, nullable=True)

    table_results = relationship(
        "BatchTableResultModel",
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="select"
    )
    output_files = relationship(
        "OutputFileModel",
        back_populates="batch",
        lazy="select"
    )

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "batch_type": self.batch_type,
            "source_catalog": self.source_catalog,
            "target_catalog": self.target_catalog,
            "status": self.status,
            "total_tables": self.total_tables,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_diffs": self.total_diffs,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "output_dir": self.output_dir,
            "excel_path": self.excel_path,
        }


class BatchTableResultModel(Base):
    """SQLAlchemy ORM Model for Individual Table Diff Results."""
    __tablename__ = "batch_table_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(100), ForeignKey("batches.batch_id", ondelete="CASCADE"), nullable=False, index=True)
    table_name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)
    diff_count = Column(Integer, default=0)
    id_columns_json = Column(Text)
    schema_name = Column(String(255))
    sql_file_path = Column(Text)
    report_file_path = Column(Text)
    report_file_type = Column(String(50))
    error_message = Column(Text)
    failed_query = Column(Text)
    ai_status = Column(String(50), default="Idle")
    ai_explanation = Column(Text)
    ai_suggested_sql = Column(Text)
    ai_prompt = Column(Text)
    started_at = Column(String(50))
    finished_at = Column(String(50))
    duration_seconds = Column(Float, default=0.0)

    batch = relationship("BatchModel", back_populates="table_results")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "table_name": self.table_name,
            "status": self.status,
            "diff_count": self.diff_count,
            "id_columns": json.loads(self.id_columns_json) if self.id_columns_json else [],
            "schema_name": self.schema_name,
            "sql_file_path": self.sql_file_path,
            "report_file_path": self.report_file_path,
            "report_file_type": self.report_file_type,
            "error_message": self.error_message,
            "failed_query": self.failed_query,
            "ai_status": self.ai_status,
            "ai_explanation": self.ai_explanation,
            "ai_suggested_sql": self.ai_suggested_sql,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
        }


class OutputFileModel(Base):
    """SQLAlchemy ORM Model for Output Report Files and SQL Scripts."""
    __tablename__ = "output_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(100), ForeignKey("batches.batch_id", ondelete="SET NULL"), nullable=True, index=True)
    table_name = Column(String(255))
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False, unique=True)
    file_type = Column(String(50), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("BatchModel", back_populates="output_files")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "table_name": self.table_name,
            "name": self.file_name,
            "path": self.file_path,
            "type": self.file_type,
            "size_bytes": self.file_size_bytes,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
        }

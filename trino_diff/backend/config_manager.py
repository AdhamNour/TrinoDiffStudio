import json
import os
try:
    from trino_diff.backend.db_manager import DatabaseManager
except ImportError:
    from backend.db_manager import DatabaseManager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "app_config.json")

DEFAULT_CONFIG = {
    "trino_host": "localhost",
    "trino_port": 8080,
    "trino_user": "admin",
    "http_scheme": "http",
    "source_catalog": "postgres",
    "target_catalog": "oracle",
    "default_schemas": "curated, rdm",
    "output_dir": os.path.join(PROJECT_ROOT, "output"),
    "excel_path": os.path.join(PROJECT_ROOT, "Oracle_to_Postgre_Business_Columns 2.xlsx"),
    "exclude_columns": "extraction_timestamp",
    "exclude_suffix": "key",
    "trim_strings": True,
    "notify_table_complete": True,
    "notify_batch_complete": True,
    "enable_ai_diagnosis": True,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5-coder:1.5b",
    "ai_effort": "High",
    "auto_ai_diagnosis": True,
}


def load_config() -> dict:
    """
    Load configuration from SQLite database if available,
    falling back to app_config.json and DEFAULT_CONFIG.
    """
    db = DatabaseManager()
    db_config = db.get_latest_app_config()
    if db_config:
        config = DEFAULT_CONFIG.copy()
        config.update(db_config)
        return config

    # Fallback to app_config.json
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(saved)
                # Seed into SQLite
                db.save_app_config(config)
                return config
        except Exception:
            pass

    config = DEFAULT_CONFIG.copy()
    db.save_app_config(config)
    return config


def save_config(config: dict) -> bool:
    """Save configuration dictionary to both app_config.json and SQLite database."""
    success_json = False
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        success_json = True
    except Exception as e:
        print(f"[ERROR] Failed to save config to JSON: {e}")

    db = DatabaseManager()
    success_db = db.save_app_config(config)

    return success_json or success_db

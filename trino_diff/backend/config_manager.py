import json
import os

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
}


def load_config() -> dict:
    """Load configuration from file or return default."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(saved)
                return config
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> bool:
    """Save configuration dictionary to file."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save config: {e}")
        return False

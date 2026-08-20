"""
Application Version Management
==============================
Provides dynamic version resolution:
- Uses APP_VERSION environment variable or bundled version.json in built releases.
- Defaults to 'dev' when running directly from python source code.
"""

import os
import sys
import json


def get_app_version() -> str:
    """
    Return the application version.
    - If running in frozen bundle (PyInstaller) or build environment with version file / env var: returns that version.
    - If running directly from python command in development: returns 'dev'.
    """
    # 1. Environment variable (highest priority for CI or explicit override)
    env_ver = os.environ.get("APP_VERSION") or os.environ.get("TRINO_DIFF_VERSION")
    if env_ver and env_ver.strip():
        return env_ver.strip()

    # 2. Bundled or local version.json
    base_dirs = []
    if getattr(sys, "frozen", False):
        base_dirs.append(getattr(sys, "_MEIPASS", ""))
        base_dirs.append(os.path.dirname(sys.executable))

    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dirs.append(current_dir)
    base_dirs.append(os.path.dirname(current_dir))

    for bdir in base_dirs:
        if not bdir:
            continue
        for candidate in ["version.json", os.path.join("trino_diff", "version.json")]:
            v_file = os.path.join(bdir, candidate)
            if os.path.isfile(v_file):
                try:
                    with open(v_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        ver = data.get("version", "").strip()
                        if ver:
                            return ver
                except Exception:
                    pass

    # 3. Default to "dev" when running from Python command
    return "dev"


__version__ = get_app_version()

#!/usr/bin/env python3
"""
Run `dbt docs generate --target postgres_curated` from ./dbt, excluding any
configured paths. Whenever it fails for a reason that can be tied to a
specific model file, rename that file to .sql.disabled so dbt ignores it on
the next run, log the action to an Excel file, and retry.

Handles:
  - depends on a node named 'X' which is disabled
  - depends on a node named 'X' which was not found
  - Found a cycle: model.proj.A --> model.proj.B [--> ...]
  - Generic "<Something> Error in model X (path/to/X.sql)"
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

DBT_DIR = "./dbt"

# Project-relative paths to exclude from the dbt run.
# (The absolute Windows path C:\Users\anhassan\airflow-dags\dbt\models\staging\T24
# becomes models/staging/T24 once we chdir into ./dbt.)
EXCLUDE_PATHS = [
    "models/staging/T24",
]

BASE_CMD = ["dbt", "docs", "generate", "--target", "postgres_curated"]
CMD = list(BASE_CMD)
for _p in EXCLUDE_PATHS:
    CMD.extend(["--exclude", f"path:{_p}"])

MAX_ITERATIONS = 200
LOG_FILE = f"dbt_disabled_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"  # written inside DBT_DIR
SEARCH_ROOTS = ["models", "seeds", "snapshots", "analyses"]

LOG_HEADERS = [
    "Timestamp",
    "Attempt",
    "Disabled File",
    "Error Category",
    "Detail",
    "Error Snippet",
]
COLUMN_WIDTHS = [20, 8, 55, 24, 60, 90]

# --- Error detection ---------------------------------------------------------

DEP_RE = re.compile(
    r"Model\s+'(?P<model>[^']+)'\s+\((?P<path>[^)]+\.sql)\)\s+"
    r"depends on a node named\s+'(?P<dep>[^']+)'\s+"
    r"which\s+(?P<kind>is disabled|was not found)",
    re.IGNORECASE,
)

DEP_PHRASE_RE = re.compile(
    r"depends on a node named\s+'(?P<dep>[^']+)'\s+"
    r"which\s+(?P<kind>is disabled|was not found)",
    re.IGNORECASE,
)

CYCLE_RE = re.compile(
    r"Found a cycle:\s*(?P<chain>\S+(?:\s*-->\s*\S+)+)",
    re.IGNORECASE,
)

GENERIC_ERROR_RE = re.compile(
    r"(?P<category>\w+(?:\s+\w+)?)\s+Error\s+in\s+model\s+\S+\s+"
    r"\((?P<path>[^)]+\.sql)\)",
    re.IGNORECASE,
)

SQL_PATH_RE = re.compile(r"\(([^()\s]+\.sql)\)")


def _snippet(text: str, pos: int, before: int = 80, after: int = 280) -> str:
    start = max(0, pos - before)
    end = min(len(text), pos + after)
    return text[start:end].strip().replace("\r", "")


def _extract_cycle_models(chain: str) -> list[str]:
    parts = [p.strip() for p in chain.split("-->") if p.strip()]
    return [p.rsplit(".", 1)[-1] for p in parts]


def find_model_file(model_name: str) -> str | None:
    for root in SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for p in Path(root).rglob(f"{model_name}.sql"):
            return str(p)
    return None


def classify_error(output: str):
    m = DEP_RE.search(output)
    if m:
        kind = m.group("kind").lower()
        category = "Disabled dependency" if "disabled" in kind else "Missing dependency"
        return category, m.group("path"), m.group("dep"), _snippet(output, m.start())

    m = CYCLE_RE.search(output)
    if m:
        chain = m.group("chain").strip()
        models_in_cycle = _extract_cycle_models(chain)
        for name in reversed(models_in_cycle):
            path = find_model_file(name)
            if path:
                return "Cycle", path, chain, _snippet(output, m.start())
        return "Cycle (unresolved)", None, chain, _snippet(output, m.start())

    m = GENERIC_ERROR_RE.search(output)
    if m:
        category = m.group("category").strip().title() + " Error"
        return category, m.group("path"), None, _snippet(output, m.start())

    phrase = DEP_PHRASE_RE.search(output)
    if phrase:
        paths = SQL_PATH_RE.findall(output)
        if paths:
            kind = phrase.group("kind").lower()
            category = "Disabled dependency" if "disabled" in kind else "Missing dependency"
            return category, paths[0], phrase.group("dep"), _snippet(output, phrase.start())

    return None, None, None, None


# --- Side effects ------------------------------------------------------------

def run_dbt():
    print(f"\n>>> Running: {' '.join(CMD)}  (cwd={os.getcwd()})")
    result = subprocess.run(CMD, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def disable_model_file(rel_path: str) -> str | None:
    candidates = [rel_path, os.path.join(".", rel_path)]
    target = next((p for p in candidates if os.path.isfile(p)), None)
    if target is None:
        print(f"!! Could not locate file on disk: {rel_path}", file=sys.stderr)
        return None
    new_path = target + ".disabled"
    os.rename(target, new_path)
    print(f"-- Disabled: {target} -> {new_path}")
    return new_path


def append_log_row(row):
    if os.path.isfile(LOG_FILE):
        wb = load_workbook(LOG_FILE)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Disabled Models"
        ws.append(LOG_HEADERS)
        for i, width in enumerate(COLUMN_WIDTHS, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width
    ws.append(row)
    wb.save(LOG_FILE)


# --- Main loop ---------------------------------------------------------------

def main() -> int:
    if not os.path.isdir(DBT_DIR):
        print(f"!! Directory not found: {DBT_DIR}", file=sys.stderr)
        return 1
    os.chdir(DBT_DIR)
    print(f"Changed working directory to: {os.getcwd()}")
    if EXCLUDE_PATHS:
        print(f"Excluding: {', '.join(EXCLUDE_PATHS)}")
    print(f"Logging disables to: {os.path.abspath(LOG_FILE)}")

    disabled_count = 0

    for attempt in range(1, MAX_ITERATIONS + 1):
        print(f"\n=== Attempt {attempt} ===")
        rc, stdout, stderr = run_dbt()
        combined = (stdout or "") + "\n" + (stderr or "")

        if rc == 0:
            print(f"\n✅ dbt docs generate succeeded after disabling {disabled_count} model(s).")
            return 0

        category, path, detail, snippet = classify_error(combined)
        if not path:
            print(f"\n❌ dbt failed (category={category!r}), couldn't pin to a model file.")
            print("---- stdout ----\n" + stdout)
            print("---- stderr ----\n" + stderr)
            return rc

        extra = f"  (detail: {detail})" if detail else ""
        print(f"!! [{category}] failing model: {path}{extra}")

        new_path = disable_model_file(path)
        if new_path is None:
            return 1

        append_log_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            attempt,
            new_path,
            category,
            detail or "",
            snippet,
        ])
        disabled_count += 1

    print(f"\n❌ Hit MAX_ITERATIONS={MAX_ITERATIONS}, giving up.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
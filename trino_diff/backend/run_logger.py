"""
Per-run text logs
=================
Every batch / single-table diff run is traced in a plain-text file stored in
``<output_dir>/logs`` and named after the run's batch id, for example
``BATCH_20260101_120000.txt`` or ``ADHOC_20260101_120000.txt``.
"""

import os
import re
import secrets
import threading
from datetime import datetime
from typing import Any, Optional, Sequence, Tuple

LOG_DIR_NAME = "logs"
LOG_FILE_EXT = ".txt"
LOG_FILE_TYPE = "Log"  # file_type stored in output_files and shown in the Output Explorer

_RULE = "=" * 80
_CONTINUATION_INDENT = "    "


def new_run_id(prefix: str) -> str:
    """Return a unique run (batch) id such as ``BATCH_20260101_120000_a1b2c3d4``.

    The random 8-character hex suffix keeps ids, and therefore log file names and
    batch rows, unique even for two runs started within the same second.
    """
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"


def get_run_log_dir(output_dir: str) -> str:
    """Return the absolute folder that holds the run logs of the given output directory."""
    return os.path.abspath(os.path.join(output_dir, LOG_DIR_NAME))


def get_run_log_path(output_dir: str, run_id: str) -> str:
    """Return the absolute path of the text log for a run (batch id)."""
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(run_id)).strip("._") or "run"
    return os.path.join(get_run_log_dir(output_dir), safe_id + LOG_FILE_EXT)


class RunLogger:
    """
    Thread-safe, append-only text log for a single run.

    Every record is appended with open/write/close, so the file on disk is always
    complete (even if the app is killed mid-run) and no handle is kept open that
    could block deleting the file. I/O failures never propagate: logging must not
    fail a diff run. The first failure is exposed through ``error``.
    """

    def __init__(self, output_dir: str, run_id: str):
        self.path = get_run_log_path(output_dir, run_id)
        self.error: Optional[str] = None
        self._lock = threading.Lock()

    def write(self, level: str, message: str) -> None:
        """Append one timestamped record; continuation lines of multi-line messages are indented."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        text = str(message).rstrip().replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\n" + _CONTINUATION_INDENT)
        self._append(f"{stamp} | {str(level).upper():<7} | {text}\n")

    def write_block(self, title: str, fields: Sequence[Tuple[str, Any]]) -> None:
        """Append a ruled block of ``label : value`` rows; list values print one item per line."""
        width = max((len(label) for label, value in fields if not isinstance(value, (list, tuple))), default=0)
        lines = [_RULE, title, _RULE]
        for label, value in fields:
            if isinstance(value, (list, tuple)):
                lines.append(f"{label}:")
                lines.extend(f"  {item}" for item in value)
            else:
                lines.append(f"{label:<{width}} : {value}")
        lines.append(_RULE)
        self._append("\n".join(lines) + "\n")

    def _append(self, text: str) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a", encoding="utf-8", errors="replace") as fh:
                    fh.write(text)
            except Exception as exc:
                if self.error is None:
                    self.error = f"{type(exc).__name__}: {exc}"

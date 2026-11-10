"""
Unit tests for the per-run text logs (RunLogger) and their integration in TrinoDiffWorker.

No Trino connection or real database is needed: the worker's connection factory is
patched to fail, which exercises the whole run lifecycle (header, per-table logging,
summary footer, batch registration) without touching external systems.
"""

import os
import re
import tempfile
import threading
import unittest
from unittest import mock

from trino_diff.backend import worker as worker_module
from trino_diff.backend.run_logger import (
    LOG_FILE_TYPE,
    RunLogger,
    get_run_log_dir,
    get_run_log_path,
)

RECORD_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \| [A-Z]{4,7} *\| ")


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class TestRunLogger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "output")

    def test_path_is_inside_logs_folder_and_named_after_the_run(self):
        path = get_run_log_path(self.out, "BATCH_20260101_120000")
        self.assertEqual(path, os.path.join(os.path.abspath(self.out), "logs", "BATCH_20260101_120000.txt"))
        self.assertEqual(os.path.dirname(path), get_run_log_dir(self.out))

    def test_run_id_cannot_escape_the_logs_folder(self):
        path = get_run_log_path(self.out, "../evil/BATCH 1")
        self.assertEqual(os.path.dirname(path), get_run_log_dir(self.out))
        self.assertEqual(os.path.basename(path), "evil_BATCH_1.txt")
        self.assertEqual(os.path.basename(get_run_log_path(self.out, "")), "run.txt")

    def test_record_format(self):
        log = RunLogger(self.out, "BATCH_1")
        log.write("info", "hello")
        log.write("SUCCESS", "done")
        lines = read_text(log.path).splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertRegex(line, RECORD_RE)
        self.assertTrue(lines[0].endswith("| INFO    | hello"))
        self.assertTrue(lines[1].endswith("| SUCCESS | done"))

    def test_multiline_message_keeps_one_record_per_timestamp(self):
        log = RunLogger(self.out, "BATCH_1")
        log.write("ERROR", "first line\nsecond line\r\nthird line")
        lines = read_text(log.path).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertRegex(lines[0], RECORD_RE)
        self.assertEqual(lines[1], "    second line")
        self.assertEqual(lines[2], "    third line")

    def test_trailing_newline_does_not_leave_a_blank_record_line(self):
        log = RunLogger(self.out, "BATCH_1")
        log.write("DEBUG", "Traceback:\n  File x\nValueError: boom\n")
        log.write("INFO", "next")
        lines = read_text(log.path).splitlines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[2], "    ValueError: boom")
        self.assertRegex(lines[3], RECORD_RE)

    def test_block_layout(self):
        log = RunLogger(self.out, "BATCH_1")
        log.write_block("Title", [("Batch ID", "BATCH_1"), ("Status", "OK"), ("Tables (2)", ["a", "b"])])
        lines = read_text(log.path).splitlines()
        self.assertEqual(lines[0], "=" * 80)
        self.assertEqual(lines[1], "Title")
        self.assertEqual(lines[2], "=" * 80)
        self.assertEqual(lines[3], "Batch ID : BATCH_1")
        self.assertEqual(lines[4], "Status   : OK")
        self.assertEqual(lines[5:8], ["Tables (2):", "  a", "  b"])
        self.assertEqual(lines[8], "=" * 80)

    def test_appends_instead_of_overwriting(self):
        RunLogger(self.out, "BATCH_1").write("INFO", "first run")
        second = RunLogger(self.out, "BATCH_1")
        second.write("INFO", "second run")
        text = read_text(second.path)
        self.assertIn("first run", text)
        self.assertIn("second run", text)

    def test_concurrent_writers_keep_records_intact(self):
        log = RunLogger(self.out, "BATCH_1")
        threads_n, per_thread = 8, 100

        def worker(tid):
            for i in range(per_thread):
                log.write("INFO", f"[t{tid}] message {i}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(threads_n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = read_text(log.path).splitlines()
        self.assertEqual(len(lines), threads_n * per_thread)
        for line in lines:
            self.assertRegex(line, RECORD_RE)
        self.assertIsNone(log.error)

    def test_io_failure_is_swallowed_and_reported(self):
        blocker = os.path.join(self.tmp.name, "not_a_folder")
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("x")
        log = RunLogger(blocker, "BATCH_1")  # <file>/logs cannot be created
        log.write("INFO", "lost")
        log.write_block("Title", [("a", "b")])
        self.assertIsNotNone(log.error)
        self.assertFalse(os.path.exists(log.path))

    def test_text_that_cannot_be_encoded_does_not_raise(self):
        log = RunLogger(self.out, "BATCH_1")
        log.write("INFO", "bad \ud800 surrogate and unicode \u2192 arrow")
        self.assertIsNone(log.error)
        self.assertIn("unicode \u2192 arrow", read_text(log.path))


class TestWorkerRunLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(worker_module, "DatabaseManager")
        self.db = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def _config(self, **overrides):
        cfg = {
            "trino_host": "trino.example",
            "trino_port": 8443,
            "trino_user": "tester",
            "trino_password": "s3cret-pw",
            "http_scheme": "https",
            "trino_verify_ssl": True,
            "source_catalog": "postgres",
            "target_catalog": "oracle",
            "output_dir": os.path.join(self.tmp.name, "out"),
            "exclude_columns": "extraction_timestamp",
            "exclude_suffix": "key",
            "trim_strings": True,
            "diff_engine": "direct",
            "iceberg_catalog": "iceberg",
            "iceberg_staging_schema": "staging",
            "iceberg_cleanup_on_error": True,
            "default_schemas": "curated, rdm, historical",
            "excel_path": "mapping.xlsx",
        }
        cfg.update(overrides)
        return cfg

    def _tasks(self, *names):
        return [{"table_name": n, "id_columns": ["id", "code"]} for n in names]

    def _run(self, tasks, batch_id="BATCH_20260101_120000", batch_type="BATCH", cancel=False, **cfg):
        w = worker_module.TrinoDiffWorker(tasks, self._config(**cfg), batch_id=batch_id, batch_type=batch_type)
        finished, emitted = [], []
        w.allFinished.connect(lambda ok, bad: finished.append((ok, bad)))
        w.logEmitted.connect(lambda level, msg: emitted.append((level, msg)))
        if cancel:
            w.cancel()
        with mock.patch.object(worker_module, "get_trino_connection", side_effect=RuntimeError("connection refused")):
            w.run()
        return w, finished, emitted

    def test_batch_run_is_traced_end_to_end(self):
        w, finished, _ = self._run(self._tasks("curated.t1", "curated.t2"))
        text = read_text(w.run_log.path)

        self.assertEqual(finished, [(0, 2)])
        self.assertEqual(
            w.run_log.path,
            os.path.join(os.path.abspath(self._config()["output_dir"]), "logs", "BATCH_20260101_120000.txt"),
        )
        # header
        self.assertIn("Trino Diff Studio - Run Log", text)
        self.assertRegex(text, r"Batch ID\s+: BATCH_20260101_120000")
        self.assertRegex(text, r"Run type\s+: Batch")
        self.assertRegex(text, r"Catalogs\s+: postgres -> oracle")
        self.assertIn("Tables (2):", text)
        self.assertIn("1. curated.t1 (schema: auto; id columns: id, code)", text)
        self.assertIn("2. curated.t2 (schema: auto; id columns: id, code)", text)
        self.assertRegex(text, r"Mapping file\s+: mapping.xlsx")
        # per-table records
        self.assertIn("| INFO    | Starting execution for 2 table(s) [Batch: BATCH_20260101_120000]", text)
        self.assertIn("[curated.t1] Error: connection refused", text)
        self.assertIn("[curated.t2] Error: connection refused", text)
        self.assertIn("Traceback", text)
        # summary
        self.assertRegex(text, r"Status\s+: FAILED")
        self.assertRegex(text, r"Tables succeeded\s+: 0")
        self.assertRegex(text, r"Tables failed\s+: 2")
        self.assertRegex(text, r"Duration\s+: \d+\.\d s")
        # the log is linked to the batch so it can be found from the Output Explorer
        self.db.record_output_file.assert_called_once_with("BATCH_20260101_120000", None, w.run_log.path, LOG_FILE_TYPE)

    def test_password_is_never_written(self):
        w, _, _ = self._run(self._tasks("curated.t1"))
        text = read_text(w.run_log.path)
        self.assertNotIn("s3cret-pw", text)
        self.assertIn("user: tester", text)

    def test_every_emitted_line_reaches_the_file(self):
        w, _, emitted = self._run(self._tasks("curated.t1", "curated.t2"))
        text = read_text(w.run_log.path)
        self.assertTrue(emitted)
        for level, message in emitted:
            self.assertIn(f"| {level:<7} | {message}", text)

    def test_single_run_is_marked_adhoc(self):
        w, finished, _ = self._run(
            [{"table_name": "curated.t1", "id_columns": ["id"], "schema": "rdm"}],
            batch_id="ADHOC_20260101_120000",
            batch_type="ADHOC",
        )
        text = read_text(w.run_log.path)
        self.assertEqual(os.path.basename(w.run_log.path), "ADHOC_20260101_120000.txt")
        self.assertEqual(finished, [(0, 1)])
        self.assertRegex(text, r"Run type\s+: Single table \(ad-hoc\)")
        self.assertIn("1. curated.t1 (schema: rdm; id columns: id)", text)
        self.assertNotIn("Mapping file", text)

    def test_pipelined_run_logs_every_table_with_intact_records(self):
        names = [f"curated.t{i}" for i in range(6)]
        w, finished, _ = self._run(self._tasks(*names), diff_engine="iceberg")
        text = read_text(w.run_log.path)
        self.assertEqual(finished, [(0, 6)])
        self.assertIn("Engine: ICEBERG PIPELINED", text)
        for name in names:
            self.assertIn(f"[{name}] Error: connection refused", text)
        record_lines = [ln for ln in text.splitlines() if " | " in ln and RECORD_RE.match(ln)]
        self.assertGreaterEqual(len(record_lines), 6)

    def test_cancelled_run_is_reported_in_the_summary(self):
        w, finished, _ = self._run(self._tasks("curated.t1", "curated.t2"), cancel=True)
        text = read_text(w.run_log.path)
        self.assertEqual(finished, [(0, 0)])
        self.assertIn("Batch execution stopped by user.", text)
        self.assertRegex(text, r"Status\s+: CANCELLED")

    def test_unexpected_failure_is_traced_and_reraised(self):
        self.db.create_batch.side_effect = RuntimeError("db down")
        w = worker_module.TrinoDiffWorker(self._tasks("curated.t1"), self._config(), batch_id="BATCH_20260101_120000")
        finished = []
        w.allFinished.connect(lambda ok, bad: finished.append((ok, bad)))
        with self.assertRaises(RuntimeError):
            w.run()
        text = read_text(w.run_log.path)
        self.assertEqual(finished, [])
        self.assertIn("Run aborted by an unexpected error: db down", text)
        self.assertIn("Traceback", text)
        self.assertRegex(text, r"Status\s+: ABORTED")
        self.db.record_output_file.assert_called_once()

    def test_logging_failure_warns_once_and_never_breaks_the_run(self):
        with mock.patch("trino_diff.backend.run_logger.open", side_effect=PermissionError("denied"), create=True):
            w, finished, emitted = self._run(self._tasks("curated.t1", "curated.t2"))
        warnings = [m for lvl, m in emitted if lvl == "WARN" and "Run log could not be saved" in m]
        self.assertEqual(finished, [(0, 2)])
        self.assertEqual(len(warnings), 1)
        self.assertIn("PermissionError", w.run_log.error)
        self.assertFalse(os.path.exists(w.run_log.path))


if __name__ == "__main__":
    unittest.main()

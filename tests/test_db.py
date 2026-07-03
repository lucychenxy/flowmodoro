import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from flowmo.db import FlowmoStore, format_duration


class FlowmoStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = FlowmoStore(Path(self.temp_dir.name) / "flowmo.sqlite3")

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_add_session_calculates_duration_and_break(self) -> None:
        start = datetime(2026, 7, 3, 9, 0, 0)
        end = start + timedelta(minutes=50)

        session = self.store.add_session("阅读", "Read papers", start, end, coefficient=5)

        self.assertEqual(session.duration_seconds, 3000)
        self.assertEqual(session.break_seconds, 600)

    def test_break_coefficient_must_be_greater_than_three(self) -> None:
        with self.assertRaises(ValueError):
            self.store.set_break_coefficient(3)

    def test_summary_groups_by_month(self) -> None:
        start = datetime(2026, 7, 3, 9, 0, 0)
        self.store.add_session("写作", "Draft", start, start + timedelta(hours=2), coefficient=5)
        self.store.add_session("写作", "Revise", start, start + timedelta(hours=1), coefficient=5)

        rows = self.store.summary("month")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].period, "2026-07")
        self.assertEqual(rows[0].category, "写作")
        self.assertEqual(rows[0].session_count, 2)
        self.assertEqual(rows[0].total_seconds, 10800)


class FormattingTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(3661), "01:01:01")


if __name__ == "__main__":
    unittest.main()


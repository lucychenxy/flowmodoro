import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from flowmo.db import CATEGORIES, FlowmoStore, build_range_bounds, build_time_buckets, format_duration


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
        self.assertFalse(session.category_edit_used)
        self.assertFalse(session.end_time_edit_used)

    def test_session_category_can_be_edited_once(self) -> None:
        start = datetime(2026, 7, 3, 9, 0, 0)
        session = self.store.add_session(
            "阅读", "Misclassified work", start, start + timedelta(minutes=30), coefficient=5
        )

        updated = self.store.update_session_category_once(session.id, "写作")

        self.assertEqual(updated.category, "写作")
        self.assertTrue(updated.category_edit_used)
        with self.assertRaises(ValueError):
            self.store.update_session_category_once(session.id, "实验")

    def test_session_category_edit_requires_different_category(self) -> None:
        start = datetime(2026, 7, 3, 9, 0, 0)
        session = self.store.add_session(
            "阅读", "Same category", start, start + timedelta(minutes=30), coefficient=5
        )

        with self.assertRaises(ValueError):
            self.store.update_session_category_once(session.id, "阅读")

    def test_session_end_time_can_be_edited_once(self) -> None:
        start = datetime(2026, 7, 3, 9, 0, 0)
        session = self.store.add_session(
            "阅读", "Forgot to stop", start, start + timedelta(hours=2), coefficient=5
        )

        updated = self.store.update_session_end_time_once(
            session.id,
            start + timedelta(minutes=45),
        )

        self.assertEqual(updated.end_time, start + timedelta(minutes=45))
        self.assertEqual(updated.duration_seconds, 2700)
        self.assertEqual(updated.break_seconds, 540)
        self.assertTrue(updated.end_time_edit_used)
        with self.assertRaises(ValueError):
            self.store.update_session_end_time_once(session.id, start + timedelta(minutes=30))

    def test_session_end_time_edit_must_be_after_start(self) -> None:
        start = datetime(2026, 7, 3, 9, 0, 0)
        session = self.store.add_session(
            "阅读", "Invalid correction", start, start + timedelta(hours=1), coefficient=5
        )

        with self.assertRaises(ValueError):
            self.store.update_session_end_time_once(session.id, start)

    def test_break_coefficient_must_be_greater_than_three(self) -> None:
        with self.assertRaises(ValueError):
            self.store.set_break_coefficient(3)

    def test_language_setting_defaults_to_english_and_can_be_changed(self) -> None:
        self.assertEqual(self.store.get_language(), "en")

        self.store.set_language("de")

        self.assertEqual(self.store.get_language(), "de")

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

    def test_time_bucket_distribution_splits_sessions_across_hours(self) -> None:
        start = datetime(2026, 7, 3, 9, 30, 0)
        end = datetime(2026, 7, 3, 10, 30, 0)
        self.store.add_session("实验", "Run test", start, end, coefficient=5)

        rows = self.store.time_bucket_distribution("day", reference_date=start.date())

        self.assertEqual(rows[9].totals_by_category["实验"], 1800)
        self.assertEqual(rows[10].totals_by_category["实验"], 1800)

    def test_time_bucket_distribution_accumulates_week_by_hour_of_day(self) -> None:
        friday_start = datetime(2026, 7, 3, 9, 0, 0)
        saturday_start = datetime(2026, 7, 4, 9, 30, 0)
        self.store.add_session(
            "实验", "Friday test", friday_start, friday_start + timedelta(hours=1), coefficient=5
        )
        self.store.add_session(
            "实验",
            "Saturday test",
            saturday_start,
            saturday_start + timedelta(minutes=30),
            coefficient=5,
        )

        rows = self.store.time_bucket_distribution("week", reference_date=friday_start.date())

        self.assertEqual(rows[9].totals_by_category["实验"], 5400)

    def test_category_distribution_uses_selected_range(self) -> None:
        start = datetime(2026, 7, 3, 9, 0, 0)
        self.store.add_session("会议", "Group meeting", start, start + timedelta(hours=1), coefficient=5)

        rows = self.store.category_distribution("week", reference_date=start.date())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].category, "会议")
        self.assertEqual(rows[0].total_seconds, 3600)

    def test_daily_totals_for_week_split_by_day(self) -> None:
        monday = datetime(2026, 7, 6, 9, 0, 0)
        tuesday = datetime(2026, 7, 7, 10, 0, 0)
        self.store.add_session(CATEGORIES[0], "Monday", monday, monday + timedelta(hours=2), coefficient=5)
        self.store.add_session(CATEGORIES[0], "Tuesday", tuesday, tuesday + timedelta(minutes=30), coefficient=5)

        rows = self.store.daily_totals("week", reference_date=monday.date())

        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0].start_date.isoformat(), "2026-07-06")
        self.assertEqual(rows[0].total_seconds, 7200)
        self.assertEqual(rows[1].total_seconds, 1800)

    def test_daily_totals_for_month_split_sessions_across_midnight(self) -> None:
        start = datetime(2026, 7, 1, 23, 30, 0)
        self.store.add_session(CATEGORIES[0], "Late work", start, start + timedelta(hours=1), coefficient=5)

        rows = self.store.daily_totals("month", reference_date=start.date())

        self.assertEqual(rows[0].total_seconds, 1800)
        self.assertEqual(rows[1].total_seconds, 1800)

    def test_monthly_totals_split_sessions_across_months(self) -> None:
        start = datetime(2026, 1, 31, 23, 0, 0)
        self.store.add_session(CATEGORIES[0], "Month boundary", start, start + timedelta(hours=2), coefficient=5)

        rows = self.store.monthly_totals(reference_date=start.date())

        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0].total_seconds, 3600)
        self.assertEqual(rows[1].total_seconds, 3600)


class FormattingTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_build_time_buckets_for_week_starts_on_monday(self) -> None:
        buckets = build_time_buckets("week", reference_date=datetime(2026, 7, 3).date())

        self.assertEqual(buckets[0].label, "00:00")
        self.assertEqual(buckets[0].start_time.date().isoformat(), "2026-06-29")
        self.assertEqual(buckets[-1].label, "23:00")

    def test_build_range_bounds_for_week_starts_on_monday(self) -> None:
        start, end = build_range_bounds("week", reference_date=datetime(2026, 7, 3).date())

        self.assertEqual(start.date().isoformat(), "2026-06-29")
        self.assertEqual(end.date().isoformat(), "2026-07-06")


if __name__ == "__main__":
    unittest.main()

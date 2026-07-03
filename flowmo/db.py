from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path


DEFAULT_DB_PATH = Path("data") / "flowmo.sqlite3"
DEFAULT_BREAK_COEFFICIENT = 5.0
MIN_BREAK_COEFFICIENT = 3.0

CATEGORIES = (
    "阅读",
    "实验",
    "写作",
    "教学",
    "会议",
    "后勤",
)


@dataclass(frozen=True)
class WorkSession:
    id: int
    category: str
    task: str
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    break_seconds: int


@dataclass(frozen=True)
class SummaryRow:
    period: str
    category: str
    session_count: int
    total_seconds: int


@dataclass(frozen=True)
class TimeBucket:
    label: str
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class TimeBucketRow:
    label: str
    totals_by_category: dict[str, int]

    @property
    def total_seconds(self) -> int:
        return sum(self.totals_by_category.values())


@dataclass(frozen=True)
class CategoryTotal:
    category: str
    total_seconds: int


def utc_now_without_microseconds() -> datetime:
    return datetime.now().replace(microsecond=0)


class FlowmoStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.initialize()

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    task TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    break_seconds INTEGER NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                INSERT OR IGNORE INTO settings (key, value)
                VALUES ('break_coefficient', ?)
                """,
                (str(DEFAULT_BREAK_COEFFICIENT),),
            )

    def get_break_coefficient(self) -> float:
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key = 'break_coefficient'"
        ).fetchone()
        if row is None:
            return DEFAULT_BREAK_COEFFICIENT
        return float(row["value"])

    def set_break_coefficient(self, coefficient: float) -> None:
        if coefficient <= MIN_BREAK_COEFFICIENT:
            raise ValueError("休息系数必须大于 3。")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('break_coefficient', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(coefficient),),
            )

    def add_session(
        self,
        category: str,
        task: str,
        start_time: datetime,
        end_time: datetime,
        coefficient: float | None = None,
    ) -> WorkSession:
        if category not in CATEGORIES:
            raise ValueError(f"未知工作类别: {category}")
        if end_time <= start_time:
            raise ValueError("结束时间必须晚于开始时间。")

        coefficient = self.get_break_coefficient() if coefficient is None else coefficient
        if coefficient <= MIN_BREAK_COEFFICIENT:
            raise ValueError("休息系数必须大于 3。")

        duration_seconds = int((end_time - start_time).total_seconds())
        break_seconds = int(duration_seconds / coefficient)
        task = task.strip()

        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO sessions (
                    category, task, start_time, end_time, duration_seconds, break_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    task,
                    start_time.isoformat(timespec="seconds"),
                    end_time.isoformat(timespec="seconds"),
                    duration_seconds,
                    break_seconds,
                ),
            )

        return WorkSession(
            id=int(cursor.lastrowid),
            category=category,
            task=task,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_seconds,
            break_seconds=break_seconds,
        )

    def recent_sessions(self, limit: int = 20) -> list[WorkSession]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM sessions
            ORDER BY start_time DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def sessions_between(self, start_time: datetime, end_time: datetime) -> list[WorkSession]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM sessions
            WHERE end_time > ? AND start_time < ?
            ORDER BY start_time
            """,
            (
                start_time.isoformat(timespec="seconds"),
                end_time.isoformat(timespec="seconds"),
            ),
        ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def summary(self, period: str) -> list[SummaryRow]:
        period_expression = {
            "week": "strftime('%Y-W%W', start_time)",
            "month": "strftime('%Y-%m', start_time)",
            "year": "strftime('%Y', start_time)",
        }.get(period)
        if period_expression is None:
            raise ValueError("period must be one of: week, month, year")

        rows = self.connection.execute(
            f"""
            SELECT
                {period_expression} AS period,
                category,
                COUNT(*) AS session_count,
                SUM(duration_seconds) AS total_seconds
            FROM sessions
            GROUP BY period, category
            ORDER BY period DESC, total_seconds DESC
            """
        ).fetchall()
        return [
            SummaryRow(
                period=row["period"],
                category=row["category"],
                session_count=int(row["session_count"]),
                total_seconds=int(row["total_seconds"] or 0),
            )
            for row in rows
        ]

    def time_bucket_distribution(
        self, range_name: str, reference_date: date | None = None
    ) -> list[TimeBucketRow]:
        buckets = build_time_buckets(range_name, reference_date)
        if not buckets:
            return []

        sessions = self.sessions_between(buckets[0].start_time, buckets[-1].end_time)
        rows: list[TimeBucketRow] = []
        for bucket in buckets:
            totals = {category: 0 for category in CATEGORIES}
            for session in sessions:
                overlap_start = max(session.start_time, bucket.start_time)
                overlap_end = min(session.end_time, bucket.end_time)
                if overlap_end <= overlap_start:
                    continue
                totals[session.category] += int((overlap_end - overlap_start).total_seconds())
            rows.append(TimeBucketRow(label=bucket.label, totals_by_category=totals))
        return rows

    def category_distribution(
        self, range_name: str, reference_date: date | None = None
    ) -> list[CategoryTotal]:
        buckets = build_time_buckets(range_name, reference_date)
        if not buckets:
            return []

        totals = {category: 0 for category in CATEGORIES}
        sessions = self.sessions_between(buckets[0].start_time, buckets[-1].end_time)
        for bucket in buckets:
            for session in sessions:
                overlap_start = max(session.start_time, bucket.start_time)
                overlap_end = min(session.end_time, bucket.end_time)
                if overlap_end <= overlap_start:
                    continue
                totals[session.category] += int((overlap_end - overlap_start).total_seconds())

        return [
            CategoryTotal(category=category, total_seconds=seconds)
            for category, seconds in totals.items()
            if seconds > 0
        ]

    def _row_to_session(self, row: sqlite3.Row) -> WorkSession:
        return WorkSession(
            id=int(row["id"]),
            category=row["category"],
            task=row["task"],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]),
            duration_seconds=int(row["duration_seconds"]),
            break_seconds=int(row["break_seconds"]),
        )


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    delta = timedelta(seconds=seconds)
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_time_buckets(range_name: str, reference_date: date | None = None) -> list[TimeBucket]:
    reference_date = reference_date or date.today()

    if range_name == "day":
        day_start = datetime.combine(reference_date, time.min)
        return [
            TimeBucket(
                label=f"{hour:02d}:00",
                start_time=day_start + timedelta(hours=hour),
                end_time=day_start + timedelta(hours=hour + 1),
            )
            for hour in range(24)
        ]

    if range_name == "week":
        week_start_date = reference_date - timedelta(days=reference_date.weekday())
        week_start = datetime.combine(week_start_date, time.min)
        labels = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        return [
            TimeBucket(
                label=labels[index],
                start_time=week_start + timedelta(days=index),
                end_time=week_start + timedelta(days=index + 1),
            )
            for index in range(7)
        ]

    if range_name == "month":
        month_start = datetime(reference_date.year, reference_date.month, 1)
        if reference_date.month == 12:
            next_month = datetime(reference_date.year + 1, 1, 1)
        else:
            next_month = datetime(reference_date.year, reference_date.month + 1, 1)

        buckets = []
        cursor = month_start
        while cursor < next_month:
            next_day = cursor + timedelta(days=1)
            buckets.append(TimeBucket(label=str(cursor.day), start_time=cursor, end_time=next_day))
            cursor = next_day
        return buckets

    if range_name == "year":
        return [
            TimeBucket(
                label=f"{month}月",
                start_time=datetime(reference_date.year, month, 1),
                end_time=(
                    datetime(reference_date.year + 1, 1, 1)
                    if month == 12
                    else datetime(reference_date.year, month + 1, 1)
                ),
            )
            for month in range(1, 13)
        ]

    raise ValueError("range_name must be one of: day, week, month, year")

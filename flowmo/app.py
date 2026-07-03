from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from flowmo.db import CATEGORIES, FlowmoStore, format_duration, utc_now_without_microseconds


class FlowmoApp(tk.Tk):
    def __init__(self, store: FlowmoStore | None = None) -> None:
        super().__init__()
        self.title("Flowmo")
        self.geometry("900x620")
        self.minsize(760, 520)

        self.store = store or FlowmoStore()
        self.current_start: datetime | None = None
        self.break_remaining_seconds = 0
        self.break_timer_job: str | None = None

        self.category_var = tk.StringVar(value=CATEGORIES[0])
        self.timer_var = tk.StringVar(value="00:00:00")
        self.status_var = tk.StringVar(value="准备开始")
        self.coefficient_var = tk.StringVar(value=f"{self.store.get_break_coefficient():.1f}")
        self.summary_period_var = tk.StringVar(value="week")
        self.break_var = tk.StringVar(value="休息时间会在结束 session 后计算")

        self._build_ui()
        self._refresh_history()
        self._refresh_summary()
        self._tick()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=16)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="类别").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            top,
            textvariable=self.category_var,
            values=CATEGORIES,
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=(8, 24))

        ttk.Label(top, text="休息系数").grid(row=0, column=2, sticky="e")
        coefficient = ttk.Spinbox(
            top,
            from_=3.1,
            to=20.0,
            increment=0.1,
            textvariable=self.coefficient_var,
            width=8,
            command=self._save_coefficient,
        )
        coefficient.grid(row=0, column=3, sticky="w", padx=(8, 0))
        coefficient.bind("<FocusOut>", lambda _event: self._save_coefficient())

        ttk.Label(top, text="具体任务").grid(row=1, column=0, sticky="nw", pady=(12, 0))
        self.task_text = tk.Text(top, height=3, wrap="word")
        self.task_text.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(12, 0))

        timer_frame = ttk.Frame(self, padding=(16, 0, 16, 16))
        timer_frame.grid(row=1, column=0, sticky="ew")
        timer_frame.columnconfigure(0, weight=1)

        ttk.Label(timer_frame, textvariable=self.timer_var, font=("Segoe UI", 36, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(timer_frame, textvariable=self.status_var).grid(row=1, column=0, sticky="w")
        ttk.Label(timer_frame, textvariable=self.break_var).grid(row=2, column=0, sticky="w")

        self.start_button = ttk.Button(timer_frame, text="开始", command=self._start_session)
        self.start_button.grid(row=0, column=1, padx=(16, 8), sticky="e")
        self.stop_button = ttk.Button(
            timer_frame, text="结束", command=self._stop_session, state="disabled"
        )
        self.stop_button.grid(row=0, column=2, sticky="e")

        notebook = ttk.Notebook(self)
        notebook.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))

        history_frame = ttk.Frame(notebook, padding=8)
        summary_frame = ttk.Frame(notebook, padding=8)
        notebook.add(history_frame, text="最近记录")
        notebook.add(summary_frame, text="统计")

        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)
        self.history = ttk.Treeview(
            history_frame,
            columns=("category", "task", "start", "end", "duration", "break"),
            show="headings",
            height=12,
        )
        for column, label, width in (
            ("category", "类别", 80),
            ("task", "任务", 240),
            ("start", "开始", 150),
            ("end", "结束", 150),
            ("duration", "工作时长", 90),
            ("break", "建议休息", 90),
        ):
            self.history.heading(column, text=label)
            self.history.column(column, width=width, anchor="w")
        self.history.grid(row=0, column=0, sticky="nsew")

        history_scroll = ttk.Scrollbar(history_frame, orient="vertical", command=self.history.yview)
        history_scroll.grid(row=0, column=1, sticky="ns")
        self.history.configure(yscrollcommand=history_scroll.set)

        controls = ttk.Frame(summary_frame)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Radiobutton(
            controls,
            text="每周",
            variable=self.summary_period_var,
            value="week",
            command=self._refresh_summary,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            controls,
            text="每月",
            variable=self.summary_period_var,
            value="month",
            command=self._refresh_summary,
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Radiobutton(
            controls,
            text="每年",
            variable=self.summary_period_var,
            value="year",
            command=self._refresh_summary,
        ).grid(row=0, column=2, sticky="w", padx=(12, 0))

        summary_frame.rowconfigure(1, weight=1)
        summary_frame.columnconfigure(0, weight=1)
        self.summary = ttk.Treeview(
            summary_frame,
            columns=("period", "category", "sessions", "duration"),
            show="headings",
            height=12,
        )
        for column, label, width in (
            ("period", "周期", 120),
            ("category", "类别", 100),
            ("sessions", "次数", 80),
            ("duration", "总时长", 120),
        ):
            self.summary.heading(column, text=label)
            self.summary.column(column, width=width, anchor="w")
        self.summary.grid(row=1, column=0, sticky="nsew")

    def _start_session(self) -> None:
        self._save_coefficient()
        self.current_start = utc_now_without_microseconds()
        self.timer_var.set("00:00:00")
        self.status_var.set(f"开始于 {self.current_start.strftime('%Y-%m-%d %H:%M:%S')}")
        self.break_var.set("当前正在工作")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        if self.break_timer_job is not None:
            self.after_cancel(self.break_timer_job)
            self.break_timer_job = None

    def _stop_session(self) -> None:
        if self.current_start is None:
            return

        end_time = utc_now_without_microseconds()
        task = self.task_text.get("1.0", "end").strip()
        coefficient = self._save_coefficient()
        try:
            session = self.store.add_session(
                category=self.category_var.get(),
                task=task,
                start_time=self.current_start,
                end_time=end_time,
                coefficient=coefficient,
            )
        except ValueError as exc:
            messagebox.showerror("无法保存 session", str(exc))
            return

        self.current_start = None
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set("Session 已保存")
        self.break_remaining_seconds = session.break_seconds
        self._refresh_history()
        self._refresh_summary()
        self._run_break_timer()

    def _save_coefficient(self) -> float:
        try:
            coefficient = float(self.coefficient_var.get())
            self.store.set_break_coefficient(coefficient)
            self.coefficient_var.set(f"{coefficient:.1f}")
            return coefficient
        except ValueError as exc:
            messagebox.showerror("休息系数无效", str(exc))
            current = self.store.get_break_coefficient()
            self.coefficient_var.set(f"{current:.1f}")
            return current

    def _tick(self) -> None:
        if self.current_start is not None:
            elapsed = int((utc_now_without_microseconds() - self.current_start).total_seconds())
            self.timer_var.set(format_duration(elapsed))
        self.after(1000, self._tick)

    def _run_break_timer(self) -> None:
        if self.break_remaining_seconds <= 0:
            self.break_var.set("建议休息结束，可以继续开始下一段工作")
            messagebox.showinfo("Flowmo", "休息时间结束，可以继续工作。")
            self.break_timer_job = None
            return

        self.break_var.set(f"建议休息剩余 {format_duration(self.break_remaining_seconds)}")
        self.break_remaining_seconds -= 1
        self.break_timer_job = self.after(1000, self._run_break_timer)

    def _refresh_history(self) -> None:
        self.history.delete(*self.history.get_children())
        for session in self.store.recent_sessions():
            self.history.insert(
                "",
                "end",
                values=(
                    session.category,
                    session.task,
                    session.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    session.end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    format_duration(session.duration_seconds),
                    format_duration(session.break_seconds),
                ),
            )

    def _refresh_summary(self) -> None:
        self.summary.delete(*self.summary.get_children())
        for row in self.store.summary(self.summary_period_var.get()):
            self.summary.insert(
                "",
                "end",
                values=(
                    row.period,
                    row.category,
                    row.session_count,
                    format_duration(row.total_seconds),
                ),
            )

    def _on_close(self) -> None:
        if self.current_start is not None:
            should_close = messagebox.askyesno(
                "正在计时",
                "当前 session 还没有结束。关闭窗口会丢弃这段未保存计时，是否继续？",
            )
            if not should_close:
                return
        self.store.close()
        self.destroy()


def main() -> None:
    app = FlowmoApp()
    app.mainloop()


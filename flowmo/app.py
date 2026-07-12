from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

from flowmo.db import (
    CATEGORIES,
    FlowmoStore,
    build_range_bounds,
    format_duration,
    utc_now_without_microseconds,
)
from flowmo.i18n import (
    LANGUAGES,
    WEEKDAYS,
    category_from_label,
    category_label,
    normalize_language,
    text,
)


CATEGORY_COLORS = {
    "阅读": "#4E79A7",
    "实验": "#F28E2B",
    "写作": "#59A14F",
    "教学": "#E15759",
    "会议": "#B07AA1",
    "后勤": "#76B7B2",
}

RANGE_LABEL_KEYS = {
    "day": "today",
    "week": "this_week",
    "month": "this_month",
    "year": "this_year",
}

HISTORY_RANGE_LABEL_KEYS = {
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}


class FlowmoApp(tk.Tk):
    def __init__(self, store: FlowmoStore | None = None) -> None:
        super().__init__()
        self.title("Flowmo")
        self.geometry("1100x720")
        self.minsize(900, 620)

        self.store = store or FlowmoStore()
        self.current_start: datetime | None = None
        self.current_category: str | None = None
        self.break_remaining_seconds = 0
        self.break_timer_job: str | None = None
        self.category_cell_editor: ttk.Combobox | None = None
        self.end_time_cell_editor: ttk.Entry | None = None
        self.language = normalize_language(self.store.get_language())

        self.category_var = tk.StringVar(value="")
        self.timer_var = tk.StringVar(value="00:00:00")
        self.status_var = tk.StringVar(value=self.t("ready"))
        self.coefficient_var = tk.StringVar(value=f"{self.store.get_break_coefficient():.1f}")
        self.visual_range_var = tk.StringVar(value="week")
        self.history_range_var = tk.StringVar(value="day")
        self.calendar_date_var = tk.StringVar(value=date.today().isoformat())
        self.language_var = tk.StringVar(value=LANGUAGES[self.language])
        self.break_var = tk.StringVar(value=self.t("status_hint"))

        self._build_ui()
        self._refresh_log()
        self._refresh_visualization()
        self._refresh_calendar()
        self._tick()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def t(self, key: str, **kwargs) -> str:
        return text(self.language, key, **kwargs)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=16)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text=self.t("category")).grid(row=0, column=0, sticky="w")
        category_frame = ttk.Frame(top)
        category_frame.grid(row=0, column=1, sticky="w", padx=(8, 24))
        for index, category in enumerate(CATEGORIES):
            ttk.Radiobutton(
                category_frame,
                text=category_label(self.language, category),
                variable=self.category_var,
                value=category_label(self.language, category),
            ).grid(row=0, column=index, sticky="w", padx=(0 if index == 0 else 8, 0))

        ttk.Label(top, text=self.t("break_coefficient")).grid(row=0, column=2, sticky="e")
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

        ttk.Label(top, text=self.t("language")).grid(row=0, column=4, sticky="e", padx=(24, 0))
        language_combo = ttk.Combobox(
            top,
            textvariable=self.language_var,
            values=list(LANGUAGES.values()),
            state="readonly",
            width=12,
        )
        language_combo.grid(row=0, column=5, sticky="w", padx=(8, 0))
        language_combo.bind("<<ComboboxSelected>>", lambda _event: self._change_language())

        ttk.Label(top, text=self.t("task")).grid(row=1, column=0, sticky="nw", pady=(12, 0))
        self.task_text = tk.Text(top, height=3, wrap="word")
        self.task_text.grid(row=1, column=1, columnspan=5, sticky="ew", padx=(8, 0), pady=(12, 0))

        timer_frame = ttk.Frame(self, padding=(16, 0, 16, 16))
        timer_frame.grid(row=1, column=0, sticky="ew")
        timer_frame.columnconfigure(0, weight=1)

        ttk.Label(timer_frame, textvariable=self.timer_var, font=("Segoe UI", 36, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(timer_frame, textvariable=self.status_var).grid(row=1, column=0, sticky="w")
        ttk.Label(timer_frame, textvariable=self.break_var).grid(row=2, column=0, sticky="w")

        self.start_button = ttk.Button(timer_frame, text=self.t("start"), command=self._start_session)
        self.start_button.grid(row=0, column=1, padx=(16, 8), sticky="e")
        self.stop_button = ttk.Button(
            timer_frame, text=self.t("stop"), command=self._stop_session, state="disabled"
        )
        self.stop_button.grid(row=0, column=2, sticky="e")

        notebook = ttk.Notebook(self)
        notebook.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))

        visualization_frame = ttk.Frame(notebook, padding=8)
        calendar_frame = ttk.Frame(notebook, padding=8)
        log_frame = ttk.Frame(notebook, padding=8)
        notebook.add(visualization_frame, text=self.t("recent"))
        notebook.add(calendar_frame, text=self.t("history"))
        notebook.add(log_frame, text=self.t("log"))

        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.history = ttk.Treeview(
            log_frame,
            columns=(
                "category",
                "task",
                "start",
                "end",
                "duration",
                "break",
                "category_edited",
                "end_edited",
            ),
            show="headings",
            height=12,
        )
        for column, label, width in (
            ("category", self.t("editable_category_column"), 150),
            ("task", self.t("task_column"), 240),
            ("start", self.t("start_column"), 150),
            ("end", self.t("editable_end_column"), 150),
            ("duration", self.t("duration_column"), 100),
            ("break", self.t("break_column"), 120),
            ("category_edited", self.t("category_edited_column"), 120),
            ("end_edited", self.t("end_time_edited_column"), 120),
        ):
            self.history.heading(column, text=label)
            self.history.column(column, width=width, anchor="w")
        self.history.grid(row=0, column=0, sticky="nsew")

        history_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self._scroll_history)
        history_scroll.grid(row=0, column=1, sticky="ns")
        self.history.configure(yscrollcommand=history_scroll.set)
        self.history.bind("<<TreeviewSelect>>", self._show_selected_log_editors)
        self.history.bind("<Configure>", lambda _event: self._close_log_cell_editors())
        self.history.bind("<MouseWheel>", lambda _event: self._close_log_cell_editors())

        self._build_visualization_tab(visualization_frame)
        self._build_calendar_tab(calendar_frame)

    def _build_visualization_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.columnconfigure(2, weight=2)

        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        for index, (range_name, label_key) in enumerate(RANGE_LABEL_KEYS.items()):
            ttk.Radiobutton(
                controls,
                text=self.t(label_key),
                variable=self.visual_range_var,
                value=range_name,
                command=self._refresh_visualization,
            ).grid(row=0, column=index, sticky="w", padx=(0 if index == 0 else 12, 0))

        self.bar_canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1)
        self.bar_canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.period_canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1)
        self.period_canvas.grid(row=1, column=1, sticky="nsew", padx=(0, 8))
        self.pie_canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1)
        self.pie_canvas.grid(row=1, column=2, sticky="nsew")

        legend = ttk.Frame(parent)
        legend.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for index, category in enumerate(CATEGORIES):
            swatch = tk.Canvas(legend, width=14, height=14, highlightthickness=0)
            swatch.create_rectangle(1, 1, 13, 13, fill=CATEGORY_COLORS[category], outline="")
            swatch.grid(row=0, column=index * 2, sticky="w", padx=(0 if index == 0 else 12, 4))
            ttk.Label(legend, text=category_label(self.language, category)).grid(
                row=0, column=index * 2 + 1, sticky="w"
            )

        self.bar_canvas.bind("<Configure>", lambda _event: self._draw_visualization())
        self.period_canvas.bind("<Configure>", lambda _event: self._draw_visualization())
        self.pie_canvas.bind("<Configure>", lambda _event: self._draw_visualization())

    def _build_calendar_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.columnconfigure(2, weight=2)

        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        for index, (range_name, label_key) in enumerate(HISTORY_RANGE_LABEL_KEYS.items()):
            ttk.Radiobutton(
                controls,
                text=self.t(label_key),
                variable=self.history_range_var,
                value=range_name,
                command=self._refresh_calendar,
            ).grid(row=0, column=index, sticky="w", padx=(0 if index == 0 else 12, 0))

        ttk.Label(controls, text=self.t("reference_date")).grid(row=0, column=4, sticky="w", padx=(24, 0))
        date_entry = ttk.Entry(
            controls,
            textvariable=self.calendar_date_var,
            width=14,
            state="readonly",
        )
        date_entry.grid(row=0, column=5, sticky="w", padx=(8, 4))
        ttk.Button(controls, text="📅", width=3, command=self._open_date_picker).grid(
            row=0, column=6, sticky="w"
        )

        self.calendar_bar_canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1)
        self.calendar_bar_canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.calendar_period_canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1)
        self.calendar_period_canvas.grid(row=1, column=1, sticky="nsew", padx=(0, 8))
        self.calendar_pie_canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1)
        self.calendar_pie_canvas.grid(row=1, column=2, sticky="nsew")

        legend = ttk.Frame(parent)
        legend.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for index, category in enumerate(CATEGORIES):
            swatch = tk.Canvas(legend, width=14, height=14, highlightthickness=0)
            swatch.create_rectangle(1, 1, 13, 13, fill=CATEGORY_COLORS[category], outline="")
            swatch.grid(row=0, column=index * 2, sticky="w", padx=(0 if index == 0 else 12, 4))
            ttk.Label(legend, text=category_label(self.language, category)).grid(
                row=0, column=index * 2 + 1, sticky="w"
            )

        self.calendar_bar_canvas.bind("<Configure>", lambda _event: self._draw_calendar())
        self.calendar_period_canvas.bind("<Configure>", lambda _event: self._draw_calendar())
        self.calendar_pie_canvas.bind("<Configure>", lambda _event: self._draw_calendar())

    def _open_date_picker(self) -> None:
        try:
            selected_date = date.fromisoformat(self.calendar_date_var.get())
        except ValueError:
            selected_date = date.today()

        picker = tk.Toplevel(self)
        picker.title(self.t("date_picker_title"))
        picker.resizable(False, False)
        picker.transient(self)
        picker.grab_set()
        self._render_date_picker(picker, selected_date.year, selected_date.month)

    def _render_date_picker(self, picker: tk.Toplevel, year: int, month: int) -> None:
        for child in picker.winfo_children():
            child.destroy()

        header = ttk.Frame(picker, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            header,
            text="<",
            width=3,
            command=lambda: self._render_date_picker(
                picker, year - 1 if month == 1 else year, 12 if month == 1 else month - 1
            ),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"{year}-{month:02d}", width=12, anchor="center").grid(
            row=0, column=1, padx=8
        )
        ttk.Button(
            header,
            text=">",
            width=3,
            command=lambda: self._render_date_picker(
                picker, year + 1 if month == 12 else year, 1 if month == 12 else month + 1
            ),
        ).grid(row=0, column=2, sticky="e")

        body = ttk.Frame(picker, padding=(8, 4, 8, 8))
        body.grid(row=1, column=0, sticky="nsew")
        for index, weekday in enumerate(WEEKDAYS[self.language]):
            ttk.Label(body, text=weekday, width=4, anchor="center").grid(row=0, column=index)

        month_days = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
        for row_index, week in enumerate(month_days, start=1):
            for column_index, day in enumerate(week):
                if day.month != month:
                    ttk.Label(body, text="", width=4).grid(row=row_index, column=column_index)
                    continue
                ttk.Button(
                    body,
                    text=str(day.day),
                    width=4,
                    command=lambda selected=day: self._select_calendar_date(picker, selected),
                ).grid(row=row_index, column=column_index, padx=1, pady=1)

    def _select_calendar_date(self, picker: tk.Toplevel, selected_date: date) -> None:
        self.calendar_date_var.set(selected_date.isoformat())
        picker.destroy()
        self._refresh_calendar()

    def _change_language(self) -> None:
        selected_language = next(
            (code for code, label in LANGUAGES.items() if label == self.language_var.get()),
            "en",
        )
        if selected_language == self.language:
            return

        selected_category = category_from_label(self.language, self.category_var.get())
        task_text = self.task_text.get("1.0", "end").strip() if hasattr(self, "task_text") else ""
        self.language = selected_language
        self.store.set_language(selected_language)
        self.category_var.set(
            category_label(self.language, selected_category) if selected_category else ""
        )
        self.language_var.set(LANGUAGES[self.language])
        self._sync_status_language()

        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        if self.current_start is not None:
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        if task_text:
            self.task_text.insert("1.0", task_text)
        self._refresh_log()
        self._refresh_visualization()
        self._refresh_calendar()

    def _sync_status_language(self) -> None:
        if self.current_start is not None:
            self.status_var.set(
                self.t("started_at", time=self.current_start.strftime("%Y-%m-%d %H:%M:%S"))
            )
            self.break_var.set(self.t("working"))
            return
        if self.break_timer_job is not None:
            self.status_var.set(self.t("resting"))
            self.break_var.set(self.t("break_active"))
            return
        self.status_var.set(self.t("ready"))
        self.break_var.set(self.t("status_hint"))

    def _start_session(self) -> None:
        selected_category = category_from_label(self.language, self.category_var.get())
        if selected_category not in CATEGORIES:
            messagebox.showwarning(self.t("choose_category"), self.t("choose_category_message"))
            return

        self._save_coefficient()
        self.current_start = utc_now_without_microseconds()
        self.current_category = selected_category
        self.break_remaining_seconds = 0
        self.timer_var.set("00:00:00")
        self.status_var.set(
            self.t("started_at", time=self.current_start.strftime("%Y-%m-%d %H:%M:%S"))
        )
        self.break_var.set(self.t("working"))
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
                category=self.current_category or category_from_label(self.language, self.category_var.get()),
                task=task,
                start_time=self.current_start,
                end_time=end_time,
                coefficient=coefficient,
            )
        except ValueError as exc:
            messagebox.showerror(self.t("save_error_title"), str(exc))
            return

        self.current_start = None
        self.current_category = None
        self.category_var.set("")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set(self.t("resting"))
        self.break_remaining_seconds = session.break_seconds
        self._refresh_log()
        self._refresh_visualization()
        self._refresh_calendar()
        self._run_break_timer()

    def _save_coefficient(self) -> float:
        try:
            coefficient = float(self.coefficient_var.get())
            self.store.set_break_coefficient(coefficient)
            self.coefficient_var.set(f"{coefficient:.1f}")
            return coefficient
        except ValueError as exc:
            messagebox.showerror(self.t("coefficient_error_title"), str(exc))
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
            self.timer_var.set("00:00:00")
            self.status_var.set(self.t("break_done_status"))
            self.break_var.set(self.t("break_done_hint"))
            messagebox.showinfo("Flowmo", self.t("break_done_dialog"))
            self.break_timer_job = None
            return

        self.timer_var.set(format_duration(self.break_remaining_seconds))
        self.break_var.set(self.t("break_active"))
        self.break_remaining_seconds -= 1
        self.break_timer_job = self.after(1000, self._run_break_timer)

    def _refresh_log(self) -> None:
        self._close_log_cell_editors()
        self.history.delete(*self.history.get_children())
        for session in self.store.recent_sessions():
            self.history.insert(
                "",
                "end",
                iid=str(session.id),
                values=(
                    category_label(self.language, session.category),
                    session.task,
                    session.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    session.end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    format_duration(session.duration_seconds),
                    format_duration(session.break_seconds),
                    self.t("yes") if session.category_edit_used else self.t("no"),
                    self.t("yes") if session.end_time_edit_used else self.t("no"),
                ),
            )

    def _scroll_history(self, *args) -> None:
        self._close_log_cell_editors()
        self.history.yview(*args)

    def _close_log_cell_editors(self) -> None:
        self._close_category_cell_editor()
        self._close_end_time_cell_editor()

    def _close_category_cell_editor(self) -> None:
        if self.category_cell_editor is not None and self.category_cell_editor.winfo_exists():
            self.category_cell_editor.destroy()
        self.category_cell_editor = None

    def _close_end_time_cell_editor(self) -> None:
        if self.end_time_cell_editor is not None and self.end_time_cell_editor.winfo_exists():
            self.end_time_cell_editor.destroy()
        self.end_time_cell_editor = None

    def _show_selected_log_editors(self, _event: tk.Event | None = None) -> None:
        self._close_log_cell_editors()
        selected = self.history.selection()
        if not selected:
            return

        row_id = selected[0]
        session_id = int(row_id)
        session = next(
            (item for item in self.store.recent_sessions() if item.id == session_id),
            None,
        )
        if session is None:
            return
        self._show_category_cell_editor(row_id, session)
        self._show_end_time_cell_editor(row_id, session)

    def _show_category_cell_editor(self, row_id: str, session) -> None:
        if session.category_edit_used:
            return
        cell_box = self.history.bbox(row_id, "#1")
        if not cell_box:
            return
        x, y, width, height = cell_box
        current_label = category_label(self.language, session.category)
        category_values = [
            category_label(self.language, category)
            for category in CATEGORIES
            if category != session.category
        ]

        editor_var = tk.StringVar(value=current_label)
        editor = ttk.Combobox(
            self.history,
            textvariable=editor_var,
            values=category_values,
            state="readonly",
        )
        editor.place(x=x, y=y, width=width, height=height)
        self.category_cell_editor = editor

        def on_select(_event: tk.Event) -> None:
            selected_label = editor_var.get()
            self._close_category_cell_editor()
            self._confirm_category_edit(session.id, session.category, selected_label)

        editor.bind("<<ComboboxSelected>>", on_select)
        editor.bind("<Escape>", lambda _event: self._close_category_cell_editor())

    def _show_end_time_cell_editor(self, row_id: str, session) -> None:
        if session.end_time_edit_used:
            return
        cell_box = self.history.bbox(row_id, "#4")
        if not cell_box:
            return
        x, y, width, height = cell_box
        end_time_text = session.end_time.strftime("%Y-%m-%d %H:%M:%S")
        editor_var = tk.StringVar(value=end_time_text)
        editor = ttk.Entry(self.history, textvariable=editor_var)
        editor.place(x=x, y=y, width=width, height=height)
        self.end_time_cell_editor = editor

        def on_return(_event: tk.Event) -> str:
            selected_text = editor_var.get().strip()
            self._close_end_time_cell_editor()
            self._confirm_end_time_edit(session.id, session.end_time, selected_text)
            return "break"

        editor.bind("<Return>", on_return)
        editor.bind("<Escape>", lambda _event: self._close_end_time_cell_editor())

    def _confirm_end_time_edit(
        self, session_id: int, old_end_time: datetime, end_time_text: str
    ) -> None:
        try:
            new_end_time = datetime.strptime(end_time_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            messagebox.showerror(self.t("end_time_edit_error"), self.t("invalid_end_time_format"))
            return
        if new_end_time == old_end_time:
            return

        old_text = old_end_time.strftime("%Y-%m-%d %H:%M:%S")
        new_text = new_end_time.strftime("%Y-%m-%d %H:%M:%S")
        confirmed = messagebox.askyesno(
            self.t("edit_end_time_title"),
            self.t("confirm_end_time_edit", old=old_text, new=new_text),
        )
        if not confirmed:
            return

        try:
            self.store.update_session_end_time_once(session_id, new_end_time)
        except ValueError as exc:
            messagebox.showerror(self.t("end_time_edit_error"), str(exc))
            return

        self._refresh_log()
        self._refresh_visualization()
        self._refresh_calendar()
        messagebox.showinfo(self.t("edit_end_time_title"), self.t("end_time_edit_success"))

    def _confirm_category_edit(
        self, session_id: int, old_category: str, category_label_value: str
    ) -> None:
        new_category = category_from_label(self.language, category_label_value)
        if new_category not in CATEGORIES:
            messagebox.showwarning(self.t("choose_category"), self.t("choose_category_message"))
            return
        if new_category == old_category:
            return

        old_label = category_label(self.language, old_category)
        new_label = category_label(self.language, new_category)
        confirmed = messagebox.askyesno(
            self.t("edit_category_title"),
            self.t("confirm_category_edit", old=old_label, new=new_label),
        )
        if not confirmed:
            return

        try:
            self.store.update_session_category_once(session_id, new_category)
        except ValueError as exc:
            messagebox.showerror(self.t("category_edit_error"), str(exc))
            return

        self._refresh_log()
        self._refresh_visualization()
        self._refresh_calendar()
        messagebox.showinfo(self.t("edit_category_title"), self.t("category_edit_success"))

    def _refresh_visualization(self) -> None:
        self._draw_visualization()

    def _refresh_calendar(self) -> None:
        self._draw_calendar()

    def _draw_visualization(self) -> None:
        if not hasattr(self, "bar_canvas") or not hasattr(self, "period_canvas") or not hasattr(self, "pie_canvas"):
            return

        range_name = self.visual_range_var.get()
        self._sync_chart_layout(self.period_canvas, self.pie_canvas, range_name)
        self._draw_charts(
            self.bar_canvas,
            self.period_canvas,
            self.pie_canvas,
            range_name,
            None,
            self.t(RANGE_LABEL_KEYS[range_name]),
        )

    def _draw_calendar(self) -> None:
        if not hasattr(self, "calendar_bar_canvas") or not hasattr(self, "calendar_period_canvas") or not hasattr(self, "calendar_pie_canvas"):
            return

        selected_date = date.fromisoformat(self.calendar_date_var.get().strip())
        range_name = self.history_range_var.get()
        self._sync_chart_layout(self.calendar_period_canvas, self.calendar_pie_canvas, range_name)

        self._draw_charts(
            self.calendar_bar_canvas,
            self.calendar_period_canvas,
            self.calendar_pie_canvas,
            range_name,
            selected_date,
            self._history_title(range_name, selected_date),
        )

    def _sync_chart_layout(
        self, period_canvas: tk.Canvas, pie_canvas: tk.Canvas, range_name: str
    ) -> None:
        chart_parent = period_canvas.master
        if range_name == "day":
            chart_parent.columnconfigure(0, weight=3)
            chart_parent.columnconfigure(1, weight=2)
            chart_parent.columnconfigure(2, weight=0)
            period_canvas.grid_remove()
            pie_canvas.grid_configure(column=1)
            return

        chart_parent.columnconfigure(0, weight=3)
        chart_parent.columnconfigure(1, weight=2)
        chart_parent.columnconfigure(2, weight=2)
        period_canvas.grid(row=1, column=1, sticky="nsew", padx=(0, 8))
        pie_canvas.grid_configure(column=2)

    def _draw_charts(
        self,
        bar_canvas: tk.Canvas,
        period_canvas: tk.Canvas,
        pie_canvas: tk.Canvas,
        range_name: str,
        reference_date: date | None,
        title_label: str,
    ) -> None:
        bucket_rows = self.store.time_bucket_distribution(range_name, reference_date)
        category_rows = self.store.category_distribution(range_name, reference_date)
        self._draw_stacked_bar_chart(bar_canvas, bucket_rows, title_label)
        if range_name == "day":
            period_canvas.delete("all")
        else:
            self._draw_period_chart(period_canvas, range_name, reference_date, title_label)
        self._draw_pie_chart(pie_canvas, category_rows, title_label)

    def _draw_stacked_bar_chart(self, canvas: tk.Canvas, bucket_rows, title_label: str) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        margin_left = 56
        margin_right = 20
        margin_top = 44
        margin_bottom = 72
        chart_width = max(width - margin_left - margin_right, 1)
        chart_height = max(height - margin_top - margin_bottom, 1)

        canvas.create_text(
            16,
            18,
            anchor="w",
            text=self.t("work_distribution", title=title_label),
            font=("Segoe UI", 12, "bold"),
        )

        max_seconds = max((row.total_seconds for row in bucket_rows), default=0)
        if max_seconds <= 0:
            self._draw_empty_state(canvas, width, height, self.t("no_records"))
            return

        y_axis_bottom = margin_top + chart_height
        canvas.create_line(margin_left, margin_top, margin_left, y_axis_bottom, fill="#777777")
        canvas.create_line(margin_left, y_axis_bottom, width - margin_right, y_axis_bottom, fill="#777777")

        for index in range(5):
            value = max_seconds * index / 4
            y = y_axis_bottom - (value / max_seconds) * chart_height
            canvas.create_line(margin_left - 4, y, width - margin_right, y, fill="#eeeeee")
            canvas.create_text(
                margin_left - 8,
                y,
                anchor="e",
                text=self._format_hours(value),
                font=("Segoe UI", 8),
                fill="#555555",
            )

        bucket_count = len(bucket_rows)
        gap = 4 if bucket_count > 12 else 10
        bar_width = max((chart_width - gap * (bucket_count - 1)) / max(bucket_count, 1), 2)
        label_step = 3

        for index, row in enumerate(bucket_rows):
            x0 = margin_left + index * (bar_width + gap)
            x1 = x0 + bar_width
            y_cursor = y_axis_bottom
            for category in CATEGORIES:
                seconds = row.totals_by_category.get(category, 0)
                if seconds <= 0:
                    continue
                segment_height = seconds / max_seconds * chart_height
                y0 = y_cursor - segment_height
                canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y_cursor,
                    fill=CATEGORY_COLORS[category],
                    outline="#ffffff",
                )
                y_cursor = y0

            if index % label_step == 0 or bucket_count <= 12:
                canvas.create_text(
                    (x0 + x1) / 2,
                    y_axis_bottom + 14,
                    text=row.label,
                    font=("Segoe UI", 8),
                    fill="#444444",
                )

        busiest = max(bucket_rows, key=lambda row: row.total_seconds)
        canvas.create_text(
            margin_left,
            height - 24,
            anchor="w",
            text=self.t(
                "busiest",
                label=busiest.label,
                duration=self._format_hours(busiest.total_seconds),
            ),
            font=("Segoe UI", 9),
            fill="#333333",
        )

    def _draw_period_chart(
        self,
        canvas: tk.Canvas,
        range_name: str,
        reference_date: date | None,
        title_label: str,
    ) -> None:
        if range_name == "week":
            rows = self.store.daily_totals("week", reference_date)
            labels = [WEEKDAYS[self.language][row.start_date.weekday()] for row in rows]
            self._draw_simple_bar_chart(
                canvas,
                labels,
                [row.total_seconds for row in rows],
                self.t("daily_work_distribution", title=title_label),
            )
            return

        if range_name == "month":
            rows = self.store.daily_totals("month", reference_date)
            self._draw_month_calendar_heatmap(canvas, rows, title_label)
            return

        if range_name == "year":
            rows = self.store.monthly_totals(reference_date)
            self._draw_simple_bar_chart(
                canvas,
                [self.t("month_short", value=int(row.label)) for row in rows],
                [row.total_seconds for row in rows],
                self.t("monthly_work_distribution", title=title_label),
            )

    def _draw_simple_bar_chart(
        self, canvas: tk.Canvas, labels: list[str], values: list[int], title: str
    ) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        margin_left = 54
        margin_right = 18
        margin_top = 52
        margin_bottom = 58
        chart_width = max(width - margin_left - margin_right, 1)
        chart_height = max(height - margin_top - margin_bottom, 1)

        canvas.create_text(16, 18, anchor="w", text=title, font=("Segoe UI", 12, "bold"))
        max_seconds = max(values, default=0)
        if max_seconds <= 0:
            self._draw_empty_state(canvas, width, height, self.t("no_records"))
            return

        y_axis_bottom = margin_top + chart_height
        canvas.create_line(margin_left, margin_top, margin_left, y_axis_bottom, fill="#777777")
        canvas.create_line(margin_left, y_axis_bottom, width - margin_right, y_axis_bottom, fill="#777777")

        for index in range(5):
            value = max_seconds * index / 4
            y = y_axis_bottom - (value / max_seconds) * chart_height
            canvas.create_line(margin_left - 4, y, width - margin_right, y, fill="#eeeeee")
            canvas.create_text(
                margin_left - 8,
                y,
                anchor="e",
                text=self._format_hours(value),
                font=("Segoe UI", 8),
                fill="#555555",
            )

        gap = 8 if len(values) <= 7 else 5
        bar_width = max((chart_width - gap * (len(values) - 1)) / max(len(values), 1), 3)
        for index, value in enumerate(values):
            x0 = margin_left + index * (bar_width + gap)
            x1 = x0 + bar_width
            y0 = y_axis_bottom - (value / max_seconds) * chart_height
            canvas.create_rectangle(x0, y0, x1, y_axis_bottom, fill="#4F9A9A", outline="#ffffff")
            canvas.create_text(
                (x0 + x1) / 2,
                y_axis_bottom + 14,
                text=labels[index],
                font=("Segoe UI", 8),
                fill="#444444",
            )

        busiest_index = max(range(len(values)), key=lambda index: values[index])
        canvas.create_text(
            margin_left,
            height - 22,
            anchor="w",
            text=self.t(
                "busiest_period",
                label=labels[busiest_index],
                duration=self._format_hours(values[busiest_index]),
            ),
            font=("Segoe UI", 9),
            fill="#333333",
        )

    def _draw_month_calendar_heatmap(self, canvas: tk.Canvas, rows, title_label: str) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.create_text(
            16,
            18,
            anchor="w",
            text=self.t("daily_calendar_heatmap", title=title_label),
            font=("Segoe UI", 12, "bold"),
        )

        if not rows:
            self._draw_empty_state(canvas, width, height, self.t("no_records"))
            return

        max_seconds = max((row.total_seconds for row in rows), default=0)
        today = date.today()
        month_weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
            rows[0].start_date.year, rows[0].start_date.month
        )
        row_by_date = {row.start_date: row for row in rows}
        grid_left = 18
        grid_top = 56
        available_width = max(width - 36, 1)
        available_height = max(height - grid_top - 36, 1)
        cell_gap = 4
        cell_size = max(
            min(
                (available_width - cell_gap * 6) / 7,
                (available_height - cell_gap * (len(month_weeks) - 1)) / max(len(month_weeks), 1),
            ),
            18,
        )

        for index, weekday in enumerate(WEEKDAYS[self.language]):
            x = grid_left + index * (cell_size + cell_gap) + cell_size / 2
            canvas.create_text(x, grid_top - 14, text=weekday, font=("Segoe UI", 8), fill="#555555")

        for week_index, week in enumerate(month_weeks):
            for day_index, day_value in enumerate(week):
                x0 = grid_left + day_index * (cell_size + cell_gap)
                y0 = grid_top + week_index * (cell_size + cell_gap)
                x1 = x0 + cell_size
                y1 = y0 + cell_size
                row = row_by_date.get(day_value)
                if row is None:
                    fill = "#f4f4f4"
                    text = ""
                elif day_value > today:
                    fill = "#eeeeee"
                    text = ""
                else:
                    fill = self._crest_color(row.total_seconds / max_seconds if max_seconds else 0)
                    text = str(day_value.day)
                canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="#ffffff")
                if text:
                    canvas.create_text(
                        (x0 + x1) / 2,
                        y0 + 12,
                        text=text,
                        font=("Segoe UI", 8),
                        fill="#1f2933",
                    )
                    if row and row.total_seconds > 0 and cell_size >= 34:
                        canvas.create_text(
                            (x0 + x1) / 2,
                            y1 - 12,
                            text=self._format_hours(row.total_seconds),
                            font=("Segoe UI", 7),
                            fill="#1f2933",
                        )

    def _crest_color(self, value: float) -> str:
        value = max(0.0, min(1.0, value))
        stops = (
            (0.0, (231, 244, 235)),
            (0.35, (133, 194, 174)),
            (0.70, (46, 129, 145)),
            (1.0, (43, 45, 110)),
        )
        for index in range(len(stops) - 1):
            left_value, left_color = stops[index]
            right_value, right_color = stops[index + 1]
            if value <= right_value:
                span = right_value - left_value
                ratio = 0 if span == 0 else (value - left_value) / span
                rgb = tuple(
                    int(left_color[channel] + (right_color[channel] - left_color[channel]) * ratio)
                    for channel in range(3)
                )
                return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        r, g, b = stops[-1][1]
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw_pie_chart(self, canvas: tk.Canvas, category_rows, title_label: str) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)

        canvas.create_text(
            16,
            18,
            anchor="w",
            text=self.t("category_share", title=title_label),
            font=("Segoe UI", 12, "bold"),
        )

        total_seconds = sum(row.total_seconds for row in category_rows)
        if total_seconds <= 0:
            self._draw_empty_state(canvas, width, height, self.t("no_records"))
            return

        canvas.create_text(
            16,
            42,
            anchor="w",
            text=self.t("total_work", duration=self._format_hours(total_seconds)),
            font=("Segoe UI", 10),
            fill="#333333",
        )

        diameter = min(width * 0.52, height * 0.48, 220)
        x0 = 24
        y0 = 76
        x1 = x0 + diameter
        y1 = y0 + diameter

        if len(category_rows) == 1:
            canvas.create_oval(
                x0,
                y0,
                x1,
                y1,
                fill=CATEGORY_COLORS[category_rows[0].category],
                outline="#ffffff",
            )
        else:
            start_angle = 90
            for row in category_rows:
                extent = 360 * row.total_seconds / total_seconds
                canvas.create_arc(
                    x0,
                    y0,
                    x1,
                    y1,
                    start=start_angle,
                    extent=-extent,
                    fill=CATEGORY_COLORS[row.category],
                    outline="#ffffff",
                )
                start_angle -= extent

        legend_x = x1 + 24
        legend_y = 62
        for index, row in enumerate(category_rows):
            y = legend_y + index * 28
            percent = row.total_seconds / total_seconds * 100
            canvas.create_rectangle(
                legend_x,
                y,
                legend_x + 12,
                y + 12,
                fill=CATEGORY_COLORS[row.category],
                outline="",
            )
            canvas.create_text(
                legend_x + 18,
                y + 6,
                anchor="w",
                text=(
                    f"{category_label(self.language, row.category)} "
                    f"{self._format_hours(row.total_seconds)} ({percent:.1f}%)"
                ),
                font=("Segoe UI", 9),
                fill="#333333",
            )

    def _draw_empty_state(self, canvas: tk.Canvas, width: int, height: int, text: str) -> None:
        canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            font=("Segoe UI", 11),
            fill="#666666",
        )

    def _format_hours(self, seconds: float) -> str:
        hours = seconds / 3600
        if hours < 1:
            minutes = int(round(seconds / 60))
            return self.t("minutes", value=minutes)
        return self.t("hours", value=hours)

    def _history_title(self, range_name: str, reference_date: date) -> str:
        if range_name == "day":
            return reference_date.isoformat()
        if range_name == "week":
            start_time, end_time = build_range_bounds("week", reference_date)
            end_date = (end_time.date() - timedelta(days=1)).isoformat()
            return self.t("week_range", start=start_time.date().isoformat(), end=end_date)
        if range_name == "month":
            return f"{reference_date.year}-{reference_date.month:02d}"
        if range_name == "year":
            return str(reference_date.year)
        return reference_date.isoformat()

    def _on_close(self) -> None:
        if self.current_start is not None:
            should_close = messagebox.askyesno(
                self.t("close_title"),
                self.t("close_message"),
            )
            if not should_close:
                return
        self.store.close()
        self.destroy()


def main() -> None:
    app = FlowmoApp()
    app.mainloop()

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import TclError
from typing import Callable

from .api import QuotaClient, QuotaError, QuotaSnapshot, RateLimit, UsageSummary, parse_snapshot
from .config import AppSettings, ConfigStore, KeyResolutionError, KeyResolver
from .formatting import (
    format_amount,
    format_compact,
    format_reset,
    format_updated,
    format_window,
)
from .font_loader import (
    MONO_FONT,
    UI_FONT,
    FontLoadError,
    LoadedFonts,
    load_bundled_fonts,
)
from .i18n import translate
from .instance_lock import InstanceLock


BG = "#17191c"
BG_HOVER = "#272b30"
FG = "#f4f5f2"
MUTED = "#a9afb5"
SUBTLE = "#737b83"
GREEN = "#48c78e"
AMBER = "#e6b450"
RED = "#ef6a6a"
TRACK = "#343940"
FONT = UI_FONT

ERROR_MESSAGE_KEYS = {
    "missing_key": "error_missing_key",
    "manual_key_missing": "error_missing_key",
    "invalid_key": "error_invalid_key",
    "rate_limited": "error_rate_limited",
    "timeout": "error_timeout",
    "network": "error_network",
    "invalid_json": "error_invalid_json",
    "invalid_response": "error_invalid_response",
    "codex_config_missing": "error_codex_config",
    "provider_mismatch": "error_provider_mismatch",
    "codex_auth_missing": "error_codex_auth",
    "codex_key_missing": "error_codex_key",
    "invalid_status": "error_invalid_status",
    "unknown": "error_unknown",
}


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str | Callable[[], str]) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event[tk.Widget]) -> None:
        self._hide()
        self.after_id = self.widget.after(450, self._show)

    def _show(self) -> None:
        self.after_id = None
        content = self.text() if callable(self.text) else self.text
        if not content:
            return
        window = tk.Toplevel(self.widget)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        label = tk.Label(
            window,
            text=content,
            justify="left",
            bg="#0e1012",
            fg=FG,
            font=(FONT, 9),
            padx=9,
            pady=6,
            bd=0,
        )
        label.pack()
        window.update_idletasks()
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        window.geometry(f"+{x}+{y}")
        self.window = window

    def _hide(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


class TokenQuotaWidget:
    WIDTH = 326
    HEIGHT = 158
    FULL_REFRESH_SECONDS = 65
    FULL_MIN_SECONDS = 22

    def __init__(
        self,
        root: tk.Tk,
        *,
        client: QuotaClient | None = None,
        store: ConfigStore | None = None,
        resolver: KeyResolver | None = None,
        demo: bool = False,
        geometry: str | None = None,
        persist_settings: bool = True,
    ) -> None:
        self.root = root
        self.client = client or QuotaClient()
        self.store = store or ConfigStore()
        self.resolver = resolver or KeyResolver(endpoint=self.client.endpoint)
        self.settings = self.store.load() if persist_settings else AppSettings(opacity=0.94)
        self.persist_settings = persist_settings
        self.demo = demo
        self.manual_key: str | None = None
        self.key_mode = "auto"
        self.events: queue.Queue[tuple[str, str, object]] = queue.Queue()
        self.pending: set[str] = set()
        self.mode_errors: dict[str, object] = {}
        self.last_full_started = 0.0
        self.rate_limit: RateLimit | None = None
        self.usage: UsageSummary | None = None
        self.quota_as_of: datetime | None = None
        self.usage_as_of: datetime | None = None
        self.settings_window: tk.Toplevel | None = None
        self.drag_origin: tuple[int, int, int, int] | None = None
        self.closed = False
        self.light_after_id: str | None = None
        self.full_after_id: str | None = None
        self.queue_after_id: str | None = None

        self._configure_window(geometry)
        self._build_ui()
        self._bind_events()
        self._render()
        self.queue_after_id = self.root.after(100, self._drain_events)

        if demo:
            self._apply_snapshot(_demo_snapshot())
        else:
            self._request("light", show_settings_on_missing=True)
            self.root.after(900, lambda: self._request("full"))
            self._schedule_light()
            self._schedule_full()

    def _configure_window(self, geometry: str | None) -> None:
        self.root.title("Token Quota Widget")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        if geometry:
            self.root.geometry(geometry)
        else:
            self.root.update_idletasks()
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            default_x = max(12, screen_w - self.WIDTH - 24)
            default_y = 36
            x = self.settings.x if self.settings.x is not None else default_x
            y = self.settings.y if self.settings.y is not None else default_y
            x = min(max(0, x), max(0, screen_w - self.WIDTH))
            y = min(max(0, y), max(0, screen_h - self.HEIGHT))
            self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        self.root.update_idletasks()
        self.root.attributes("-alpha", self.settings.opacity)

    def _build_ui(self) -> None:
        self.surface = tk.Frame(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=BG,
            bd=0,
            highlightthickness=1,
            highlightbackground="#30343a",
        )
        self.surface.pack(fill="both", expand=True)
        self.surface.pack_propagate(False)

        self.status_canvas = tk.Canvas(
            self.surface,
            width=10,
            height=10,
            bg=BG,
            bd=0,
            highlightthickness=0,
        )
        self.status_canvas.place(x=14, y=16, width=10, height=10)
        self.status_dot = self.status_canvas.create_oval(1, 1, 9, 9, fill=AMBER, outline="")

        self.title_label = tk.Label(
            self.surface,
            text=self._t("remaining"),
            bg=BG,
            fg=MUTED,
            font=(FONT, 10),
            anchor="w",
        )
        self.title_label.place(x=29, y=9, width=200, height=24)

        self.refresh_button = self._icon_button("↻", 236, self.manual_refresh, "refresh")
        self.settings_button = self._icon_button("⚙", 265, self.open_settings, "settings")
        self.close_button = self._icon_button("×", 294, self.close, "close")

        self.balance_label = tk.Label(
            self.surface,
            text="--",
            bg=BG,
            fg=FG,
            font=(FONT, 25, "bold"),
            anchor="w",
        )
        self.balance_label.place(x=13, y=35, width=300, height=39)

        self.used_label = tk.Label(
            self.surface,
            text=self._t("connecting"),
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        self.used_label.place(x=14, y=75, width=298, height=20)

        self.progress = tk.Canvas(
            self.surface,
            width=298,
            height=5,
            bg=BG,
            bd=0,
            highlightthickness=0,
        )
        self.progress.place(x=14, y=99, width=298, height=5)
        self.progress.create_rectangle(0, 0, 298, 5, fill=TRACK, outline="")
        self.progress_fill = self.progress.create_rectangle(0, 0, 0, 5, fill=GREEN, outline="")

        self.token_label = tk.Label(
            self.surface,
            text=self._t("tokens_pending"),
            bg=BG,
            fg=FG,
            font=(FONT, 10, "bold"),
            anchor="w",
        )
        self.token_label.place(x=14, y=108, width=298, height=22)
        self.token_tooltip = Tooltip(self.token_label, self._usage_tooltip_text)

        self.footer_label = tk.Label(
            self.surface,
            text=self._t("waiting_update"),
            bg=BG,
            fg=SUBTLE,
            font=(FONT, 8),
            anchor="e",
        )
        self.footer_label.place(x=14, y=135, width=298, height=15)

        self.menu = tk.Menu(
            self.root,
            tearoff=False,
            bg="#202328",
            fg=FG,
            activebackground=BG_HOVER,
            activeforeground=FG,
            bd=0,
            font=(FONT, 9),
        )
        self.menu.add_command(label=self._t("refresh"), command=self.manual_refresh)
        self.menu.add_command(label=self._t("settings"), command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_command(label=self._t("quit"), command=self.close)

    def _icon_button(
        self,
        text: str,
        x: int,
        command: Callable[[], None],
        tooltip_key: str,
    ) -> tk.Label:
        label = tk.Label(
            self.surface,
            text=text,
            bg=BG,
            fg=MUTED,
            activebackground=BG_HOVER,
            activeforeground=FG,
            font=(FONT, 13),
            anchor="center",
            cursor="hand2",
        )
        label.place(x=x, y=5, width=27, height=28)
        label._quota_interactive = True  # type: ignore[attr-defined]
        label.bind("<ButtonRelease-1>", lambda _event: command())
        label.bind("<Enter>", lambda _event: label.configure(bg=BG_HOVER, fg=FG))
        label.bind("<Leave>", lambda _event: label.configure(bg=BG, fg=MUTED))
        Tooltip(label, lambda: self._t(tooltip_key))
        return label

    def _t(self, key: str, **values: object) -> str:
        return translate(self.settings.language, key, **values)

    def _apply_language(self) -> None:
        self.menu.entryconfigure(0, label=self._t("refresh"))
        self.menu.entryconfigure(1, label=self._t("settings"))
        self.menu.entryconfigure(3, label=self._t("quit"))
        self._render()

    def _bind_events(self) -> None:
        self.root.bind("<ButtonPress-1>", self._drag_start, add="+")
        self.root.bind("<B1-Motion>", self._drag_move, add="+")
        self.root.bind("<ButtonRelease-1>", self._drag_end, add="+")
        self.root.bind("<Button-3>", self._show_menu, add="+")
        self.root.bind("<Control-r>", lambda _event: self.manual_refresh())
        self.root.bind("<Control-comma>", lambda _event: self.open_settings())
        self.root.bind("<Control-q>", lambda _event: self.close())

    def _drag_start(self, event: tk.Event[tk.Widget]) -> None:
        if getattr(event.widget, "_quota_interactive", False):
            return
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def _drag_move(self, event: tk.Event[tk.Widget]) -> None:
        if self.drag_origin is None:
            return
        start_x, start_y, window_x, window_y = self.drag_origin
        self.root.geometry(f"+{window_x + event.x_root - start_x}+{window_y + event.y_root - start_y}")

    def _drag_end(self, _event: tk.Event[tk.Widget]) -> None:
        if self.drag_origin is None:
            return
        self.drag_origin = None
        self.settings.x = self.root.winfo_x()
        self.settings.y = self.root.winfo_y()
        self._save_settings()

    def _show_menu(self, event: tk.Event[tk.Widget]) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _resolve_key(self) -> str:
        if self.key_mode == "manual":
            if self.manual_key:
                return self.manual_key
            raise KeyResolutionError("请填写 API Key", code="manual_key_missing")
        return self.resolver.resolve().key

    def _request(self, mode: str, *, show_settings_on_missing: bool = False) -> None:
        if self.demo or self.closed or mode in self.pending:
            return
        if mode == "full":
            elapsed = time.monotonic() - self.last_full_started
            if elapsed < self.FULL_MIN_SECONDS:
                return
        try:
            key = self._resolve_key()
        except KeyResolutionError as exc:
            self.mode_errors[mode] = exc
            self._render()
            if show_settings_on_missing:
                self.root.after(300, self.open_settings)
            return

        self.pending.add(mode)
        if mode == "full":
            self.last_full_started = time.monotonic()
        self._render_status()
        thread = threading.Thread(
            target=self._fetch_worker,
            args=(mode, key),
            name=f"quota-{mode}",
            daemon=True,
        )
        thread.start()

    def _fetch_worker(self, mode: str, key: str) -> None:
        try:
            snapshot = self.client.fetch(key, mode)
        except (QuotaError, OSError) as exc:
            self.events.put(("error", mode, exc))
        except Exception:
            self.events.put(
                ("error", mode, QuotaError("查询时发生未知错误", code="unknown"))
            )
        else:
            self.events.put(("success", mode, snapshot))

    def _drain_events(self) -> None:
        if self.closed:
            return
        while True:
            try:
                kind, mode, payload = self.events.get_nowait()
            except queue.Empty:
                break
            self.pending.discard(mode)
            if kind == "success" and isinstance(payload, QuotaSnapshot):
                self.mode_errors.pop(mode, None)
                self._apply_snapshot(payload)
            else:
                self.mode_errors[mode] = payload
                self._render()
        self.queue_after_id = self.root.after(100, self._drain_events)

    def _apply_snapshot(self, snapshot: QuotaSnapshot) -> None:
        if (
            self.quota_as_of is None
            or snapshot.as_of is None
            or snapshot.as_of >= self.quota_as_of
        ):
            self.rate_limit = snapshot.primary_rate_limit
            self.quota_as_of = snapshot.as_of
        if snapshot.usage is not None:
            self.usage = snapshot.usage
            self.usage_as_of = snapshot.as_of
        if not snapshot.is_valid:
            self.mode_errors[snapshot.mode] = QuotaError(
                "当前额度状态无效",
                code="invalid_status",
            )
        self._render()

    def _error_text(self, error: object, language: str | None = None) -> str:
        language = language or self.settings.language
        code = getattr(error, "code", "unknown")
        if code == "server_error":
            status = getattr(error, "status_code", None) or "?"
            return translate(language, "error_server", status=status)
        key = ERROR_MESSAGE_KEYS.get(str(code), "error_unknown")
        return translate(language, key)

    def _render(self) -> None:
        rate = self.rate_limit
        if rate is None:
            self.title_label.configure(text=self._t("remaining"))
            self.balance_label.configure(text="--")
            if self.mode_errors:
                error = next(iter(self.mode_errors.values()))
                self.used_label.configure(text=self._error_text(error))
            else:
                self.used_label.configure(text=self._t("connecting"))
            self.progress.coords(self.progress_fill, 0, 0, 0, 5)
        else:
            window = format_window(rate.window, self.settings.language)
            self.title_label.configure(
                text=self._t("window_remaining", window=window)
            )
            self.balance_label.configure(text=format_amount(rate.remaining, rate.unit))
            self.used_label.configure(
                text=self._t(
                    "used",
                    used=format_amount(rate.used, rate.unit),
                    limit=format_amount(rate.limit, rate.unit),
                )
            )
            width = round(298 * rate.used_fraction)
            if rate.used_fraction >= 0.90:
                color = RED
            elif rate.used_fraction >= 0.70:
                color = AMBER
            else:
                color = GREEN
            self.progress.coords(self.progress_fill, 0, 0, width, 5)
            self.progress.itemconfigure(self.progress_fill, fill=color)

        if self.usage is None:
            self.token_label.configure(text=self._t("tokens_pending"))
        else:
            self.token_label.configure(
                text=self._t(
                    "tokens_summary",
                    hours=self.usage.hours,
                    tokens=format_compact(self.usage.total_tokens),
                )
            )

        if self.mode_errors and rate is not None:
            error = next(iter(self.mode_errors.values()))
            self.footer_label.configure(text=self._error_text(error), fg=AMBER)
        elif rate is not None:
            self.footer_label.configure(
                text=(
                    f"{format_reset(rate.reset_at, self.settings.language)} · "
                    f"{format_updated(self.quota_as_of, self.settings.language)}"
                ),
                fg=SUBTLE,
            )
        else:
            self.footer_label.configure(text=self._t("waiting_update"), fg=SUBTLE)
        self._render_status()

    def _render_status(self) -> None:
        if self.mode_errors:
            color = RED if self.rate_limit is None else AMBER
        elif self.pending:
            color = AMBER
        elif self.rate_limit is not None:
            color = GREEN
        else:
            color = AMBER
        self.status_canvas.itemconfigure(self.status_dot, fill=color)

    def _usage_tooltip_text(self) -> str:
        usage = self.usage
        if usage is None:
            return self._t("full_pending")
        return self._t(
            "usage_tooltip",
            input=format_compact(usage.input_tokens),
            output=format_compact(usage.output_tokens),
            cache=format_compact(usage.cache_read_tokens),
            requests=usage.requests,
        )

    def manual_refresh(self) -> None:
        self._request("light")
        self._request("full")

    def _schedule_light(self) -> None:
        if self.closed or self.demo:
            return
        if self.light_after_id is not None:
            self.root.after_cancel(self.light_after_id)
        self.light_after_id = self.root.after(
            self.settings.refresh_seconds * 1000,
            self._light_tick,
        )

    def _light_tick(self) -> None:
        self.light_after_id = None
        self._request("light")
        self._schedule_light()

    def _schedule_full(self) -> None:
        if self.closed or self.demo:
            return
        if self.full_after_id is not None:
            self.root.after_cancel(self.full_after_id)
        self.full_after_id = self.root.after(
            self.FULL_REFRESH_SECONDS * 1000,
            self._full_tick,
        )

    def _full_tick(self) -> None:
        self.full_after_id = None
        self._request("full")
        self._schedule_full()

    def open_settings(self) -> None:
        if self.closed:
            return
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        original_opacity = self.settings.opacity
        self.root.attributes("-topmost", False)
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        self.settings_window = dialog
        dialog.title(self._t("settings_title"))
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.attributes("-alpha", 0.98)
        dialog.geometry(self._dialog_geometry(480, 306))

        source_var = tk.StringVar(value=self.key_mode)
        key_var = tk.StringVar(value=self.manual_key or "")
        refresh_var = tk.StringVar(value=str(self.settings.refresh_seconds))
        opacity_var = tk.DoubleVar(value=self.settings.opacity)
        language_var = tk.StringVar(value=self.settings.language)
        source_status = tk.StringVar()
        error_var = tk.StringVar()

        auto_radio = tk.Radiobutton(
            dialog,
            text=self._t("source_auto"),
            value="auto",
            variable=source_var,
            bg=BG,
            fg=FG,
            activebackground=BG,
            activeforeground=FG,
            selectcolor=BG_HOVER,
            font=(FONT, 10),
            anchor="w",
            highlightthickness=0,
        )
        auto_radio.place(x=22, y=18, width=435, height=26)

        source_label = tk.Label(
            dialog,
            textvariable=source_status,
            bg=BG,
            fg=SUBTLE,
            font=(FONT, 8),
            anchor="w",
        )
        source_label.place(x=46, y=44, width=410, height=18)

        manual_radio = tk.Radiobutton(
            dialog,
            text=self._t("source_manual"),
            value="manual",
            variable=source_var,
            bg=BG,
            fg=FG,
            activebackground=BG,
            activeforeground=FG,
            selectcolor=BG_HOVER,
            font=(FONT, 10),
            anchor="w",
            highlightthickness=0,
        )
        manual_radio.place(x=22, y=68, width=435, height=26)

        key_entry = tk.Entry(
            dialog,
            textvariable=key_var,
            show="*",
            bg="#22262b",
            fg=FG,
            insertbackground=FG,
            disabledbackground="#1d2024",
            disabledforeground=SUBTLE,
            relief="flat",
            font=(MONO_FONT, 10),
        )
        key_entry.place(x=46, y=98, width=410, height=30)

        language_label = tk.Label(
            dialog,
            text=self._t("language"),
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        language_label.place(x=22, y=145, width=104, height=24)

        language_zh = tk.Radiobutton(
            dialog,
            text="中文",
            value="zh",
            variable=language_var,
            indicatoron=False,
            bg="#22262b",
            fg=FG,
            activebackground=BG_HOVER,
            activeforeground=FG,
            selectcolor=GREEN,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=(FONT, 9),
            cursor="hand2",
        )
        language_zh.place(x=136, y=141, width=72, height=28)

        language_en = tk.Radiobutton(
            dialog,
            text="English",
            value="en",
            variable=language_var,
            indicatoron=False,
            bg="#22262b",
            fg=FG,
            activebackground=BG_HOVER,
            activeforeground=FG,
            selectcolor=GREEN,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=(FONT, 9),
            cursor="hand2",
        )
        language_en.place(x=210, y=141, width=82, height=28)

        refresh_label = tk.Label(
            dialog,
            text=self._t("quota_refresh"),
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        refresh_label.place(x=22, y=181, width=104, height=24)
        refresh_spin = tk.Spinbox(
            dialog,
            from_=5,
            to=300,
            increment=5,
            textvariable=refresh_var,
            bg="#22262b",
            fg=FG,
            buttonbackground=BG_HOVER,
            insertbackground=FG,
            relief="flat",
            font=(FONT, 9),
            justify="right",
        )
        refresh_spin.place(x=136, y=179, width=74, height=28)
        seconds_label = tk.Label(
            dialog,
            text=self._t("seconds"),
            bg=BG,
            fg=SUBTLE,
            font=(FONT, 9),
            anchor="w",
        )
        seconds_label.place(x=216, y=181, width=40, height=24)

        opacity_label = tk.Label(
            dialog,
            text=self._t("opacity"),
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        opacity_label.place(x=22, y=218, width=104, height=24)
        opacity_scale = tk.Scale(
            dialog,
            from_=0.60,
            to=1.0,
            resolution=0.05,
            orient="horizontal",
            variable=opacity_var,
            command=lambda value: self.root.attributes("-alpha", float(value)),
            showvalue=False,
            bg=BG,
            fg=FG,
            troughcolor=TRACK,
            activebackground=GREEN,
            highlightthickness=0,
            bd=0,
            sliderlength=16,
        )
        opacity_scale.place(x=136, y=214, width=320, height=32)

        error_label = tk.Label(
            dialog,
            textvariable=error_var,
            bg=BG,
            fg=RED,
            font=(FONT, 8),
            anchor="w",
        )
        error_label.place(x=22, y=249, width=270, height=20)

        cancel_button = tk.Button(
            dialog,
            text=self._t("cancel"),
            command=lambda: cancel(),
            bg="#2a2e33",
            fg=FG,
            activebackground="#343940",
            activeforeground=FG,
            relief="flat",
            bd=0,
            font=(FONT, 9),
            cursor="hand2",
        )
        cancel_button.place(x=304, y=257, width=72, height=31)

        save_button = tk.Button(
            dialog,
            text=self._t("save"),
            bg=GREEN,
            fg="#101613",
            activebackground="#68d6a6",
            activeforeground="#101613",
            relief="flat",
            bd=0,
            font=(FONT, 9, "bold"),
            cursor="hand2",
        )
        save_button.place(x=384, y=257, width=72, height=31)

        def update_source_state(*_args: object) -> None:
            language = language_var.get()
            is_manual = source_var.get() == "manual"
            key_entry.configure(state="normal" if is_manual else "disabled")
            if is_manual:
                source_status.set(translate(language, "source_memory_only"))
                source_label.configure(fg=SUBTLE)
                key_entry.focus_set()
                return
            try:
                resolution = self.resolver.resolve()
            except KeyResolutionError as exc:
                source_status.set(self._error_text(exc, language))
                source_label.configure(fg=AMBER)
            else:
                text = translate(language, "source_found", source=resolution.source)
                if resolution.permission_mode is not None:
                    warning = translate(
                        language,
                        "source_permission",
                        mode=f"{resolution.permission_mode:o}",
                    )
                    text += f" · {warning}"
                    source_label.configure(fg=AMBER)
                else:
                    source_label.configure(fg=SUBTLE)
                source_status.set(text)

        def update_dialog_language(*_args: object) -> None:
            language = language_var.get()
            dialog.title(translate(language, "settings_title"))
            auto_radio.configure(text=translate(language, "source_auto"))
            manual_radio.configure(text=translate(language, "source_manual"))
            language_label.configure(text=translate(language, "language"))
            refresh_label.configure(text=translate(language, "quota_refresh"))
            seconds_label.configure(text=translate(language, "seconds"))
            opacity_label.configure(text=translate(language, "opacity"))
            cancel_button.configure(text=translate(language, "cancel"))
            save_button.configure(text=translate(language, "save"))
            error_var.set("")
            update_source_state()

        def cancel() -> None:
            self.root.attributes("-alpha", original_opacity)
            self.settings_window = None
            dialog.grab_release()
            dialog.destroy()
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()

        def save() -> None:
            language = language_var.get()
            mode = source_var.get()
            if mode == "manual":
                key = key_var.get().strip()
                if not key:
                    error_var.set(translate(language, "error_missing_key"))
                    key_entry.focus_set()
                    return
            else:
                try:
                    self.resolver.resolve()
                except KeyResolutionError as exc:
                    error_var.set(self._error_text(exc, language))
                    return
                key = None
            try:
                refresh = int(refresh_var.get())
            except ValueError:
                error_var.set(translate(language, "error_refresh_number"))
                return
            if not 5 <= refresh <= 300:
                error_var.set(translate(language, "error_refresh_range"))
                return

            self.key_mode = mode
            self.manual_key = key
            self.settings.refresh_seconds = refresh
            self.settings.opacity = float(opacity_var.get())
            self.settings.language = language
            self.root.attributes("-alpha", self.settings.opacity)
            self.mode_errors.clear()
            self._apply_language()
            self._save_settings()
            self._schedule_light()
            self.settings_window = None
            dialog.grab_release()
            key_var.set("")
            dialog.destroy()
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.manual_refresh()

        source_var.trace_add("write", update_source_state)
        language_var.trace_add("write", update_dialog_language)
        save_button.configure(command=save)
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.bind("<Escape>", lambda _event: cancel())
        dialog.bind("<Return>", lambda _event: save())
        update_dialog_language()
        self.root.withdraw()
        dialog.deiconify()
        dialog.lift()
        dialog.grab_set()

    def _dialog_geometry(self, width: int, height: int) -> str:
        x = self.root.winfo_x() + (self.WIDTH - width) // 2
        y = self.root.winfo_y() + 24
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = min(max(0, x), max(0, screen_w - width))
        y = min(max(0, y), max(0, screen_h - height))
        return f"{width}x{height}+{x}+{y}"

    def _save_settings(self) -> None:
        if not self.persist_settings:
            return
        try:
            self.store.save(self.settings)
        except OSError:
            pass

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.settings.x = self.root.winfo_x()
        self.settings.y = self.root.winfo_y()
        self._save_settings()
        for after_id in (self.light_after_id, self.full_after_id, self.queue_after_id):
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except TclError:
                    pass
        self.root.destroy()


def _demo_snapshot() -> QuotaSnapshot:
    return parse_snapshot(
        {
            "mode": "full",
            "status": "active",
            "is_valid": True,
            "as_of": datetime.now().astimezone().isoformat(),
            "rate_limits": [
                {
                    "window": "7d",
                    "limit": 240.7558,
                    "used": 38.2674,
                    "remaining": 202.4884,
                    "unit": "USD",
                    "reset_at": datetime.now().astimezone().replace(hour=11, minute=24).isoformat(),
                }
            ],
            "usage_range": {"hours": 72},
            "usage": {
                "requests": 264,
                "input_tokens": 2_767_697,
                "output_tokens": 128_542,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 18_069_376,
                "total_tokens": 20_965_615,
                "cost": 27.2609,
            },
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="透明的 Quota Share 桌面额度组件")
    parser.add_argument("--demo", action="store_true", help="使用演示数据，不访问网络")
    parser.add_argument("--geometry", help="覆盖 Tk 窗口位置，例如 326x158+40+40")
    parser.add_argument("--no-lock", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--quit-after", type=float, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lock: InstanceLock | None = None
    loaded_fonts: LoadedFonts | None = None
    if not args.no_lock and not args.demo:
        try:
            lock = InstanceLock()
        except (RuntimeError, OSError) as exc:
            print(exc, file=sys.stderr)
            return 2

    try:
        try:
            loaded_fonts = load_bundled_fonts()
        except FontLoadError as exc:
            print(f"无法加载内置字体：{exc}", file=sys.stderr)
            return 1

        try:
            root = tk.Tk()
        except TclError as exc:
            print(f"无法连接桌面显示：{exc}", file=sys.stderr)
            return 1

        app = TokenQuotaWidget(
            root,
            demo=args.demo,
            geometry=args.geometry,
            persist_settings=not args.demo,
        )
        if args.quit_after and args.quit_after > 0:
            root.after(round(args.quit_after * 1000), app.close)
        root.mainloop()
        return 0
    finally:
        if loaded_fonts is not None:
            loaded_fonts.close()
        if lock:
            lock.close()

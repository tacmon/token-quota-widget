from __future__ import annotations

import os
import tkinter as tk
import unittest
from unittest.mock import patch

from token_quota_widget.api import RateLimit
from token_quota_widget.ui import AMBER, GREEN, RED, TokenQuotaWidget


@unittest.skipUnless(os.name == "nt", "Windows Tk layout behavior")
class UsedPercentageTests(unittest.TestCase):
    @staticmethod
    def _destroy_root(root: tk.Tk) -> None:
        try:
            root.destroy()
        except tk.TclError:
            pass

    def _build_widget(self, *, is_windows: bool) -> TokenQuotaWidget:
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(self._destroy_root, root)
        with patch("token_quota_widget.ui.IS_WINDOWS", is_windows, create=True):
            app = TokenQuotaWidget(root, demo=True, persist_settings=False)
        root.update_idletasks()
        return app

    def test_windows_renders_percentage_and_clears_without_rate(self) -> None:
        app = self._build_widget(is_windows=True)
        label = getattr(app, "used_percent_label", None)

        self.assertIsNotNone(label)
        assert label is not None
        self.assertEqual(label.cget("text"), "16%")
        self.assertEqual(label.cget("foreground"), GREEN)
        self.assertEqual(label.place_info()["x"], "252")
        self.assertEqual(label.place_info()["width"], "60")
        self.assertEqual(app.used_label.place_info()["width"], "232")

        app.settings.language = "en"
        app._render()
        app.root.update_idletasks()
        self.assertLessEqual(app.used_label.winfo_reqwidth(), 232)
        self.assertLessEqual(label.winfo_reqwidth(), 60)

        app.rate_limit = None
        app._render()
        self.assertEqual(label.cget("text"), "")

    def test_windows_percentage_uses_progress_threshold_colors(self) -> None:
        app = self._build_widget(is_windows=True)
        label = app.used_percent_label
        assert label is not None

        cases = (
            (75.0, "75%", AMBER),
            (95.0, "95%", RED),
        )
        for used, expected_text, expected_color in cases:
            with self.subTest(used=used):
                app.rate_limit = RateLimit(
                    window="7d",
                    limit=100.0,
                    used=used,
                    remaining=100.0 - used,
                    unit="USD",
                    reset_at=None,
                )
                app._render()
                self.assertEqual(label.cget("text"), expected_text)
                self.assertEqual(label.cget("foreground"), expected_color)

    def test_non_windows_keeps_original_used_row(self) -> None:
        app = self._build_widget(is_windows=False)

        self.assertIsNone(app.used_percent_label)
        self.assertEqual(app.used_label.place_info()["width"], "298")


if __name__ == "__main__":
    unittest.main()

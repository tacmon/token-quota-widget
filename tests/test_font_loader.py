from __future__ import annotations

import io
import os
import tempfile
import tkinter as tk
import tkinter.font as tkfont
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tkinter import TclError
from unittest.mock import patch

from token_quota_widget.font_loader import (
    FONT_FILES,
    MONO_FONT,
    UI_FONT,
    FontLoadError,
    load_bundled_fonts,
)


class FontLoaderTests(unittest.TestCase):
    def test_all_declared_assets_exist(self) -> None:
        for path in FONT_FILES:
            self.assertTrue(path.is_file(), path.name)

    def test_non_windows_does_not_require_bundled_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            font_dir = Path(directory)
            with patch("token_quota_widget.font_loader.os.name", "posix"):
                try:
                    loaded = load_bundled_fonts(font_dir)
                except FontLoadError as exc:
                    self.fail(f"non-Windows startup required bundled fonts: {exc}")

        loaded.close()

    @unittest.skipUnless(os.name == "nt", "Windows private font API")
    def test_tk_resolves_bundled_families_and_weights(self) -> None:
        loaded = load_bundled_fonts()
        root = tk.Tk()
        root.withdraw()
        try:
            ui_regular = tkfont.Font(root, family=UI_FONT, size=10)
            ui_bold = tkfont.Font(root, family=UI_FONT, size=10, weight="bold")
            mono = tkfont.Font(root, family=MONO_FONT, size=10)
            self.assertEqual(
                ui_regular.actual("family").casefold(),
                UI_FONT.casefold(),
            )
            self.assertEqual(
                ui_bold.actual("family").casefold(),
                UI_FONT.casefold(),
            )
            self.assertEqual(ui_bold.actual("weight"), "bold")
            self.assertEqual(
                mono.actual("family").casefold(),
                MONO_FONT.casefold(),
            )
        finally:
            root.destroy()
            loaded.close()

    @unittest.skipUnless(os.name == "nt", "Windows private font API")
    def test_missing_assets_raise_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FontLoadError):
                load_bundled_fonts(Path(directory))

    def test_tk_startup_failure_closes_loaded_fonts(self) -> None:
        class FakeLoadedFonts:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        loaded = FakeLoadedFonts()
        with (
            patch(
                "token_quota_widget.ui.load_bundled_fonts",
                return_value=loaded,
            ),
            patch(
                "token_quota_widget.ui.tk.Tk",
                side_effect=TclError("test display failure"),
            ),
        ):
            from token_quota_widget.ui import main

            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--demo"]), 1)

        self.assertTrue(loaded.closed)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Callable


UI_FONT = "Noto Sans CJK SC"
MONO_FONT = "DejaVu Sans Mono"
FONT_DIR = Path(__file__).with_name("fonts")
FONT_NAMES = (
    "NotoSansCJKsc-Regular.otf",
    "NotoSansCJKsc-Bold.otf",
    "DejaVuSansMono.ttf",
    "DejaVuSansMono-Bold.ttf",
)
FONT_FILES = tuple(FONT_DIR / name for name in FONT_NAMES)
FR_PRIVATE = 0x10


class FontLoadError(RuntimeError):
    pass


class LoadedFonts:
    def __init__(
        self,
        paths: tuple[Path, ...] = (),
        remove_font: Callable[[str, int, object | None], int] | None = None,
    ) -> None:
        self._paths = paths
        self._remove_font = remove_font

    def close(self) -> None:
        paths = self._paths
        self._paths = ()
        if self._remove_font is None:
            return
        for path in reversed(paths):
            self._remove_font(str(path), FR_PRIVATE, None)


def _font_paths(font_dir: Path) -> tuple[Path, ...]:
    return tuple(font_dir / name for name in FONT_NAMES)


def _validate_assets(paths: tuple[Path, ...]) -> None:
    for path in paths:
        if not path.is_file():
            raise FontLoadError(f"缺少字体文件 {path.name}")


def load_bundled_fonts(font_dir: Path = FONT_DIR) -> LoadedFonts:
    if os.name != "nt":
        return LoadedFonts()

    paths = tuple(path.resolve() for path in _font_paths(font_dir))
    _validate_assets(paths)

    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    add_font = gdi32.AddFontResourceExW
    add_font.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p)
    add_font.restype = ctypes.c_int
    remove_font = gdi32.RemoveFontResourceExW
    remove_font.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p)
    remove_font.restype = wintypes.BOOL

    loaded: list[Path] = []
    for path in paths:
        ctypes.set_last_error(0)
        if add_font(str(path), FR_PRIVATE, None) == 0:
            for loaded_path in reversed(loaded):
                remove_font(str(loaded_path), FR_PRIVATE, None)
            code = ctypes.get_last_error()
            detail = f"（Windows 错误 {code}）" if code else ""
            raise FontLoadError(f"无法加载字体 {path.name}{detail}")
        loaded.append(path)
    return LoadedFonts(tuple(loaded), remove_font)

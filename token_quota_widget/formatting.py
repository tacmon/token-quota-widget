from __future__ import annotations

from datetime import datetime


def format_compact(value: int | float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        scaled, suffix = value / 1_000_000_000, "B"
    elif absolute >= 1_000_000:
        scaled, suffix = value / 1_000_000, "M"
    elif absolute >= 1_000:
        scaled, suffix = value / 1_000, "K"
    else:
        return f"{int(value):,}"
    rendered = f"{scaled:.2f}".rstrip("0").rstrip(".")
    return f"{rendered}{suffix}"


def format_amount(value: float, unit: str) -> str:
    normalized = unit.upper()
    if normalized == "USD":
        return f"${value:,.2f}"
    if normalized in {"CNY", "RMB"}:
        return f"¥{value:,.2f}"
    if "TOKEN" in normalized:
        return format_compact(value)
    suffix = f" {unit}" if unit else ""
    return f"{value:,.2f}{suffix}"


def format_window(value: str, language: str = "zh") -> str:
    if len(value) > 1 and value[:-1].isdigit():
        number = int(value[:-1])
        unit = value[-1].lower()
        if language == "en":
            suffix = {"d": "day", "h": "hour", "m": "minute"}.get(unit)
            if suffix:
                plural = "" if number == 1 else "s"
                return f"{number} {suffix}{plural}"
        else:
            suffix = {"d": "天", "h": "小时", "m": "分钟"}.get(unit)
            if suffix:
                return f"{number} {suffix}"
    return value or ("Current" if language == "en" else "当前")


def format_reset(value: datetime | None, language: str = "zh") -> str:
    if value is None:
        return "Reset time unknown" if language == "en" else "重置时间未知"
    local = value.astimezone()
    if language == "en":
        return f"Reset {local:%b %d %H:%M}"
    return f"{local:%m月%d日 %H:%M} 重置"


def format_updated(value: datetime | None, language: str = "zh") -> str:
    if value is None:
        return "Updated now" if language == "en" else "刚刚更新"
    if language == "en":
        return f"{value.astimezone():%H:%M}"
    return f"{value.astimezone():%H:%M} 更新"

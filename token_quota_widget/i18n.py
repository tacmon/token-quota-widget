from __future__ import annotations


SUPPORTED_LANGUAGES = ("zh", "en")


MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "remaining": "剩余额度",
        "window_remaining": "{window}剩余额度",
        "connecting": "正在连接额度服务",
        "used": "已用 {used} / {limit}",
        "tokens_pending": "近 72 小时 Token --",
        "tokens_summary": "近 {hours} 小时 Token {tokens}",
        "waiting_update": "等待首次更新",
        "refresh": "立即刷新",
        "settings": "设置",
        "close": "关闭",
        "quit": "退出",
        "full_pending": "完整数据尚未更新",
        "usage_tooltip": "输入 {input} · 输出 {output}\n缓存读取 {cache} · {requests:,} 次请求",
        "settings_title": "Token 额度设置",
        "source_auto": "自动读取环境变量或当前 Codex",
        "source_manual": "手动填写（仅本次运行）",
        "source_memory_only": "Key 不会写入磁盘",
        "source_found": "已找到：{source}",
        "source_permission": "权限 {mode}，建议 600",
        "quota_refresh": "额度刷新",
        "seconds": "秒",
        "opacity": "透明度",
        "language": "界面语言",
        "cancel": "取消",
        "save": "保存",
        "error_missing_key": "请填写 API Key",
        "error_invalid_key": "API Key 无效或无权查询",
        "error_rate_limited": "查询过快，请稍后再试",
        "error_server": "服务返回 HTTP {status}",
        "error_timeout": "连接超时",
        "error_network": "暂时无法连接额度服务",
        "error_invalid_json": "服务返回了无效的 JSON",
        "error_invalid_response": "服务返回的数据格式无效",
        "error_unknown": "查询时发生未知错误",
        "error_codex_config": "未找到可用的 Codex 配置",
        "error_provider_mismatch": "当前 Codex provider 与额度服务不匹配",
        "error_codex_auth": "未找到可用的 Codex 鉴权文件",
        "error_codex_key": "Codex 鉴权文件中没有 OPENAI_API_KEY",
        "error_invalid_status": "当前额度状态无效",
        "error_refresh_number": "刷新间隔必须是数字",
        "error_refresh_range": "刷新间隔应为 5 到 300 秒",
    },
    "en": {
        "remaining": "Remaining quota",
        "window_remaining": "{window} remaining",
        "connecting": "Connecting to quota service",
        "used": "Used {used} / {limit}",
        "tokens_pending": "Last 72h tokens --",
        "tokens_summary": "Last {hours}h tokens {tokens}",
        "waiting_update": "Waiting for first update",
        "refresh": "Refresh now",
        "settings": "Settings",
        "close": "Close",
        "quit": "Quit",
        "full_pending": "Detailed usage has not loaded yet",
        "usage_tooltip": "Input {input} · Output {output}\nCache read {cache} · {requests:,} requests",
        "settings_title": "Token Quota Settings",
        "source_auto": "Automatic: environment or Codex",
        "source_manual": "Manual entry (this session only)",
        "source_memory_only": "The key is not saved to disk",
        "source_found": "Found: {source}",
        "source_permission": "mode {mode}; 600 recommended",
        "quota_refresh": "Refresh",
        "seconds": "sec",
        "opacity": "Opacity",
        "language": "Language",
        "cancel": "Cancel",
        "save": "Save",
        "error_missing_key": "Enter an API key",
        "error_invalid_key": "The API key is invalid or unauthorized",
        "error_rate_limited": "Too many requests; try again shortly",
        "error_server": "Service returned HTTP {status}",
        "error_timeout": "Connection timed out",
        "error_network": "The quota service is unavailable",
        "error_invalid_json": "The service returned invalid JSON",
        "error_invalid_response": "The service returned invalid data",
        "error_unknown": "An unexpected error occurred",
        "error_codex_config": "No usable Codex configuration was found",
        "error_provider_mismatch": "The active Codex provider does not match this service",
        "error_codex_auth": "No usable Codex auth file was found",
        "error_codex_key": "OPENAI_API_KEY is missing from Codex auth",
        "error_invalid_status": "The current quota status is invalid",
        "error_refresh_number": "Refresh interval must be a number",
        "error_refresh_range": "Refresh interval must be 5 to 300 seconds",
    },
}


def normalize_language(value: object) -> str:
    return value if isinstance(value, str) and value in SUPPORTED_LANGUAGES else "zh"


def translate(language: str, key: str, **values: object) -> str:
    language = normalize_language(language)
    template = MESSAGES[language].get(key, MESSAGES["zh"].get(key, key))
    return template.format(**values)

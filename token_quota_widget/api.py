from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


DEFAULT_ENDPOINT = "https://sub2api.kinglong.de5.net/quota-share/api"


class QuotaError(RuntimeError):
    """A user-facing API error with optional HTTP metadata."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "unknown",
        status_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class RateLimit:
    window: str
    limit: float
    used: float
    remaining: float
    unit: str
    reset_at: datetime | None

    @property
    def used_fraction(self) -> float:
        if self.limit <= 0:
            return 0.0
        return min(1.0, max(0.0, self.used / self.limit))


@dataclass(frozen=True, slots=True)
class UsageSummary:
    hours: int
    requests: int
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    cost: float


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    mode: str
    status: str
    is_valid: bool
    as_of: datetime | None
    rate_limits: tuple[RateLimit, ...]
    usage: UsageSummary | None = None

    @property
    def primary_rate_limit(self) -> RateLimit:
        return self.rate_limits[0]


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_float(mapping: Mapping[str, Any], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QuotaError(f"接口字段 {key} 不是数字", code="invalid_response")
    return float(value)


def _as_int(mapping: Mapping[str, Any], key: str, default: int = 0) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)


def parse_snapshot(payload: Any) -> QuotaSnapshot:
    if not isinstance(payload, Mapping):
        raise QuotaError("接口返回的不是 JSON 对象", code="invalid_response")

    raw_limits = payload.get("rate_limits")
    if not isinstance(raw_limits, list) or not raw_limits:
        raise QuotaError("接口响应缺少额度数据", code="invalid_response")

    rate_limits: list[RateLimit] = []
    for raw in raw_limits:
        if not isinstance(raw, Mapping):
            raise QuotaError("接口中的额度数据格式无效", code="invalid_response")
        rate_limits.append(
            RateLimit(
                window=str(raw.get("window", "")),
                limit=_as_float(raw, "limit"),
                used=_as_float(raw, "used"),
                remaining=_as_float(raw, "remaining"),
                unit=str(raw.get("unit", "")),
                reset_at=_as_datetime(raw.get("reset_at")),
            )
        )

    usage: UsageSummary | None = None
    raw_usage = payload.get("usage")
    if isinstance(raw_usage, Mapping):
        raw_range = payload.get("usage_range")
        hours = 72
        if isinstance(raw_range, Mapping):
            hours = _as_int(raw_range, "hours", 72)
        usage = UsageSummary(
            hours=hours,
            requests=_as_int(raw_usage, "requests"),
            input_tokens=_as_int(raw_usage, "input_tokens"),
            output_tokens=_as_int(raw_usage, "output_tokens"),
            cache_creation_tokens=_as_int(raw_usage, "cache_creation_tokens"),
            cache_read_tokens=_as_int(raw_usage, "cache_read_tokens"),
            total_tokens=_as_int(raw_usage, "total_tokens"),
            cost=float(raw_usage.get("cost", 0.0) or 0.0),
        )

    return QuotaSnapshot(
        mode=str(payload.get("mode", "light")),
        status=str(payload.get("status", "unknown")),
        is_valid=bool(payload.get("is_valid", False)),
        as_of=_as_datetime(payload.get("as_of")),
        rate_limits=tuple(rate_limits),
        usage=usage,
    )


def _server_error_message(body: bytes) -> str | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    for key in ("message", "error", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and 0 < len(value) <= 240:
            return value
    return None


class QuotaClient:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 15.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def fetch(self, api_key: str, mode: str = "light") -> QuotaSnapshot:
        if mode not in {"light", "full"}:
            raise ValueError("mode must be 'light' or 'full'")
        if not api_key.strip():
            raise QuotaError("需要 API Key", code="missing_key")

        separator = "&" if urllib.parse.urlparse(self.endpoint).query else "?"
        url = f"{self.endpoint}{separator}{urllib.parse.urlencode({'mode': mode})}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key.strip()}",
                "User-Agent": "TokenQuotaWidget/0.2",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read(8192)
            retry_after = None
            raw_retry = exc.headers.get("Retry-After")
            if raw_retry and raw_retry.isdigit():
                retry_after = int(raw_retry)
            if exc.code in {401, 403}:
                message = "API Key 无效或无权查询"
                code = "invalid_key"
            elif exc.code == 429:
                message = "查询过快，请稍后再试"
                code = "rate_limited"
            else:
                message = _server_error_message(body) or f"服务返回 HTTP {exc.code}"
                code = "server_error"
            raise QuotaError(
                message,
                code=code,
                status_code=exc.code,
                retry_after=retry_after,
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                message = "连接超时"
                code = "timeout"
            else:
                message = "暂时无法连接额度服务"
                code = "network"
            raise QuotaError(message, code=code) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise QuotaError("连接超时", code="timeout") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QuotaError("服务返回了无效的 JSON", code="invalid_json") from exc

        return parse_snapshot(payload)

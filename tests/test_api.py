from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from token_quota_widget.api import QuotaClient, QuotaError, parse_snapshot
from token_quota_widget.formatting import (
    format_amount,
    format_compact,
    format_reset,
    format_updated,
    format_window,
)
from token_quota_widget.i18n import translate


FULL_PAYLOAD = {
    "api_version": "v1",
    "mode": "full",
    "status": "active",
    "is_valid": True,
    "as_of": "2026-07-20T00:57:39.567828318Z",
    "rate_limits": [
        {
            "window": "7d",
            "limit": 240.755795098,
            "used": 10.16262635,
            "remaining": 230.593168748,
            "unit": "USD",
            "reset_at": "2026-07-25T03:24:53Z",
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
        "cost": 27.26093895,
    },
}


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return self.body if amount < 0 else self.body[:amount]


class ParseSnapshotTests(unittest.TestCase):
    def test_parses_full_response(self) -> None:
        snapshot = parse_snapshot(FULL_PAYLOAD)

        self.assertEqual(snapshot.mode, "full")
        self.assertTrue(snapshot.is_valid)
        self.assertAlmostEqual(snapshot.primary_rate_limit.remaining, 230.593168748)
        self.assertEqual(snapshot.primary_rate_limit.window, "7d")
        self.assertIsNotNone(snapshot.usage)
        assert snapshot.usage is not None
        self.assertEqual(snapshot.usage.hours, 72)
        self.assertEqual(snapshot.usage.total_tokens, 20_965_615)

    def test_rejects_response_without_rate_limits(self) -> None:
        with self.assertRaisesRegex(QuotaError, "缺少额度数据") as context:
            parse_snapshot({"mode": "light", "rate_limits": []})
        self.assertEqual(context.exception.code, "invalid_response")

    def test_fraction_is_clamped(self) -> None:
        payload = dict(FULL_PAYLOAD)
        payload["rate_limits"] = [dict(FULL_PAYLOAD["rate_limits"][0], used=999.0)]
        self.assertEqual(parse_snapshot(payload).primary_rate_limit.used_fraction, 1.0)

    def test_formatters_keep_labels_compact(self) -> None:
        self.assertEqual(format_amount(230.5931, "USD"), "$230.59")
        self.assertEqual(format_compact(20_965_615), "20.97M")
        self.assertEqual(format_compact(128_542), "128.54K")

    def test_english_formatters_and_messages(self) -> None:
        snapshot = parse_snapshot(FULL_PAYLOAD)
        self.assertEqual(format_window("7d", "en"), "7 days")
        self.assertTrue(format_reset(snapshot.primary_rate_limit.reset_at, "en").startswith("Reset "))
        self.assertRegex(format_updated(snapshot.as_of, "en"), r"^\d{2}:\d{2}$")
        self.assertEqual(
            translate("en", "used", used="$10.16", limit="$240.76"),
            "Used $10.16 / $240.76",
        )


class QuotaClientTests(unittest.TestCase):
    def test_sends_key_in_header_not_url(self) -> None:
        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            self.assertEqual(timeout, 3.0)
            self.assertNotIn("test-secret", request.full_url)
            self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
            self.assertTrue(request.full_url.endswith("?mode=full"))
            return FakeResponse(FULL_PAYLOAD)

        client = QuotaClient("https://example.test/quota", timeout=3.0)
        with patch("token_quota_widget.api.urllib.request.urlopen", fake_urlopen):
            snapshot = client.fetch("test-secret", "full")

        self.assertEqual(snapshot.mode, "full")

    def test_empty_key_has_localizable_error_code(self) -> None:
        with self.assertRaises(QuotaError) as context:
            QuotaClient("https://example.test/quota").fetch("", "light")
        self.assertEqual(context.exception.code, "missing_key")


if __name__ == "__main__":
    unittest.main()

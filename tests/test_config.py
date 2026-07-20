from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from token_quota_widget.config import (
    AppSettings,
    ConfigStore,
    KeyResolutionError,
    KeyResolver,
)


class ConfigStoreTests(unittest.TestCase):
    def test_round_trip_is_private_and_contains_no_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "widget" / "config.json"
            store = ConfigStore(path)
            settings = AppSettings(
                refresh_seconds=25,
                opacity=0.8,
                language="en",
                x=12,
                y=34,
            )

            store.save(settings)

            self.assertEqual(store.load(), settings)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn("key", path.read_text(encoding="utf-8").lower())

    @unittest.skipUnless(os.name == "nt", "Windows path behavior")
    def test_default_path_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                store = ConfigStore()

        self.assertEqual(
            store.path,
            Path(directory) / "TokenQuotaWidget" / "config.json",
        )

    def test_invalid_values_fall_back_or_clamp(self) -> None:
        settings = AppSettings.from_mapping(
            {
                "refresh_seconds": 1,
                "opacity": 2.0,
                "language": "unsupported",
                "x": "bad",
            }
        )
        self.assertEqual(settings.refresh_seconds, 5)
        self.assertEqual(settings.opacity, 1.0)
        self.assertEqual(settings.language, "zh")
        self.assertIsNone(settings.x)

    def test_old_config_defaults_to_chinese(self) -> None:
        settings = AppSettings.from_mapping({"refresh_seconds": 15})
        self.assertEqual(settings.language, "zh")


class KeyResolverTests(unittest.TestCase):
    def _write_codex_files(self, directory: Path, host: str) -> None:
        (directory / "config.toml").write_text(
            "model_provider = \"provider\"\n"
            "[model_providers.provider]\n"
            f"base_url = \"https://{host}/v1\"\n",
            encoding="utf-8",
        )
        (directory / "auth.json").write_text(
            json.dumps({"OPENAI_API_KEY": "codex-secret"}),
            encoding="utf-8",
        )

    def test_reads_codex_key_only_for_matching_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory)
            self._write_codex_files(codex_home, "sub2api.kinglong.de5.net")
            resolver = KeyResolver(codex_home=codex_home, environ={})

            resolution = resolver.resolve()

            self.assertEqual(resolution.key, "codex-secret")
            self.assertEqual(resolution.source, "Codex auth")
            if os.name == "nt":
                self.assertIsNone(resolution.warning)
                self.assertIsNone(resolution.permission_mode)
            else:
                self.assertIsNotNone(resolution.warning)
                self.assertIsNotNone(resolution.permission_mode)

    def test_refuses_to_send_unrelated_codex_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory)
            self._write_codex_files(codex_home, "api.openai.com")
            resolver = KeyResolver(codex_home=codex_home, environ={})

            with self.assertRaisesRegex(KeyResolutionError, "provider.*不匹配") as context:
                resolver.resolve()
            self.assertEqual(context.exception.code, "provider_mismatch")

    def test_explicit_environment_key_has_priority(self) -> None:
        resolver = KeyResolver(
            codex_home=Path("/does/not/exist"),
            environ={"QUOTA_SHARE_API_KEY": "explicit-secret"},
        )
        self.assertEqual(resolver.resolve().key, "explicit-secret")


if __name__ == "__main__":
    unittest.main()

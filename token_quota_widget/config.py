from __future__ import annotations

import json
import os
import stat
import tempfile
import tomllib
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from .api import DEFAULT_ENDPOINT
from .i18n import normalize_language


class KeyResolutionError(RuntimeError):
    def __init__(self, message: str, *, code: str = "unknown") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class KeyResolution:
    key: str
    source: str
    warning: str | None = None
    permission_mode: int | None = None


@dataclass(slots=True)
class AppSettings:
    refresh_seconds: int = 15
    opacity: float = 0.90
    language: str = "zh"
    x: int | None = None
    y: int | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "AppSettings":
        refresh = data.get("refresh_seconds", 15)
        opacity = data.get("opacity", 0.90)
        language = normalize_language(data.get("language", "zh"))
        x = data.get("x")
        y = data.get("y")
        return cls(
            refresh_seconds=min(300, max(5, int(refresh)))
            if isinstance(refresh, (int, float)) and not isinstance(refresh, bool)
            else 15,
            opacity=min(1.0, max(0.60, float(opacity)))
            if isinstance(opacity, (int, float)) and not isinstance(opacity, bool)
            else 0.90,
            language=language,
            x=int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None,
            y=int(y) if isinstance(y, (int, float)) and not isinstance(y, bool) else None,
        )

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            if os.name == "nt":
                config_home = Path(
                    os.environ.get(
                        "LOCALAPPDATA",
                        Path.home() / "AppData" / "Local",
                    )
                )
                path = config_home / "TokenQuotaWidget" / "config.json"
            else:
                config_home = Path(
                    os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
                )
                path = config_home / "token-quota-widget" / "config.json"
        self.path = path

    def load(self) -> AppSettings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return AppSettings()
        if not isinstance(payload, Mapping):
            return AppSettings()
        return AppSettings.from_mapping(payload)

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                self.path.parent.chmod(0o700)
            except OSError:
                pass

        fd, temp_name = tempfile.mkstemp(
            prefix="config-",
            suffix=".json",
            dir=self.path.parent,
        )
        try:
            if os.name != "nt":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(settings.to_mapping(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.path)
            if os.name != "nt":
                self.path.chmod(0o600)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                Path(temp_name).unlink()
            except OSError:
                pass
            raise


class KeyResolver:
    """Resolve a key without ever copying it into the widget config file."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        codex_home: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.codex_home = codex_home or Path(
            os.environ.get("CODEX_HOME", Path.home() / ".codex")
        )
        self.environ = environ if environ is not None else os.environ

    def resolve(self) -> KeyResolution:
        explicit = self.environ.get("QUOTA_SHARE_API_KEY", "").strip()
        if explicit:
            return KeyResolution(explicit, "QUOTA_SHARE_API_KEY")
        return self._resolve_codex_key()

    def _resolve_codex_key(self) -> KeyResolution:
        config_path = self.codex_home / "config.toml"
        auth_path = self.codex_home / "auth.json"
        try:
            with config_path.open("rb") as handle:
                config = tomllib.load(handle)
        except (FileNotFoundError, OSError, tomllib.TOMLDecodeError) as exc:
            raise KeyResolutionError(
                "未找到可用的 Codex 配置",
                code="codex_config_missing",
            ) from exc

        provider_name = config.get("model_provider")
        providers = config.get("model_providers")
        provider = providers.get(provider_name) if isinstance(providers, Mapping) else None
        base_url = provider.get("base_url") if isinstance(provider, Mapping) else None
        provider_host = urllib.parse.urlparse(str(base_url or "")).hostname
        endpoint_host = urllib.parse.urlparse(self.endpoint).hostname
        if not provider_host or provider_host != endpoint_host:
            raise KeyResolutionError(
                "当前 Codex provider 与额度服务不匹配",
                code="provider_mismatch",
            )

        try:
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise KeyResolutionError(
                "未找到可用的 Codex 鉴权文件",
                code="codex_auth_missing",
            ) from exc
        key = payload.get("OPENAI_API_KEY") if isinstance(payload, Mapping) else None
        if not isinstance(key, str) or not key.strip():
            raise KeyResolutionError(
                "Codex 鉴权文件中没有 OPENAI_API_KEY",
                code="codex_key_missing",
            )

        warning = None
        permission_mode = None
        if os.name != "nt":
            try:
                mode = stat.S_IMODE(auth_path.stat().st_mode)
                if mode & 0o077:
                    warning = f"权限 {mode:o}，建议 600"
                    permission_mode = mode
            except OSError:
                pass
        return KeyResolution(key.strip(), "Codex auth", warning, permission_mode)

"""无数据库本地配置；命令行和环境变量可覆盖 TOML。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

DEFAULT_SOURCES = (
    "internet_archive",
    "open_library",
    "google_books",
)


@dataclass(frozen=True, slots=True)
class Settings:
    data_root: Path = Path("data")
    proxy: str = ""
    timeout_seconds: float = 30.0
    retries: int = 3
    sources: tuple[str, ...] = DEFAULT_SOURCES
    axiom_url: str = "http://127.0.0.1:8000"
    tls_verify: bool = True
    llm_model: str = "qwen-plus"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_timeout_seconds: float = 60.0
    llm_call_budget: int = 6
    llm_max_tokens: int = 4096

    @property
    def state_dir(self) -> Path:
        return self.data_root / ".qed-tracker"


def _default_config_paths() -> list[Path]:
    paths = [Path.cwd() / "qed-tracker.local.toml"]
    configured = os.getenv("QED_TRACKER_CONFIG")
    if configured:
        paths.insert(0, Path(configured).expanduser())
    paths.append(Path.home() / ".qed-tracker" / "config.toml")
    return paths


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_settings(config_path: Path | None = None, **overrides: Any) -> Settings:
    path = config_path
    if path is None:
        path = next((candidate for candidate in _default_config_paths() if candidate.exists()), None)
    raw = _read_toml(path) if path else {}
    core = raw.get("core", {})
    axiom = raw.get("axiom", {})
    llm = raw.get("llm", {})
    values: dict[str, Any] = {}
    if core.get("data_root"):
        values["data_root"] = Path(core["data_root"]).expanduser()
    if "proxy" in core:
        values["proxy"] = core["proxy"]
    if "timeout_seconds" in core:
        values["timeout_seconds"] = float(core["timeout_seconds"])
    if "retries" in core:
        values["retries"] = int(core["retries"])
    if "sources" in core:
        values["sources"] = tuple(core["sources"])
    if "tls_verify" in core:
        values["tls_verify"] = _bool(core["tls_verify"])
    if axiom.get("url"):
        values["axiom_url"] = axiom["url"].rstrip("/")
    if llm.get("model"):
        values["llm_model"] = str(llm["model"])
    if llm.get("base_url"):
        values["llm_base_url"] = str(llm["base_url"]).rstrip("/")
    if "timeout_seconds" in llm:
        values["llm_timeout_seconds"] = float(llm["timeout_seconds"])
    if "call_budget" in llm:
        values["llm_call_budget"] = int(llm["call_budget"])
    if "max_tokens" in llm:
        values["llm_max_tokens"] = int(llm["max_tokens"])

    env_map = {
        "QED_TRACKER_DATA_ROOT": ("data_root", Path),
        "QED_TRACKER_PROXY": ("proxy", str),
        "QED_TRACKER_TIMEOUT_SECONDS": ("timeout_seconds", float),
        "QED_TRACKER_RETRIES": ("retries", int),
        "QED_TRACKER_AXIOM_URL": ("axiom_url", str),
        "QED_TRACKER_TLS_VERIFY": ("tls_verify", _bool),
        "QED_TRACKER_LLM_MODEL": ("llm_model", str),
        "QED_TRACKER_LLM_BASE_URL": ("llm_base_url", str),
        "QED_TRACKER_LLM_TIMEOUT_SECONDS": ("llm_timeout_seconds", float),
        "QED_TRACKER_LLM_CALL_BUDGET": ("llm_call_budget", int),
        "QED_TRACKER_LLM_MAX_TOKENS": ("llm_max_tokens", int),
    }
    for env_name, (field_name, converter) in env_map.items():
        if env_name in os.environ:
            values[field_name] = converter(os.environ[env_name])
    if "QED_TRACKER_SOURCES" in os.environ:
        values["sources"] = tuple(item.strip() for item in os.environ["QED_TRACKER_SOURCES"].split(",") if item.strip())

    values.update({key: value for key, value in overrides.items() if value is not None})
    if "data_root" in values:
        values["data_root"] = Path(values["data_root"]).expanduser()
    settings = replace(Settings(), **values)
    data_root = settings.data_root
    if not data_root.is_absolute():
        data_root = (Path.cwd() / data_root).resolve()
    return replace(settings, data_root=data_root, axiom_url=settings.axiom_url.rstrip("/"), llm_base_url=settings.llm_base_url.rstrip("/"))


def llm_api_key() -> str:
    return os.getenv("QED_TRACKER_LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""


def example_config(data_root: str = "data") -> str:
    sources = ", ".join(f'"{name}"' for name in DEFAULT_SOURCES)
    return (
        "[core]\n"
        f'data_root = "{data_root.replace(chr(92), "/")}"\n'
        'proxy = ""\n'
        "timeout_seconds = 30\n"
        "retries = 3\n"
        "tls_verify = true\n"
        f"sources = [{sources}]\n\n"
        "[axiom]\n"
        'url = "http://127.0.0.1:8000"\n\n'
        "[llm]\n"
        'model = "qwen-plus"\n'
        'base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"\n'
        "timeout_seconds = 60\n"
        "call_budget = 6\n"
        "max_tokens = 4096\n"
    )

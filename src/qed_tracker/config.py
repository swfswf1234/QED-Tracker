"""统一配置：直读根 `.env` 的 `QED_*` 变量；本地 TOML 与 `QED_TRACKER_*` 已退役。

密钥（`QWEN_API_KEY`、`QED_DB_PASSWORD`）只经环境读取，不进入 `Settings` 的 repr。
无根 `.env` 时使用内置最小默认值；缺密钥时相关能力降级，不阻塞启动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

DEFAULT_SOURCES = (
    "internet_archive",
    "open_library",
    "google_books",
)

_DASH_SCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True, slots=True)
class Settings:
    data_root: Path = Path("dataset/qed-tracker")
    proxy: str = ""
    timeout_seconds: float = 30.0
    retries: int = 3
    sources: tuple[str, ...] = DEFAULT_SOURCES
    axiom_url: str = "http://127.0.0.1:8902"
    tls_verify: bool = True
    llm_model: str = "qwen-plus"
    llm_base_url: str = _DASH_SCOPE_BASE_URL
    llm_timeout_seconds: float = 60.0
    llm_call_budget: int = 6
    llm_max_tokens: int = 4096
    port: int = 8901
    tracker_url: str = "http://127.0.0.1:8901"
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "qed"
    db_user: str = "root"
    db_password: str = ""

    @property
    def state_dir(self) -> Path:
        return self.data_root / "meta"

    @property
    def db_configured(self) -> bool:
        return bool(self.db_password)

    @property
    def llm_configured(self) -> bool:
        return bool(llm_api_key())


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


_ENV_MAP = {
    "QED_MODEL": ("llm_model", str),
    "QED_AXIOM_URL": ("axiom_url", str),
    "QED_TRACKER_PORT": ("port", int),
    "QED_TRACKER_URL": ("tracker_url", str),
    "QED_DB_HOST": ("db_host", str),
    "QED_DB_PORT": ("db_port", int),
    "QED_DB_NAME": ("db_name", str),
    "QED_DB_USER": ("db_user", str),
    "QED_DB_PASSWORD": ("db_password", str),
    "QED_PROXY": ("proxy", str),
    "QED_TIMEOUT_SECONDS": ("timeout_seconds", float),
    "QED_RETRIES": ("retries", int),
    "QED_TLS_VERIFY": ("tls_verify", _bool),
    "QED_LLM_BASE_URL": ("llm_base_url", str),
}


def load_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {}
    for env_name, (field_name, converter) in _ENV_MAP.items():
        if env_name in os.environ:
            values[field_name] = converter(os.environ[env_name])
    if "QED_SOURCES" in os.environ:
        values["sources"] = tuple(item.strip() for item in os.environ["QED_SOURCES"].split(",") if item.strip())
    values.update({key: value for key, value in overrides.items() if value is not None})
    if "data_root" in values:
        values["data_root"] = Path(values["data_root"]).expanduser()
    settings = replace(Settings(), **values)
    data_root = settings.data_root
    if not data_root.is_absolute():
        data_root = (Path.cwd() / data_root).resolve()
    return replace(
        settings,
        data_root=data_root,
        axiom_url=settings.axiom_url.rstrip("/"),
        tracker_url=settings.tracker_url.rstrip("/"),
        llm_base_url=settings.llm_base_url.rstrip("/"),
    )


def llm_api_key() -> str:
    return os.getenv("QWEN_API_KEY") or ""


def degradation_notice(settings: Settings) -> str:
    """无根 `.env` 或缺密钥时的启动尾注提醒。"""
    missing = []
    if not settings.llm_configured:
        missing.append("QWEN_API_KEY（LLM 评估降级：catalog evaluate 跳过评估只落候选）")
    if not settings.db_configured:
        missing.append("QED_DB_PASSWORD（MySQL 登记降级：仅写 meta/resources/ JSON）")
    if not missing:
        return ""
    return "启动尾注：根 .env 缺少 " + "、".join(missing) + "；相关能力已降级，不阻塞主链路。"

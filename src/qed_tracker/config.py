"""统一配置：自身 `.env` → 根 `.env`（兜底）→ 内置默认值（QED-037，REQ-043）。

自身 `.env` 存于仓库根；根 `.env` 向上走查兜底。读取优先级：
真实环境变量 > 自身 `.env` > 根 `.env` > 内置最小默认值。
密钥（`API_KEY`、`QED_DB_PASSWORD`）只经环境读取，
不进入 `Settings` 的 repr。缺密钥时相关能力降级，不阻塞启动。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

DEFAULT_SOURCES = (
    "internet_archive",
    "open_library",
    "google_books",
    "libgen_li",  # QED-021：发现专用来源（metadata_only + 人工下载 links，无直链不落盘）
)

_DASH_SCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8900"
# .env 文件允许注入的键：QED_* + 唯一密钥变量 API_KEY（QED-038/ARCH-017：
# 逐厂商 key 别名全部取消，无回退；厂商选择由根仓库 QED_API_PROVIDER 决定）。
_ENV_KEYS = frozenset(("API_KEY",))


@dataclass(frozen=True, slots=True)
class Settings:
    data_root: Path = Path("dataset")
    proxy: str = ""
    timeout_seconds: float = 30.0
    retries: int = 3
    book_candidate_budget: float = 300.0  # QED-050：候选级预算（秒），取代 QED_FETCH_ATTEMPT_TIMEOUT（旧键一版别名后废弃）
    book_min_pages: int = 10  # 机器验收硬门槛：页数下限
    book_min_size_bytes: int = 204800  # 机器验收硬门槛：大小下限（200KB）
    book_search_limit: int = 8  # 每 query 每渠道候选上限
    book_query_variants: int = 3  # LLM 检索词变体上限（书级全局兜底一次）
    book_llm_query: bool = True  # LLM 检索词兜底开关（关闭时零候选直接人工指引）
    book_llm_confirm: bool = True  # LLM 确认开关（关闭时预筛通过即下载，匹配精度下降）
    book_llm_budget: int = 8  # 单次 fetch 的 LLM 调用预算
    sources: tuple[str, ...] = DEFAULT_SOURCES
    axiom_url: str = "http://127.0.0.1:8902"
    tls_verify: bool = True
    llm_model: str = "qwen-plus"
    llm_base_url: str = _DASH_SCOPE_BASE_URL
    llm_timeout_seconds: float = 300.0  # REQ-061：原 60s 硬顶致长生成 ReadTimeout，与根仓库默认对齐
    llm_call_budget: int = 6
    llm_max_tokens: int = 4096
    api_select: str = "local"  # local/api=直连 dashscope qwen；qed-engine=经 8900 网关（QED-037）
    llm_gateway_url: str = _DEFAULT_GATEWAY_URL  # qed-engine 模式网关地址（QED-037）
    port: int = 8901
    tracker_url: str = "http://127.0.0.1:8901"
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "qed"
    db_user: str = "root"
    db_password: str = ""

    @property
    def state_dir(self) -> Path:
        # ARCH-019 统一数据根：私有状态区固定 <data_root>/qed-tracker/meta（raw/tmp 为共享布局）。
        return self.data_root / "qed-tracker" / "meta"

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
    "QED_DATA_ROOT": ("data_root", str),
    "QED_DB_HOST": ("db_host", str),
    "QED_DB_PORT": ("db_port", int),
    "QED_DB_NAME": ("db_name", str),
    "QED_DB_USER": ("db_user", str),
    "QED_DB_PASSWORD": ("db_password", str),
    "QED_PROXY": ("proxy", str),
    "QED_TIMEOUT_SECONDS": ("timeout_seconds", float),
    "QED_RETRIES": ("retries", int),
    "QED_FETCH_ATTEMPT_TIMEOUT": ("book_candidate_budget", float),  # 旧键一版别名（新键设置时被其覆盖）
    "QED_BOOK_CANDIDATE_BUDGET": ("book_candidate_budget", float),
    "QED_BOOK_MIN_PAGES": ("book_min_pages", int),
    "QED_BOOK_MIN_SIZE_BYTES": ("book_min_size_bytes", int),
    "QED_BOOK_SEARCH_LIMIT": ("book_search_limit", int),
    "QED_BOOK_QUERY_VARIANTS": ("book_query_variants", int),
    "QED_BOOK_LLM_QUERY": ("book_llm_query", _bool),
    "QED_BOOK_LLM_CONFIRM": ("book_llm_confirm", _bool),
    "QED_BOOK_LLM_BUDGET": ("book_llm_budget", int),
    "QED_TLS_VERIFY": ("tls_verify", _bool),
    "QED_LLM_BASE_URL": ("llm_base_url", str),
    "QED_LLM_TIMEOUT": ("llm_timeout_seconds", float),  # REQ-061 同步：根仓库同键名，原 60s 硬顶致长生成 ReadTimeout
    "QED_API_SELECT": ("api_select", str),
    "QED_LLM_GATEWAY_URL": ("llm_gateway_url", str),
}


def strip_inline_comment(value: str) -> str:
    """剥离 `.env` 值的内联注释：`#` 前有空白（如 ` #`）才视为注释并截断；
    `#` 前无空白（如库名 `qed#x`、密码 `secret#pass`）保留，避免误伤真实值。"""
    return re.split(r"\s+#", value, maxsplit=1)[0].rstrip()


def _env_file_values(start: Path | None = None) -> dict[str, str]:
    """从 start 向上走查全部 `.env`，合并为视图（不修改 os.environ，避免测试环境污染）。

    先加载者（自身 .env）优先，根 `.env` 兜底；空值（如 `KEY=`）跳过留给兜底来源。
    键限 `QED_*` 与供应商密钥别名；已有环境变量优先于文件值（见 `_env_value`）。
    值支持内联注释剥离（`value # comment` → `value`，见 `strip_inline_comment`）。
    """
    values: dict[str, str] = {}
    start = start or Path.cwd()
    for candidate in (candidate / ".env" for candidate in (start, *start.parents)):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = strip_inline_comment(value.strip()).strip('"').strip("'")
            if not value:
                continue
            if key.startswith("QED_") or key in _ENV_KEYS:
                values.setdefault(key, value)
    return values


def _env_value(key: str) -> str:
    """单键取值：真实环境变量 > 自身 .env > 根 .env。"""
    return os.environ.get(key) or _env_file_values().get(key) or ""


def load_settings(**overrides: Any) -> Settings:
    file_values = _env_file_values()
    values: dict[str, Any] = {}
    for env_name, (field_name, converter) in _ENV_MAP.items():
        raw = os.environ.get(env_name) or file_values.get(env_name)
        if raw is not None:
            values[field_name] = converter(raw)
    if "QED_SOURCES" in os.environ:
        values["sources"] = tuple(item.strip() for item in os.environ["QED_SOURCES"].split(",") if item.strip())
    elif "QED_SOURCES" in file_values:
        values["sources"] = tuple(
            item.strip() for item in file_values["QED_SOURCES"].split(",") if item.strip()
        )
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
        llm_gateway_url=settings.llm_gateway_url.rstrip("/"),
    )


def llm_api_key() -> str:
    """唯一供应商密钥（QED-038/ARCH-017）：只读 `API_KEY`，逐厂商 key 别名无回退。"""
    return _env_value("API_KEY")


def degradation_notice(settings: Settings) -> str:
    """无 `.env` 或缺密钥时的启动尾注提醒。"""
    missing = []
    if not settings.llm_configured:
        missing.append("API_KEY（LLM 评估降级：catalog evaluate 跳过评估只落候选）")
    if not settings.db_configured:
        missing.append("QED_DB_PASSWORD（MySQL 必选：qt_tasks/qt_selections 需要数据库连接）")
    if not missing:
        return ""
    return "启动尾注：.env 缺少 " + "、".join(missing) + "；相关能力已降级，不阻塞主链路。"

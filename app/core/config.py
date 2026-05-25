import os
from pathlib import Path
from configparser import ConfigParser

from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings


def load_ini_config() -> dict:
    config = ConfigParser()
    ini_path = Path(__file__).parent.parent.parent / "setting.ini"
    if ini_path.exists():
        config.read(ini_path, encoding="utf-8")
    return config


class Settings(BaseSettings):
    base_path: str = Field(default=".")

    # === 数据集路径 ===
    dataset_dir: str = Field(default="dataset")
    textbook_dir: str = Field(default="")

    # === 数据库配置 (多引擎) ===
    db_engine: str = Field(default="mysql")
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=3306)
    db_name: str = Field(default="qed_tracker")
    db_user: str = Field(default="root")
    db_password: str = Field(default="")

    # === LLM 配置 ===
    local_llm_api_base: str = Field(default="http://127.0.0.1:5001/v1")
    local_llm_api_key: str = Field(default="lm-studio")
    local_llm_model: str = Field(default="qwen/qwen3.5-9b")

    # === Discovery 配置 ===
    search_keywords: list[str] = Field(
        default=["数学分析", "实变函数", "泛函分析", "复变函数", "偏微分方程"]
    )
    arxiv_math_domains: list[str] = Field(
        default=["math.CA", "math.FA", "math.AP", "math.CV"]
    )
    arxiv_llm_domains: list[str] = Field(
        default=["cs.LG", "cs.CL", "cs.CV", "cs.AI"]
    )

    # === GitHub 配置 ===
    github_token: str = Field(default="")

    # === API 配置 ===
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8001)

    # === 代理配置 ===
    http_proxy: str = Field(default="")

    # === 日志配置 ===
    log_level: str = Field(default="INFO")

    model_config = ConfigDict(env_prefix="QED_")

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent.parent

    @property
    def dataset_path(self) -> Path:
        path = Path(self.dataset_dir)
        if path.is_absolute():
            return path
        return self.project_root / path

    @property
    def textbook_path(self) -> Path:
        """教材下载专用路径，默认与 dataset_path 相同"""
        raw = self.textbook_dir or self.dataset_dir
        path = Path(raw)
        if path.is_absolute():
            return path
        return self.project_root / path

    @property
    def db_url(self) -> str:
        if self.db_engine == "mysql":
            return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


def load_settings_from_ini() -> Settings:
    config = load_ini_config()
    kwargs = {}

    if config.has_section("Core"):
        sec = config["Core"]
        if sec.get("dataset_dir"):
            kwargs["dataset_dir"] = sec.get("dataset_dir")
        if sec.get("textbook_dir"):
            kwargs["textbook_dir"] = sec.get("textbook_dir")
        if sec.get("log_level"):
            kwargs["log_level"] = sec.get("log_level")

    if config.has_section("Database"):
        sec = config["Database"]
        if sec.get("engine"):
            kwargs["db_engine"] = sec.get("engine")
        kwargs["db_host"] = sec.get("host", "localhost")
        kwargs["db_port"] = sec.getint("port", 3306)
        kwargs["db_name"] = sec.get("database", "qed_tracker")
        kwargs["db_user"] = sec.get("user", "root")
        kwargs["db_password"] = sec.get("password", "")

    if config.has_section("LLM"):
        sec = config["LLM"]
        kwargs["local_llm_api_base"] = sec.get("local_api_base", "http://127.0.0.1:5001/v1")
        kwargs["local_llm_api_key"] = sec.get("local_api_key", "lm-studio")
        kwargs["local_llm_model"] = sec.get("local_model", "qwen/qwen3.5-9b")

    if config.has_section("Discovery"):
        sec = config["Discovery"]
        kw_str = sec.get("search_keywords", "")
        if kw_str:
            kwargs["search_keywords"] = [k.strip() for k in kw_str.split(",") if k.strip()]
        domain_str = sec.get("arxiv_math_domains", "")
        if domain_str:
            kwargs["arxiv_math_domains"] = [d.strip() for d in domain_str.split(",") if d.strip()]
        llm_domain_str = sec.get("arxiv_llm_domains", "")
        if llm_domain_str:
            kwargs["arxiv_llm_domains"] = [d.strip() for d in llm_domain_str.split(",") if d.strip()]

    if config.has_section("Proxy") and config["Proxy"].get("http"):
        kwargs["http_proxy"] = config["Proxy"]["http"]

    if config.has_section("GitHub") and config["GitHub"].get("token"):
        kwargs["github_token"] = config["GitHub"]["token"]

    if config.has_section("API"):
        sec = config["API"]
        if sec.get("host"):
            kwargs["api_host"] = sec.get("host")
        if sec.get("port"):
            kwargs["api_port"] = sec.getint("port", 8001)

    return Settings(**kwargs)


settings = load_settings_from_ini()

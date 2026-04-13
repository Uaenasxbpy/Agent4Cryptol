"""统一配置管理，优先从 YAML 配置文件读取。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_project_path(
    value: Path | None,
    project_root: Path,
    default_relative_path: str,
) -> Path:
    if value is None:
        return project_root / default_relative_path
    return value if value.is_absolute() else project_root / value


class Settings(BaseModel):
    """全局设置类，优先从 YAML 文件读取。"""

    model_config = ConfigDict(extra="ignore")

    CONFIG_SOURCE: Path | None = None

    # === 项目路径 ===
    PROJECT_ROOT: Path = Field(default_factory=_default_project_root)
    RAG_DIR: Path | None = None
    PROMPT_DIR: Path | None = None
    LOGGER_DIR: Path | None = None
    CRYPTOL_OUTPUT_DIR: Path | None = None

    # === LLM 配置 ===
    LLM_MODEL: str = "qwen3.5-plus"
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_API_KEY_ENV: str = "DASHSCOPE_API_KEY"
    LLM_TIMEOUT: int = 120

    # === Cryptol 编译配置 ===
    CRYPTOL_CMD: str = "cryptol"
    COMPILE_TIMEOUT: int = 30

    # === 工作流配置 ===
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2

    # === RAG 检索配置 ===
    RAG_TOP_K_RULES: int = 8
    RAG_TOP_K_GUARDRAILS: int = 4
    RAG_TOP_K_PATTERNS: int = 5
    RAG_TOP_K_TEMPLATES: int = 3
    RAG_TOP_K_EXAMPLES: int = 5
    RAG_ENABLE_CACHE: bool = True

    # === 参数解析配置 ===
    ACTIVE_PARAMETER_SETS: dict[str, str] = Field(default_factory=dict)

    # === 日志配置 ===
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    LOG_MAX_BYTES: int = 2 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 3
    LOG_ENABLE_JSON: bool = False

    @model_validator(mode="after")
    def finalize_paths(self) -> "Settings":
        self.RAG_DIR = _resolve_project_path(self.RAG_DIR, self.PROJECT_ROOT, "RAG")
        self.PROMPT_DIR = _resolve_project_path(self.PROMPT_DIR, self.PROJECT_ROOT, "prompt")
        self.LOGGER_DIR = _resolve_project_path(self.LOGGER_DIR, self.PROJECT_ROOT, "logger")
        self.CRYPTOL_OUTPUT_DIR = _resolve_project_path(
            self.CRYPTOL_OUTPUT_DIR,
            self.PROJECT_ROOT,
            "Cryptol",
        )
        return self


def _candidate_config_paths(project_root: Path) -> list[Path]:
    return [
        project_root / "config.yaml",
        project_root / "config.yml",
        project_root / "config.example.yaml",
        project_root / "config.example.yml",
    ]


def _normalize_yaml_config(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)

    paths = data.get("paths", {})
    if isinstance(paths, dict):
        normalized.setdefault("RAG_DIR", paths.get("rag_dir"))
        normalized.setdefault("PROMPT_DIR", paths.get("prompt_dir"))
        normalized.setdefault("LOGGER_DIR", paths.get("logger_dir"))
        normalized.setdefault("CRYPTOL_OUTPUT_DIR", paths.get("cryptol_output_dir"))

    llm = data.get("llm", {})
    if isinstance(llm, dict):
        normalized.setdefault("LLM_MODEL", llm.get("model"))
        normalized.setdefault("LLM_BASE_URL", llm.get("base_url"))
        normalized.setdefault("LLM_API_KEY_ENV", llm.get("api_key_env"))
        normalized.setdefault("LLM_TIMEOUT", llm.get("timeout"))

    cryptol = data.get("cryptol", {})
    if isinstance(cryptol, dict):
        normalized.setdefault("CRYPTOL_CMD", cryptol.get("cmd"))
        normalized.setdefault("COMPILE_TIMEOUT", cryptol.get("compile_timeout"))

    workflow = data.get("workflow", {})
    if isinstance(workflow, dict):
        normalized.setdefault("MAX_RETRIES", workflow.get("max_retries"))
        normalized.setdefault("RETRY_DELAY", workflow.get("retry_delay"))

    rag = data.get("rag", {})
    if isinstance(rag, dict):
        normalized.setdefault("RAG_TOP_K_RULES", rag.get("top_k_rules"))
        normalized.setdefault("RAG_TOP_K_GUARDRAILS", rag.get("top_k_guardrails"))
        normalized.setdefault("RAG_TOP_K_PATTERNS", rag.get("top_k_patterns"))
        normalized.setdefault("RAG_TOP_K_TEMPLATES", rag.get("top_k_templates"))
        normalized.setdefault("RAG_TOP_K_EXAMPLES", rag.get("top_k_examples"))
        normalized.setdefault("RAG_ENABLE_CACHE", rag.get("enable_cache"))

    parameters = data.get("parameters", {})
    if isinstance(parameters, dict):
        normalized.setdefault("ACTIVE_PARAMETER_SETS", parameters.get("active_sets"))

    logging_config = data.get("logging", {})
    if isinstance(logging_config, dict):
        normalized.setdefault("LOG_LEVEL", logging_config.get("level"))
        normalized.setdefault("LOG_FORMAT", logging_config.get("format"))
        normalized.setdefault("LOG_MAX_BYTES", logging_config.get("max_bytes"))
        normalized.setdefault("LOG_BACKUP_COUNT", logging_config.get("backup_count"))
        normalized.setdefault("LOG_ENABLE_JSON", logging_config.get("enable_json"))

    return {key: value for key, value in normalized.items() if value is not None}


def _load_yaml_config(project_root: Path) -> tuple[dict[str, Any], Path | None]:
    for path in _candidate_config_paths(project_root):
        if not path.exists():
            continue

        with open(path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

        if not isinstance(data, dict):
            raise ValueError(f"配置文件必须是 YAML 对象：{path}")

        return _normalize_yaml_config(data), path

    return {}, None


def load_settings() -> Settings:
    project_root = _default_project_root()
    config_data, config_path = _load_yaml_config(project_root)
    config_data["PROJECT_ROOT"] = project_root
    if config_path is not None:
        config_data["CONFIG_SOURCE"] = config_path
    return Settings.model_validate(config_data)


settings = load_settings()

"""日志初始化工具，支持按函数目录和运行批次组织日志。"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from workflow.settings import settings


@dataclass
class RunLogContext:
    """当前工作流运行对应的日志路径上下文。"""

    function_name: str
    function_log_dir: Path
    prompt_log_dir: Path
    run_label: str
    workflow_log_path: Path
    error_log_path: Path


_CURRENT_RUN_LOG_CONTEXT: RunLogContext | None = None


def _build_handler(path: Path, level: int) -> RotatingFileHandler:
    """创建带滚动策略的文件处理器。"""
    handler = RotatingFileHandler(
        path,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    return handler


def _build_console_handler(level: int) -> logging.StreamHandler:
    """创建输出到终端的日志处理器。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    return handler


def _sanitize_file_name(name: str) -> str:
    """清理日志文件名中的非法字符。"""
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return sanitized or "unknown"


def _extract_log_group(json_path: Path) -> str:
    """从输入路径中提取日志分组目录，例如 FIPS203 -> fips203。"""
    for part in json_path.parts:
        if re.fullmatch(r"FIPS\d+", part, re.IGNORECASE):
            return part.lower()
    return "misc"


def _extract_function_name(json_path: Path) -> str:
    """从函数 JSON 中提取函数名，失败时回退到文件名。"""
    try:
        with open(json_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        raw_name = str(data.get("name", "")).strip()
    except Exception:
        raw_name = ""

    return _sanitize_file_name(raw_name or json_path.stem)


def _build_run_log_context(json_file_path: str) -> RunLogContext:
    """根据输入 JSON 路径构造当前运行的日志路径。"""
    json_path = Path(json_file_path).resolve()
    log_group = _extract_log_group(json_path)
    function_name = _extract_function_name(json_path)
    function_log_dir = settings.LOGGER_DIR / log_group / function_name
    prompt_log_dir = function_log_dir / "fix_prompts"
    run_label = datetime.now().strftime("%Y%m%d_%H%M%S")

    return RunLogContext(
        function_name=function_name,
        function_log_dir=function_log_dir,
        prompt_log_dir=prompt_log_dir,
        run_label=run_label,
        workflow_log_path=function_log_dir / f"{run_label}.workflow.log",
        error_log_path=function_log_dir / f"{run_label}.error.log",
    )


def _close_logger_handlers(logger: logging.Logger) -> None:
    """移除并关闭 logger 上已有的处理器。"""
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def setup_logging(json_file_path: str, log_level: str | None = None) -> None:
    """初始化当前函数运行的日志，支持动态日志级别。"""
    global _CURRENT_RUN_LOG_CONTEXT

    _level = log_level or settings.LOG_LEVEL
    numeric_level = getattr(logging, _level.upper(), logging.INFO)
    context = _build_run_log_context(json_file_path)

    context.function_log_dir.mkdir(parents=True, exist_ok=True)
    context.prompt_log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    _close_logger_handlers(root_logger)
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(_build_console_handler(numeric_level))
    root_logger.addHandler(_build_handler(context.workflow_log_path, numeric_level))
    root_logger.addHandler(_build_handler(context.error_log_path, logging.ERROR))

    _CURRENT_RUN_LOG_CONTEXT = context


def write_fix_prompt_log(retry_count: int, function_name: str, prompt_text: str) -> Path | None:
    """为每一轮修复单独落一份 prompt 日志。"""
    context = _CURRENT_RUN_LOG_CONTEXT
    if context is None:
        return None

    context.prompt_log_dir.mkdir(parents=True, exist_ok=True)
    path = context.prompt_log_dir / f"{context.run_label}.retry_{retry_count:02d}.fix_prompt.log"
    content = (
        f"[fix_prompt_start] run={context.run_label} retry={retry_count} function={function_name}\n"
        f"{prompt_text}\n"
        f"[fix_prompt_end]\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def finalize_logging(version: int) -> dict[str, Path]:
    """在工作流结束后关闭处理器，并返回本次运行的日志路径。"""
    del version
    global _CURRENT_RUN_LOG_CONTEXT

    context = _CURRENT_RUN_LOG_CONTEXT
    if context is None:
        return {}

    root_logger = logging.getLogger()
    _close_logger_handlers(root_logger)

    archived_paths = {
        "workflow": context.workflow_log_path,
        "error": context.error_log_path,
        "fix_prompt_dir": context.prompt_log_dir,
    }

    _CURRENT_RUN_LOG_CONTEXT = None
    return archived_paths
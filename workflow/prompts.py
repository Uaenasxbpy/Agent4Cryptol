"""提示词模板读取与代码块提取工具。"""

from __future__ import annotations

import difflib
import json
import logging
import re
from functools import lru_cache
from string import Template

from workflow.logging_utils import write_fix_prompt_log
from workflow.settings import settings
from workflow.state import RepairAttempt


logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _load_template(name: str) -> Template:
    """读取文本模板并缓存。"""
    path = settings.PROMPT_DIR / name
    with open(path, "r", encoding="utf-8") as file:
        return Template(file.read())


TRANSLATION_SYSTEM_PROMPT = _load_template("translation_system.txt").template
FIX_SYSTEM_PROMPT = _load_template("fix_system.txt").template
TRANSLATION_PROMPT_TEMPLATE = _load_template("translation_user.txt")
FIX_PROMPT_TEMPLATE = _load_template("fix_user.txt")
FIX_FOLLOWUP_TEMPLATE = _load_template("fix_followup.txt")


def load_system_prompt(filename: str) -> str:
    """按文件名加载系统提示词，支持消融实验替换提示词变体。"""
    return _load_template(filename).template


def _build_algorithm_json(function_data: dict) -> str:
    """构造提示词中使用的当前函数 JSON 文本。"""
    payload = {
        "function_id": function_data.get("function_id"),
        "name": function_data.get("name"),
        "label": function_data.get("label"),
        "page_start": function_data.get("page_start"),
        "page_end": function_data.get("page_end"),
        "inputs": function_data.get("inputs", []),
        "outputs": function_data.get("outputs", []),
        "body_raw": function_data.get("body_raw", []),
    }

    if "layer" in function_data:
        payload["layer"] = function_data.get("layer")
    if "dependencies" in function_data:
        payload["dependencies"] = function_data.get("dependencies", {})
    if "parameter_resolution" in function_data:
        payload["parameter_resolution"] = function_data.get("parameter_resolution", {})

    return json.dumps(payload, indent=2, ensure_ascii=False)


def _extract_error_line(compile_error: str) -> int | None:
    """从编译错误文本中提取首个行号。"""
    match = re.search(r":(\d+):\d+(?:--\d+:\d+)?", compile_error)
    if match:
        return int(match.group(1))
    return None


def _format_code_excerpt(code: str, line_number: int | None, radius: int = 2) -> str:
    """截取错误附近的代码片段并附上行号。"""
    lines = code.splitlines()
    if not lines:
        return "<empty code>"

    if line_number is None:
        selected = lines[: min(len(lines), 8)]
        start = 1
    else:
        start = max(1, line_number - radius)
        end = min(len(lines), line_number + radius)
        selected = lines[start - 1:end]

    return "\n".join(f"{start + index:>4}: {line}" for index, line in enumerate(selected))


def _summarize_top_level(code: str, limit: int = 6) -> str:
    """提取模块名和若干顶层签名，帮助模型快速定位上下文。"""
    lines = code.splitlines()
    summary_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("module "):
            summary_lines.append(stripped)
            break

    for line in lines:
        stripped = line.strip()
        if not stripped or line.startswith((" ", "\t")):
            continue
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        if stripped.startswith("module "):
            continue
        if ":" in stripped or "=" in stripped:
            summary_lines.append(stripped)
        if len(summary_lines) >= limit + 1:
            break

    return "\n".join(summary_lines[: limit + 1]) or "<no top-level summary>"


def summarize_current_code(cryptol_code: str, compile_error: str) -> str:
    """生成当前失败代码的摘要。"""
    error_line = _extract_error_line(compile_error)
    parts = [
        "Top-level overview:",
        _summarize_top_level(cryptol_code),
        "",
        "Error location excerpt:",
        _format_code_excerpt(cryptol_code, error_line),
    ]
    return "\n".join(parts).strip()


def _normalize_for_change_detection(text: str) -> str:
    """粗略归一化文本，用于识别括号/空白级别的微小修改。"""
    return re.sub(r"[\s()]", "", text)


def summarize_code_changes(old_code: str, new_code: str, max_lines: int = 8) -> str:
    """总结本轮修复对代码做了哪些文本修改。"""
    if old_code == new_code:
        return "No textual changes were made."

    if _normalize_for_change_detection(old_code) == _normalize_for_change_detection(new_code):
        return "Only whitespace or parentheses changed; no deeper semantic edit is visible."

    diff_lines = list(
        difflib.unified_diff(
            old_code.splitlines(),
            new_code.splitlines(),
            fromfile="previous",
            tofile="current",
            lineterm="",
            n=0,
        )
    )

    changes = [
        line for line in diff_lines
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]

    if not changes:
        return "Changes were made, but no concise diff summary is available."

    trimmed = changes[:max_lines]
    if len(changes) > max_lines:
        trimmed.append("...")
    return "\n".join(trimmed)


def _condense_error_text(error_text: str, max_lines: int = 3) -> str:
    """压缩错误文本，避免历史区块过长。"""
    lines = [line.rstrip() for line in error_text.splitlines() if line.strip()]
    if not lines:
        return "<empty error>"
    trimmed = lines[:max_lines]
    if len(lines) > max_lines:
        trimmed.append("...")
    return "\n".join(trimmed)


def format_repair_history(repair_history: list[RepairAttempt], limit: int = 3) -> str:
    """将最近几轮修复历史格式化为 prompt 文本。"""
    if not repair_history:
        return "No previous repair attempts."

    recent_attempts = repair_history[-limit:]
    blocks = []
    for attempt in recent_attempts:
        blocks.append(
            "\n".join(
                [
                    f"Attempt {attempt['retry_count']}:",
                    "Compiler error handled in that attempt:",
                    _condense_error_text(attempt["source_compile_error"]),
                    "Attempted modification summary:",
                    attempt["attempted_change_summary"],
                ]
            )
        )
    return "\n\n".join(blocks)


def build_translation_prompt(
    function_data: dict,
    rag_context: str,
    json_file_path: str | None = None,
    dependency_context: str = "",
) -> str:
    """构造首次翻译时的用户提示词。"""
    return TRANSLATION_PROMPT_TEMPLATE.substitute(
        function_id=function_data.get("function_id", ""),
        label=function_data.get("label", ""),
        function_name=function_data.get("name", ""),
        algorithm_json=_build_algorithm_json(function_data),
        dependency_context=dependency_context or "// 无外部依赖（layer 0 函数）",
        rag_context=rag_context,
    )


def build_fix_prompt(
    function_data: dict,
    cryptol_code: str,
    compile_error: str,
    compile_output: str,
    retry_count: int,
    repair_history: list[RepairAttempt],
    json_file_path: str | None = None,
    rag_context: str = "",
    dependency_context: str = "",
) -> str:
    """构造编译失败后的修复提示词，并写入每轮独立日志文件。"""
    prompt_text = FIX_PROMPT_TEMPLATE.substitute(
        retry_count=retry_count,
        compile_error=compile_error,
        compile_output=compile_output,
        current_code_summary=summarize_current_code(cryptol_code, compile_error),
        cryptol_code=cryptol_code,
        repair_history=format_repair_history(repair_history),
        algorithm_json=_build_algorithm_json(function_data),
        dependency_context=dependency_context or "// 无外部依赖",
        rag_context=rag_context or "No RAG snippets available.",
    )

    logger.info("已生成第 %s 次修复提示词", retry_count)
    path = write_fix_prompt_log(
        retry_count=retry_count,
        function_name=function_data.get("name", ""),
        prompt_text=prompt_text,
    )
    if path is not None:
        logger.info("已写入修复提示词日志：%s", path)
    return prompt_text


def build_fix_followup_prompt(
    cryptol_code: str,
    compile_error: str,
    compile_output: str,
    retry_count: int,
) -> str:
    """构造多轮修复中后续轮次的追问提示词。"""
    return FIX_FOLLOWUP_TEMPLATE.substitute(
        retry_count=retry_count,
        compile_error=compile_error,
        compile_output=compile_output,
        cryptol_code=cryptol_code,
    )


def extract_code_block(text: str) -> str:
    """提取第一个 fenced code block 中的 Cryptol 代码。"""
    match = re.search(r"```cryptol\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return text.strip()

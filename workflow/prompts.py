"""提示词模板读取与代码块提取工具。"""

from __future__ import annotations

import difflib
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from string import Template

from workflow.config import PROMPT_DIR
from workflow.logging_utils import write_fix_prompt_log
from workflow.settings import settings
from workflow.state import RepairAttempt


logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _load_template(name: str) -> Template:
    """读取文本模板并缓存。"""
    path = PROMPT_DIR / name
    with open(path, "r", encoding="utf-8") as file:
        return Template(file.read())


TRANSLATION_SYSTEM_PROMPT = _load_template("translation_system.txt").template
FIX_SYSTEM_PROMPT = _load_template("fix_system.txt").template
TRANSLATION_PROMPT_TEMPLATE = _load_template("translation_user.txt")
FIX_PROMPT_TEMPLATE = _load_template("fix_user.txt")
FIX_FOLLOWUP_TEMPLATE = _load_template("fix_followup.txt")


def _build_algorithm_json(function_data: dict) -> str:
    """构造提示词中使用的算法 JSON 文本。"""
    return json.dumps(
        {
            "name": function_data.get("name"),
            "inputs": function_data.get("inputs", []),
            "outputs": function_data.get("outputs", []),
            "body_raw": function_data.get("body_raw", []),
        },
        indent=2,
        ensure_ascii=False,
    )


@lru_cache(maxsize=None)
def _load_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=None)
def _load_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file:
        return file.read().strip()


def _extract_spec_id(json_file_path: str | None) -> str | None:
    if not json_file_path:
        return None

    json_path = Path(json_file_path).resolve()
    for part in json_path.parts:
        if re.fullmatch(r"FIPS\d+", part, re.IGNORECASE):
            return part.upper()
    return None


def _resolve_parameter_root(json_file_path: str | None) -> Path | None:
    spec_id = _extract_spec_id(json_file_path)
    if spec_id is None or json_file_path is None:
        return None

    json_path = Path(json_file_path).resolve()
    candidate = json_path.parents[2] / "source" / f"{spec_id.lower()}_parameter"
    return candidate if candidate.exists() else None


def _get_active_parameter_set(spec_id: str | None) -> str | None:
    if spec_id is None:
        return None
    return settings.ACTIVE_PARAMETER_SETS.get(spec_id)


def _collect_known_parameter_symbols(
    global_parameters: dict,
    parameter_sets: dict,
    resolution_notes: dict,
) -> set[str]:
    symbols: set[str] = set()

    for item in global_parameters.get("global_constants", []):
        name = str(item.get("name", "")).strip().lower()
        if name:
            symbols.add(name)

    for item in global_parameters.get("parameter_variables", []):
        name = str(item.get("name", "")).strip().lower()
        if name:
            symbols.add(name)

    for parameter_set in parameter_sets.get("parameter_sets", []):
        for parameter in parameter_set.get("parameters", []):
            name = str(parameter.get("name", "")).strip().lower()
            if name:
                symbols.add(name)

    return symbols


def _extract_relevant_parameter_symbols(
    function_data: dict,
    known_symbols: set[str],
) -> list[str]:
    text_chunks = [
        str(function_data.get("name", "")),
        " ".join(str(line) for line in function_data.get("body_raw", [])),
        json.dumps(function_data.get("inputs", []), ensure_ascii=False),
        json.dumps(function_data.get("outputs", []), ensure_ascii=False),
    ]
    text = " ".join(text_chunks)
    lowered_text = text.lower()

    func_name = str(function_data.get("name", ""))
    name_tokens = {t.lower() for t in func_name.split("_") if t}

    found_symbols: set[str] = set()

    for symbol in known_symbols:
        if re.search(rf"\b{re.escape(symbol)}\b", lowered_text):
            found_symbols.add(symbol)
        elif symbol in name_tokens:
            found_symbols.add(symbol)

    expanded: set[str] = set()
    for symbol in found_symbols:
        for candidate in known_symbols:
            if candidate != symbol and candidate.startswith(symbol):
                expanded.add(candidate)
    found_symbols |= expanded

    return sorted(found_symbols)


def _build_parameter_context(function_data: dict, json_file_path: str | None) -> str:
    """Build parameter reference plus raw JSON payload for the active FIPS document."""
    parameter_root = _resolve_parameter_root(json_file_path)
    spec_id = _extract_spec_id(json_file_path)
    if parameter_root is None or spec_id is None:
        return ""
    active_parameter_set = _get_active_parameter_set(spec_id)

    parameter_sets_path = parameter_root / "parameter_sets.json"
    global_parameters_path = parameter_root / "global_parameters.json"
    resolution_notes_path = parameter_root / "parameter_resolution_notes.json"

    if not (
        parameter_sets_path.exists()
        and global_parameters_path.exists()
        and resolution_notes_path.exists()
    ):
        return ""

    parameter_sets = _load_json_file(str(parameter_sets_path))
    global_parameters = _load_json_file(str(global_parameters_path))
    resolution_notes = _load_json_file(str(resolution_notes_path))
    known_symbols = _collect_known_parameter_symbols(
        global_parameters,
        parameter_sets,
        resolution_notes,
    )
    relevant_symbols = _extract_relevant_parameter_symbols(function_data, known_symbols)

    lines = [
        f"Document: {spec_id}",
        f"Parameter directory: {parameter_root}",
        f"Configured active parameter set: {active_parameter_set or 'NONE'}",
        "- Use explicit function inputs first.",
        "- If a symbol is not an explicit input, prefer documented global constants.",
        "- Use parameter-set values from the configured active parameter set when it is provided.",
        "- If no active parameter set is configured, keep parameter-set-dependent symbols symbolic unless the source data uniquely determines a concrete value.",
    ]

    if relevant_symbols:
        lines.append(f"- Relevant symbols detected from this function: {', '.join(relevant_symbols)}")

    rules = resolution_notes.get("parameter_resolution_rules", [])
    if rules:
        lines.append("")
        lines.append("Resolution rules from source data:")
        for rule in sorted(rules, key=lambda item: item.get("priority", 999)):
            lines.append(f"- P{rule.get('priority', '?')}: {rule.get('rule', '')}")

    matched_globals = [
        item
        for item in global_parameters.get("global_constants", [])
        if not relevant_symbols or str(item.get("name", "")).lower() in relevant_symbols
    ]
    if matched_globals:
        lines.append("")
        lines.append("Relevant global constants:")
        for item in matched_globals:
            lines.append(
                f"- {item.get('name')} = {item.get('value')} ({item.get('description', '')})"
            )

    matched_variables = [
        item
        for item in global_parameters.get("parameter_variables", [])
        if not relevant_symbols or str(item.get("name", "")).lower() in relevant_symbols
    ]
    if matched_variables:
        lines.append("")
        lines.append("Relevant parameter variables:")
        for item in matched_variables:
            lines.append(f"- {item.get('name')}: {item.get('description', '')}")

    matched_set_lines: list[str] = []
    for parameter_set in parameter_sets.get("parameter_sets", []):
        set_name = str(parameter_set.get("set_name", ""))
        if active_parameter_set and set_name != active_parameter_set:
            continue

        relevant_entries = [
            parameter
            for parameter in parameter_set.get("parameters", [])
            if not relevant_symbols or str(parameter.get("name", "")).lower() in relevant_symbols
        ]
        if relevant_entries:
            matched_set_lines.append(
                "- "
                + set_name
                + ": "
                + ", ".join(
                    f"{entry.get('name')}={entry.get('value')}" for entry in relevant_entries
                )
            )
    if matched_set_lines:
        lines.append("")
        lines.append(
            "Relevant parameter-set values:"
            if not active_parameter_set
            else f"Relevant parameter-set values from active set {active_parameter_set}:"
        )
        lines.extend(matched_set_lines)

    matched_examples = [
        item
        for item in resolution_notes.get("examples", [])
        if str(item.get("function_like_symbol", "")).lower() in function_data.get("name", "").lower()
        or any(
            re.search(rf"\b{re.escape(symbol)}\b", str(item.get("resolution", "")).lower())
            for symbol in relevant_symbols
        )
    ]
    if matched_examples:
        lines.append("")
        lines.append("Relevant resolution notes:")
        for item in matched_examples:
            lines.append(
                f"- {item.get('function_like_symbol')}: {item.get('resolution', '')}"
            )

    raw_global_parameters = _load_text_file(str(global_parameters_path))
    raw_resolution_notes = _load_text_file(str(resolution_notes_path))

    if active_parameter_set:
        active_set_data = [
            ps for ps in parameter_sets.get("parameter_sets", [])
            if ps.get("set_name") == active_parameter_set
        ]
        raw_parameter_sets = json.dumps(
            {"parameter_sets": active_set_data}, indent=2, ensure_ascii=False,
        )
    else:
        raw_parameter_sets = _load_text_file(str(parameter_sets_path))

    lines.extend(
        [
            "",
            "Authoritative raw parameter JSON:",
            "global_parameters.json",
            "```json",
            raw_global_parameters,
            "```",
            "",
            f"parameter_sets.json (active set: {active_parameter_set or 'ALL'})",
            "```json",
            raw_parameter_sets,
            "```",
            "",
            "parameter_resolution_notes.json",
            "```json",
            raw_resolution_notes,
            "```",
        ]
    )

    return "\n".join(lines)


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
) -> str:
    """构造首次翻译时的用户提示词。"""
    return TRANSLATION_PROMPT_TEMPLATE.substitute(
        function_id=function_data.get("function_id", ""),
        label=function_data.get("label", ""),
        function_name=function_data.get("name", ""),
        algorithm_json=_build_algorithm_json(function_data),
        parameter_context=_build_parameter_context(function_data, json_file_path),
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
        parameter_context=_build_parameter_context(function_data, json_file_path),
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

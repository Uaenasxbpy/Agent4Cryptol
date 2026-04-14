"""多轮对话 Fix Agent：在同一对话上下文中迭代修复编译错误。

核心思路：
- 第1轮：构建完整的 [System, User] 消息（含代码、错误、RAG 上下文）
- 第2轮起：在已有对话上追加 [Assistant(上轮回复), User(新编译错误)]
- 模型能看到自己之前的所有尝试和每次的编译反馈，避免重复无效修复
"""

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from workflow.model import get_model
from workflow.prompts import (
    FIX_SYSTEM_PROMPT,
    build_fix_prompt,
    build_fix_followup_prompt,
    extract_code_block,
    load_system_prompt,
)
from workflow.rag import retrieve_rag_for_fix
from workflow.dependency_resolver import load_dependencies

logger = logging.getLogger(__name__)


def _normalize_response_text(content: object) -> str:
    """将模型返回内容统一折叠为字符串。"""
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue

            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(part.strip() for part in parts if isinstance(part, str) and part.strip())

    return str(content or "").strip()


def _looks_like_cryptol_source(text: str) -> bool:
    """粗略判断文本是否像一段可保存的 Cryptol 源码。"""
    stripped = text.strip()
    if not stripped:
        return False

    return bool(
        re.search(r"\bmodule\s+[A-Za-z_][A-Za-z0-9_']*\s+where\b", stripped)
        or re.search(r"^[A-Za-z_][A-Za-z0-9_']*\s*:", stripped, re.MULTILINE)
        or re.search(r"^[A-Za-z_][A-Za-z0-9_']*.*=", stripped, re.MULTILINE)
    )


def _validate_and_extract(raw_response: str, fallback_code: str, func_name: str, retry_count: int) -> str:
    """从模型回复中提取代码，无效则返回 fallback。"""
    fixed_code = extract_code_block(raw_response)

    if not fixed_code.strip():
        logger.error(
            "fix_agent 未返回可保存代码，保留上一版：function=%s retry=%s",
            func_name, retry_count,
        )
        return fallback_code

    if "```" not in raw_response and not _looks_like_cryptol_source(fixed_code):
        logger.error(
            "fix_agent 返回内容不像 Cryptol 源码，保留上一版：function=%s retry=%s",
            func_name, retry_count,
        )
        return fallback_code

    return fixed_code


def run_fix_agent(
    function_data: dict,
    cryptol_code: str,
    compile_error: str,
    compile_output: str,
    retry_count: int,
    fix_messages: list[Any],
    json_file_path: str | None = None,
    experiment_config: dict | None = None,
) -> tuple[str, list[Any]]:
    """执行一次修复，返回 (修复后的代码, 更新后的消息历史)。

    多轮对话逻辑：
    - fix_messages 为空 → 第一轮修复，构建完整的初始 prompt
    - fix_messages 非空 → 后续轮次，追加上轮 AI 回复 + 新的编译错误

    消融实验控制（通过 experiment_config）：
    - enable_fix_rag: False 时跳过错误感知 RAG，使用空上下文
    - enable_repair_history: False 时每轮重置消息历史（无多轮对话记忆）
    - fix_system_prompt: 指定不同系统提示词文件名
    """
    exp_config = experiment_config or {}
    enable_fix_rag = exp_config.get("enable_fix_rag", True)
    enable_history = exp_config.get("enable_repair_history", True)
    fix_prompt_file = exp_config.get("fix_system_prompt")

    func_name = function_data.get("name", "unknown")
    logger.info(
        "fix_agent 开始：function=%s retry=%s 对话轮次=%s",
        func_name, retry_count,
        "首轮" if not fix_messages else f"第{retry_count}轮(累积{len(fix_messages)}条消息)",
    )

    model = get_model()
    system_prompt = load_system_prompt(fix_prompt_file) if fix_prompt_file else FIX_SYSTEM_PROMPT

    # enable_repair_history=False：每轮都视为"首轮"，重置消息历史
    effective_messages = fix_messages if enable_history else []

    if not effective_messages:
        # ---- 第一轮（或禁用历史时每轮）：构建完整的初始对话 ----
        if enable_fix_rag:
            rag_context = retrieve_rag_for_fix(compile_error, function_data)
            logger.info(
                "fix_agent RAG 检索完成：function=%s context_length=%s",
                func_name, len(rag_context),
            )
        else:
            rag_context = ""
            logger.info("fix_agent RAG 检索已禁用（消融实验）：function=%s", func_name)

        dependency_context = load_dependencies(
            function_data,
            json_file_path or "",
            experiment_name=exp_config.get("experiment_name", ""),
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=build_fix_prompt(
                    function_data=function_data,
                    cryptol_code=cryptol_code,
                    compile_error=compile_error,
                    compile_output=compile_output,
                    retry_count=retry_count,
                    repair_history=[],
                    json_file_path=json_file_path,
                    rag_context=rag_context,
                    dependency_context=dependency_context,
                )
            ),
        ]
    else:
        # ---- 后续轮次：在已有对话上追加 ----
        messages = list(effective_messages)

        # 追加上一轮的编译反馈
        followup_content = build_fix_followup_prompt(
            cryptol_code=cryptol_code,
            compile_error=compile_error,
            compile_output=compile_output,
            retry_count=retry_count,
        )
        messages.append(HumanMessage(content=followup_content))

    # ---- 调用模型 ----
    response = model.invoke(messages)
    raw_response = _normalize_response_text(response.content)
    fixed_code = _validate_and_extract(raw_response, cryptol_code, func_name, retry_count)

    # ---- 将本轮对话追加到消息历史 ----
    # 保存模型的回复，下一轮调用时它能看到自己之前的输出
    updated_messages = list(messages) + [AIMessage(content=raw_response)]

    logger.info(
        "fix_agent 完成：function=%s retry=%s code_length=%s 消息总数=%s",
        func_name, retry_count, len(fixed_code), len(updated_messages),
    )
    return fixed_code, updated_messages

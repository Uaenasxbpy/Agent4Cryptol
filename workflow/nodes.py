"""LangGraph 节点实现。"""

import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from workflow.cryptol_compiler import compile_cryptol_code
from workflow.dependency_resolver import load_dependencies
from workflow.fix_agent import run_fix_agent
from workflow.function_utils import FunctionInfo
from workflow.model import get_model
from workflow.prompts import (
    TRANSLATION_SYSTEM_PROMPT,
    build_translation_prompt,
    extract_code_block,
    load_system_prompt,
    summarize_code_changes,
)
from workflow.rag import retrieve_rag_context
from workflow.settings import settings
from workflow.state import WorkflowState


logger = logging.getLogger(__name__)


def _get_function_info(state: WorkflowState) -> FunctionInfo:
    """构造带输入路径上下文的函数信息对象。"""
    function_data = dict(state["function_data"])
    experiment_name = state.get("experiment_config", {}).get("experiment_name", "")
    if experiment_name:
        function_data["__experiment_name__"] = experiment_name
    return FunctionInfo(function_data, state["json_file_path"])


def node_load_json(state: WorkflowState) -> dict:
    """节点 1：从磁盘读取函数 JSON。"""
    path = Path(state["json_file_path"])
    logger.info("读取函数 JSON：%s", path)
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return {"function_data": data}


def node_rag_retrieval(state: WorkflowState) -> dict:
    """节点 2：根据函数内容检索翻译阶段 RAG 上下文。
    若 experiment_config.enable_gen_rag 为 False，跳过检索，返回空上下文。
    """
    exp_config = state.get("experiment_config", {})
    if not exp_config.get("enable_gen_rag", True):
        logger.info("RAG 检索已禁用（消融实验）：function=%s", state["function_data"].get("name", "?"))
        return {"rag_context": ""}

    function_data = state["function_data"]
    func_info = _get_function_info(state)
    logger.info("开始检索 RAG 上下文：function=%s", func_info.name)

    top_k_override = exp_config.get("rag_top_k_override", {})
    context = retrieve_rag_context(
        function_data,
        top_k_guardrails=top_k_override.get("guardrails"),
        top_k_patterns=top_k_override.get("patterns"),
        top_k_templates=top_k_override.get("templates"),
        top_k_rules=top_k_override.get("rules"),
        top_k_examples=top_k_override.get("examples"),
    )
    logger.info("RAG 检索完成：function=%s context_length=%s", func_info.name, len(context))
    return {"rag_context": context}


def node_translate(state: WorkflowState) -> dict:
    """节点 3：首次调用模型，将 JSON 翻译为 Cryptol。
    系统提示词文件名可由 experiment_config.translation_system_prompt 覆盖。
    """
    function_data = state["function_data"]
    func_info = _get_function_info(state)
    logger.info("开始首次翻译：function=%s", func_info.name)

    exp_config = state.get("experiment_config", {})
    system_prompt_file = exp_config.get("translation_system_prompt")
    system_prompt = load_system_prompt(system_prompt_file) if system_prompt_file else TRANSLATION_SYSTEM_PROMPT

    model = get_model()
    dependency_context = load_dependencies(
        function_data,
        state["json_file_path"],
        experiment_name=exp_config.get("experiment_name", ""),
    )
    if dependency_context:
        logger.info("已加载依赖上下文：function=%s dep_length=%s", func_info.name, len(dependency_context))
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=build_translation_prompt(
                function_data,
                state["rag_context"],
                state["json_file_path"],
                dependency_context=dependency_context,
            )
        ),
    ]
    response = model.invoke(messages)
    code = extract_code_block(response.content)
    func_info.save_snapshot(code, "v0")
    logger.info("首次翻译完成：function=%s code_length=%s", func_info.name, len(code))
    return {"cryptol_code": code, "retry_count": 0, "repair_history": [], "fix_messages": []}


def node_compile(state: WorkflowState) -> dict:
    """节点 4：直接调用本地 Cryptol 编译器编译代码。
    将 spec 输出目录（如 Cryptol/fips203/）加入 CRYPTOLPATH，使依赖模块可被找到。
    """
    func_info = _get_function_info(state)
    attempt = state.get("retry_count", 0)
    logger.info("开始编译：function=%s attempt=%s", func_info.name, attempt + 1)

    # 依赖搜索路径：spec 专属输出目录（已生成的 .cry 文件所在位置）
    search_paths = []
    if func_info.group:
        dep_dir = settings.CRYPTOL_OUTPUT_DIR / func_info.group
        if func_info.experiment_name:
            dep_dir = dep_dir / func_info.experiment_name
        if dep_dir.exists():
            search_paths.append(dep_dir)

    try:
        success, compile_text, info_text, warning_text, error_text = compile_cryptol_code(
            cryptol_code=state["cryptol_code"],
            search_paths=search_paths or None,
        )

        if success:
            logger.info("编译成功：function=%s attempt=%s", func_info.name, attempt + 1)
            if warning_text.strip():
                logger.warning(
                    "编译成功但存在警告：function=%s attempt=%s warning=%s",
                    func_info.name,
                    attempt + 1,
                    warning_text[:300],
                )
        else:
            logger.warning(
                "编译失败：function=%s attempt=%s error=%s",
                func_info.name,
                attempt + 1,
                error_text[:300],
            )

        return {
            "compile_success": success,
            "compile_error": error_text,
            "compile_output": compile_text,
        }

    except RuntimeError as e:
        logger.error("编译异常：function=%s attempt=%s error=%s", func_info.name, attempt + 1, str(e))
        return {
            "compile_success": False,
            "compile_error": str(e),
            "compile_output": "",
        }
    except Exception as exc:
        logger.error("编译未预期错误：function=%s attempt=%s error=%s", func_info.name, attempt + 1, str(exc))
        return {
            "compile_success": False,
            "compile_error": f"编译异常：{str(exc)}",
            "compile_output": "",
        }


def node_fix(state: WorkflowState) -> dict:
    """节点 5：多轮对话修复——在同一对话上下文中迭代修复编译错误。"""
    retry_count = state.get("retry_count", 0) + 1
    func_info = _get_function_info(state)
    current_code = state["cryptol_code"]
    repair_history = list(state.get("repair_history", []))
    fix_messages = list(state.get("fix_messages", []))
    logger.info("开始修复：function=%s retry=%s 消息历史=%s条", func_info.name, retry_count, len(fix_messages))

    code, updated_messages = run_fix_agent(
        function_data=state["function_data"],
        cryptol_code=current_code,
        compile_error=state["compile_error"],
        compile_output=state["compile_output"],
        retry_count=retry_count,
        fix_messages=fix_messages,
        json_file_path=state["json_file_path"],
        experiment_config=state.get("experiment_config", {}),
    )

    updated_history = repair_history + [
        {
            "retry_count": retry_count,
            "source_compile_error": state["compile_error"],
            "attempted_change_summary": summarize_code_changes(current_code, code),
        }
    ]

    func_info.save_snapshot(code, f"v{retry_count}")
    logger.info("修复完成：function=%s retry=%s code_length=%s", func_info.name, retry_count, len(code))
    return {
        "cryptol_code": code,
        "retry_count": retry_count,
        "repair_history": updated_history,
        "fix_messages": updated_messages,
    }


def node_save(state: WorkflowState) -> dict:
    """节点 6a：保存最终成功版本，文件名固定为 name.cry。"""
    func_info = _get_function_info(state)
    output_path = func_info.save_snapshot(state["cryptol_code"])
    logger.info("已保存最终成功结果：%s", output_path)
    return {"output_path": str(output_path)}


def node_save_failed(state: WorkflowState) -> dict:
    """节点 6b：保存最终失败版本，并附带错误信息。"""
    func_info = _get_function_info(state)
    output_path = func_info.build_output_path("failed")

    header = (
        f"// COMPILATION FAILED after {state.get('retry_count', 0)} repair attempt(s)\n"
        f"// Last error:\n"
        + "\n".join(f"//   {line}" for line in state["compile_error"].splitlines())
        + "\n\n"
    )
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(header + state["cryptol_code"])

    logger.warning("已保存最终失败结果：%s", output_path)
    return {"output_path": str(output_path)}

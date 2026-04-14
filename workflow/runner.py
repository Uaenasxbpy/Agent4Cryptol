"""工作流运行入口。"""

import logging
import time

from workflow.graph import build_graph
from workflow.logging_utils import finalize_logging, setup_logging
from workflow.state import WorkflowState


logger = logging.getLogger(__name__)


def run_workflow(json_file_path: str, experiment_config: dict | None = None) -> dict:
    """运行单个函数 JSON 的完整工作流。

    Args:
        json_file_path: 函数 JSON 文件路径
        experiment_config: 消融实验配置字典，None 表示使用完整系统。
            支持字段：enable_gen_rag, enable_fix_rag, enable_repair_history,
                      max_retries, translation_system_prompt, fix_system_prompt,
                      rag_top_k_override, experiment_name

    返回的字典除原有 WorkflowState 字段外，额外包含：
    - elapsed_seconds: float  运行总耗时（秒）
    - workflow_error: str     若工作流本身抛异常，记录错误信息
    """
    exp_config = experiment_config or {}
    setup_logging(json_file_path)
    exp_name = exp_config.get("experiment_name", "full")
    logger.info("工作流启动：json_file_path=%s experiment=%s", json_file_path, exp_name)

    graph = build_graph()
    initial_state: WorkflowState = {
        "json_file_path": json_file_path,
        "function_data": {},
        "rag_context": "",
        "cryptol_code": "",
        "compile_success": False,
        "compile_error": "",
        "compile_output": "",
        "retry_count": 0,
        "output_path": "",
        "repair_history": [],
        "fix_messages": [],
        "experiment_config": exp_config,
    }

    result = dict(initial_state)
    start_time = time.time()
    try:
        result = graph.invoke(initial_state)

        if result["compile_success"]:
            logger.info("工作流结束：编译成功 output=%s", result["output_path"])
        else:
            logger.warning(
                "工作流结束：编译失败 retry_count=%s output=%s",
                result["retry_count"],
                result["output_path"],
            )

        result["workflow_error"] = ""
        return result

    except Exception as exc:
        logger.error("工作流异常中断：%s", exc, exc_info=True)
        result["workflow_error"] = str(exc)
        result["compile_success"] = False
        return result

    finally:
        result["elapsed_seconds"] = round(time.time() - start_time, 2)
        finalize_logging(result.get("retry_count", 0))
"""工作流共享状态定义。"""

from typing import Any, TypedDict


class RepairAttempt(TypedDict):
    """单轮修复尝试的摘要信息。"""

    retry_count: int
    source_compile_error: str
    attempted_change_summary: str


class WorkflowState(TypedDict):
    """LangGraph 节点之间传递的共享状态。"""

    json_file_path: str
    function_data: dict
    rag_context: str
    cryptol_code: str
    compile_success: bool
    compile_error: str
    compile_output: str
    retry_count: int
    output_path: str
    repair_history: list[RepairAttempt]
    fix_messages: list[Any]  # 多轮修复对话的消息历史
    # 消融实验配置：控制各功能组件是否启用
    # 支持字段：enable_gen_rag, enable_fix_rag, enable_repair_history,
    #           max_retries, translation_system_prompt, fix_system_prompt,
    #           rag_top_k_override, experiment_name
    experiment_config: dict
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
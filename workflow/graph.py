"""工作流图构建。"""

from langgraph.graph import END, StateGraph

from workflow.config import MAX_RETRIES
from workflow.nodes import (
    node_compile,
    node_fix,
    node_load_json,
    node_rag_retrieval,
    node_save,
    node_save_failed,
    node_translate,
)
from workflow.state import WorkflowState


def route_after_compile(state: WorkflowState) -> str:
    """
    根据编译结果决定下一步路由。
    max_retries 优先从 experiment_config 读取，允许消融实验覆盖。
    """
    if state["compile_success"]:
        return "save"
    exp_max = state.get("experiment_config", {}).get("max_retries")
    max_retries = exp_max if exp_max is not None else MAX_RETRIES
    if state.get("retry_count", 0) >= max_retries:
        return "save_failed"
    return "fix"


def build_graph():
    """组装并编译 LangGraph 状态图。"""
    graph = StateGraph(WorkflowState)

    graph.add_node("load_json", node_load_json)
    graph.add_node("rag_retrieval", node_rag_retrieval)
    graph.add_node("translate", node_translate)
    graph.add_node("compile", node_compile)
    graph.add_node("fix", node_fix)
    graph.add_node("save", node_save)
    graph.add_node("save_failed", node_save_failed)

    graph.set_entry_point("load_json")
    graph.add_edge("load_json", "rag_retrieval")
    graph.add_edge("rag_retrieval", "translate")
    graph.add_edge("translate", "compile")

    graph.add_conditional_edges(
        "compile",
        route_after_compile,
        {"save": "save", "fix": "fix", "save_failed": "save_failed"},
    )

    graph.add_edge("fix", "compile")
    graph.add_edge("save", END)
    graph.add_edge("save_failed", END)

    return graph.compile()

"""
agent_workflow.py
=================
命令行入口：运行单个函数 JSON 的工作流。

用法：
    python agent_workflow.py [path/to/function.json]

测试示例：
    python agent_workflow.py data/FIPS203/ir/functions/alg_001_for_example.json

如果未传入参数，则默认使用示例 JSON。
"""

import sys

from workflow.config import DEFAULT_JSON_FILE
from workflow.runner import run_workflow


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_JSON_FILE)
    run_workflow(target)

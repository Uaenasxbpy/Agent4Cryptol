"""依赖模块解析器：读取函数 JSON 的 dependencies 字段，加载已生成的 .cry 文件。

核心逻辑：
1. 从 function_data["dependencies"]["direct_calls"] 取出每个依赖
2. 根据 json_file_path 推断 spec（FIPS203 → fips203）
3. 在 settings.CRYPTOL_OUTPUT_DIR / spec / {callee_name}.cry 查找已生成文件
4. 提取模块名 + 完整代码，格式化为可注入提示词的依赖块
"""

from __future__ import annotations

import re
from pathlib import Path

from workflow.settings import settings


def _infer_spec(json_file_path: str) -> str:
    """从 JSON 路径中推断小写 spec 标识（如 fips203）。"""
    for part in Path(json_file_path).parts:
        if re.fullmatch(r"FIPS\d+", part, re.IGNORECASE):
            return part.lower()
    return ""


def _find_cry_file(callee_name: str, spec: str) -> Path | None:
    """按优先级查找依赖函数的 .cry 文件。"""
    if not spec:
        return None

    candidates = [
        settings.CRYPTOL_OUTPUT_DIR / spec / f"{callee_name}.cry",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _find_cry_file_for_experiment(callee_name: str, spec: str, experiment_name: str = "") -> Path | None:
    """优先查找当前消融实验目录，其次回退到默认 spec 目录。"""
    if not spec:
        return None

    candidates: list[Path] = []
    if experiment_name:
        candidates.append(settings.CRYPTOL_OUTPUT_DIR / spec / experiment_name / f"{callee_name}.cry")
    candidates.append(settings.CRYPTOL_OUTPUT_DIR / spec / f"{callee_name}.cry")

    for path in candidates:
        if path.exists():
            return path
    return None


def _extract_module_name(cry_code: str) -> str:
    """从 Cryptol 代码中提取 module 名称。"""
    match = re.search(r"^\s*module\s+([A-Za-z_][A-Za-z0-9_']*)\s+where", cry_code, re.MULTILINE)
    if match:
        return match.group(1)
    return ""


def _format_import_hint(module_name: str, import_strategy: str) -> str:
    """根据 import_strategy 给出推荐的 import 语句。"""
    if not module_name:
        return ""
    # 生成一个简短别名（取首字母大写缩写，避免与函数同名时混淆）
    alias = "".join(c for c in module_name if c.isupper()) or module_name[:3]
    if import_strategy == "qualified_import":
        return (
            f"  // 推荐使用（别名限定）：import {module_name} as {alias}\n"
            f"  // 调用方式：{alias}::{module_name} arg"
        )
    # direct_import 或 none：直接 import，函数名裸调用
    return (
        f"  // 推荐使用（直接导入）：import {module_name}\n"
        f"  // 调用方式：{module_name} arg"
    )


def load_dependencies(
    function_data: dict,
    json_file_path: str,
    experiment_name: str = "",
) -> str:
    """加载当前函数所有已生成依赖的 .cry 代码，格式化为提示词注入块。

    Returns:
        格式化后的依赖上下文字符串；若无依赖则返回空字符串。
    """
    deps = function_data.get("dependencies", {})
    direct_calls: list[dict] = deps.get("direct_calls", [])
    import_strategy: str = deps.get("import_strategy", "qualified_import")

    if not direct_calls:
        return ""

    spec = _infer_spec(json_file_path)
    blocks: list[str] = []

    for call in direct_calls:
        callee_name: str = call.get("callee_name", "")
        callee_id: str = call.get("callee_id", "")
        required: bool = call.get("required", True)

        if not callee_name:
            continue

        cry_path = _find_cry_file_for_experiment(callee_name, spec, experiment_name)

        if cry_path is None:
            # 依赖文件尚未生成，给出占位提示
            status = "REQUIRED" if required else "OPTIONAL"
            blocks.append(
                f"// [{status}] {callee_name} ({callee_id})\n"
                f"// ⚠ 依赖文件尚未生成（{settings.CRYPTOL_OUTPUT_DIR / spec / callee_name}.cry 不存在）。\n"
                f"// 若该依赖是必需的，请先生成它，或在当前模块内自行实现。"
            )
            continue

        cry_code = cry_path.read_text(encoding="utf-8").strip()
        module_name = _extract_module_name(cry_code)
        import_hint = _format_import_hint(module_name or callee_name, import_strategy)

        blocks.append(
            f"// === 依赖模块：{callee_name} ({callee_id}) ===\n"
            f"// 文件路径：{cry_path}\n"
            f"{import_hint}\n"
            f"// --- 完整模块代码 ---\n"
            f"{cry_code}"
        )

    if not blocks:
        return ""

    header = (
        f"// ============================================================\n"
        f"// 已生成的依赖模块（import_strategy: {import_strategy}）\n"
        f"// 使用上方代码中的模块名和函数签名决定如何 import 和调用。\n"
        f"// ============================================================\n"
    )
    return header + "\n\n".join(blocks)

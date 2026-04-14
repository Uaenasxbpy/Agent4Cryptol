"""
report_ablation.py
==================
消融实验跨条件对比报告生成器。

从多个实验条件的原始结果中提取关键指标，输出：
  - ablation_comparison_{ts}.json   完整对比数据
  - ablation_comparison_{ts}.md     Markdown 表格报告
  - ablation_comparison_{ts}.csv    CSV（供 Excel / pandas 分析）

核心指标（每个条件一行）：
  condition         实验条件名
  total             处理函数总数
  pass_at_round_0   首次翻译即通过（不需要任何修复）
  pass_final        最终通过（含所有修复轮次）
  pass_rate_0       pass_at_round_0 / total  (%)
  pass_rate_final   pass_final / total       (%)
  avg_repair_rounds 通过函数的平均修复轮次（仅计成功案例）
  avg_time_s        每函数平均耗时（秒）
  top_error         失败函数中最常见的错误类型
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 错误分类（复用 report.py 的逻辑，避免循环导入）
# ---------------------------------------------------------------------------

def _classify_error(compile_error: str) -> str:
    if not compile_error or not compile_error.strip():
        return ""
    lower = compile_error.lower()
    if "boundaries" in lower and "numeric types" in lower:
        return "sequence boundary"
    if "parse error" in lower:
        return "parse error"
    if "type mismatch" in lower:
        return "type mismatch"
    if "expected a value" in lower and "found a type" in lower:
        return "type used as value"
    if "not in scope" in lower:
        return "not in scope"
    if "does not support" in lower:
        return "unsupported op"
    if "ambiguous" in lower:
        return "ambiguous type"
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    return "other"


# ---------------------------------------------------------------------------
# 单条件指标提取
# ---------------------------------------------------------------------------

def _extract_metrics(condition_name: str, results: list[dict]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {"condition": condition_name, "total": 0}

    pass_round_0 = sum(
        1 for r in results
        if r.get("compile_success") and r.get("retry_count", 0) == 0
    )
    pass_final = sum(1 for r in results if r.get("compile_success"))

    # 成功案例的修复轮次（只包含经过修复的，即 retry_count > 0）
    repaired_successes = [
        r["retry_count"] for r in results
        if r.get("compile_success") and r.get("retry_count", 0) > 0
    ]
    avg_repair = round(sum(repaired_successes) / len(repaired_successes), 2) if repaired_successes else 0.0

    # 平均耗时
    times = [r.get("elapsed_seconds", 0) for r in results if r.get("elapsed_seconds")]
    avg_time = round(sum(times) / len(times), 2) if times else 0.0

    # 最常见错误类型
    error_counter: Counter = Counter()
    for r in results:
        if not r.get("compile_success"):
            err = r.get("compile_error", "") or r.get("workflow_error", "")
            error_counter[_classify_error(err)] += 1
    top_error = error_counter.most_common(1)[0][0] if error_counter else ""

    # 修复轮次分布
    round_dist: dict[str, int] = {}
    for r in results:
        key = f"pass@{r.get('retry_count', 0)}" if r.get("compile_success") else "failed"
        round_dist[key] = round_dist.get(key, 0) + 1

    return {
        "condition": condition_name,
        "total": total,
        "pass_at_round_0": pass_round_0,
        "pass_final": pass_final,
        "pass_rate_0": round(pass_round_0 / total * 100, 1),
        "pass_rate_final": round(pass_final / total * 100, 1),
        "avg_repair_rounds": avg_repair,
        "avg_time_s": avg_time,
        "top_error": top_error,
        "round_distribution": round_dist,
    }


# ---------------------------------------------------------------------------
# 构建 & 格式化对比报告
# ---------------------------------------------------------------------------

def build_comparison(all_results: dict[str, list[dict]]) -> dict[str, Any]:
    """从多个条件的结果中构建对比报告字典。

    Args:
        all_results: {condition_name: [workflow_result, ...]}

    Returns:
        包含 metrics 列表和 per_function 对比的报告字典
    """
    metrics = [
        _extract_metrics(name, results)
        for name, results in all_results.items()
    ]

    # 逐函数对比（按函数名对齐各条件结果）
    func_index: dict[str, dict[str, Any]] = {}
    for cond_name, results in all_results.items():
        for r in results:
            func_data = r.get("function_data", {})
            func_name = func_data.get("name", "") or Path(r.get("json_file_path", "")).stem
            if func_name not in func_index:
                func_index[func_name] = {"function": func_name, "results": {}}
            func_index[func_name]["results"][cond_name] = {
                "success": r.get("compile_success", False),
                "retry_count": r.get("retry_count", 0),
                "elapsed_seconds": r.get("elapsed_seconds", 0),
            }

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "conditions": list(all_results.keys()),
        "metrics": metrics,
        "per_function": list(func_index.values()),
    }


def format_markdown_comparison(comparison: dict) -> str:
    lines = []
    lines.append("# Agent4Cryptol Ablation Study Report")
    lines.append(f"\n> Generated: {comparison.get('timestamp', '')}")
    lines.append(f"\nConditions evaluated: `{'`, `'.join(comparison['conditions'])}`")

    metrics = comparison.get("metrics", [])

    # ---- 核心指标表 ----
    lines.append("\n## Summary\n")
    header = "| Condition | Total | Pass@0 | Pass@0% | Pass Final | Final% | Avg Repairs | Avg Time(s) | Top Error |"
    lines.append(header)
    lines.append("|-----------|------:|-------:|--------:|-----------:|-------:|------------:|------------:|-----------|")
    for m in metrics:
        lines.append(
            f"| **{m['condition']}** "
            f"| {m.get('total', 0)} "
            f"| {m.get('pass_at_round_0', 0)} "
            f"| {m.get('pass_rate_0', 0)}% "
            f"| {m.get('pass_final', 0)} "
            f"| {m.get('pass_rate_final', 0)}% "
            f"| {m.get('avg_repair_rounds', 0)} "
            f"| {m.get('avg_time_s', 0)} "
            f"| {m.get('top_error', '')} |"
        )

    # ---- 修复轮次分布表 ----
    lines.append("\n## Fix Round Distribution per Condition\n")
    # 收集所有可能的 key
    all_keys: set[str] = set()
    for m in metrics:
        all_keys.update(m.get("round_distribution", {}).keys())
    sorted_keys = sorted(all_keys, key=lambda k: (k == "failed", k))

    header2 = "| Condition | " + " | ".join(sorted_keys) + " |"
    lines.append(header2)
    lines.append("|-----------|" + "------:|" * len(sorted_keys))
    for m in metrics:
        rd = m.get("round_distribution", {})
        row = f"| **{m['condition']}** | " + " | ".join(str(rd.get(k, 0)) for k in sorted_keys) + " |"
        lines.append(row)

    # ---- 增量对比（相对 full baseline） ----
    full_metric = next((m for m in metrics if m["condition"] == "full"), None)
    if full_metric and len(metrics) > 1:
        lines.append("\n## Delta vs. Full Baseline\n")
        lines.append("| Condition | Δ Pass@0% | Δ Final% | Δ Avg Time(s) |")
        lines.append("|-----------|----------:|---------:|--------------:|")
        base_p0 = full_metric.get("pass_rate_0", 0)
        base_pf = full_metric.get("pass_rate_final", 0)
        base_t = full_metric.get("avg_time_s", 0)
        for m in metrics:
            if m["condition"] == "full":
                continue
            dp0 = round(m.get("pass_rate_0", 0) - base_p0, 1)
            dpf = round(m.get("pass_rate_final", 0) - base_pf, 1)
            dt = round(m.get("avg_time_s", 0) - base_t, 2)
            sign = lambda v: f"+{v}" if v > 0 else str(v)
            lines.append(f"| **{m['condition']}** | {sign(dp0)}% | {sign(dpf)}% | {sign(dt)} |")

    # ---- 逐函数对比（展示各条件是否通过） ----
    per_func = comparison.get("per_function", [])
    if per_func:
        conditions = comparison.get("conditions", [])
        lines.append("\n## Per-Function Pass/Fail Matrix\n")
        header3 = "| Function | " + " | ".join(conditions) + " |"
        lines.append(header3)
        lines.append("|----------|" + "-------:|" * len(conditions))
        for entry in sorted(per_func, key=lambda x: x["function"]):
            row_parts = [f"| {entry['function']} |"]
            for cond in conditions:
                r = entry["results"].get(cond)
                if r is None:
                    row_parts.append(" - |")
                elif r["success"]:
                    retries = r["retry_count"]
                    row_parts.append(f" Pass@{retries} |")
                else:
                    row_parts.append(" Fail |")
            lines.append("".join(row_parts))

    return "\n".join(lines)


def format_csv_comparison(comparison: dict) -> str:
    """生成 CSV 格式的核心指标表（含 per_function 矩阵）。"""
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)

    # 汇总表
    writer.writerow([
        "condition", "total", "pass_at_round_0", "pass_rate_0_%",
        "pass_final", "pass_rate_final_%", "avg_repair_rounds",
        "avg_time_s", "top_error",
    ])
    for m in comparison.get("metrics", []):
        writer.writerow([
            m.get("condition", ""),
            m.get("total", 0),
            m.get("pass_at_round_0", 0),
            m.get("pass_rate_0", 0),
            m.get("pass_final", 0),
            m.get("pass_rate_final", 0),
            m.get("avg_repair_rounds", 0),
            m.get("avg_time_s", 0),
            m.get("top_error", ""),
        ])

    # 空行分隔
    writer.writerow([])
    writer.writerow(["Per-Function Matrix"])

    conditions = comparison.get("conditions", [])
    writer.writerow(["function"] + conditions)
    for entry in sorted(comparison.get("per_function", []), key=lambda x: x["function"]):
        row = [entry["function"]]
        for cond in conditions:
            r = entry["results"].get(cond)
            if r is None:
                row.append("-")
            elif r["success"]:
                row.append(f"Pass@{r['retry_count']}")
            else:
                row.append("Fail")
        writer.writerow(row)

    return buf.getvalue()


def save_comparison(comparison: dict, output_dir: str | Path = "results") -> dict[str, Path]:
    """将对比报告保存为 JSON、Markdown、CSV 三种格式。

    Returns:
        {"json": Path, "markdown": Path, "csv": Path}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"ablation_comparison_{ts}.json"
    json_path.write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    md_path = output_dir / f"ablation_comparison_{ts}.md"
    md_path.write_text(format_markdown_comparison(comparison), encoding="utf-8")

    csv_path = output_dir / f"ablation_comparison_{ts}.csv"
    csv_path.write_text(format_csv_comparison(comparison), encoding="utf-8", newline="")

    return {"json": json_path, "markdown": md_path, "csv": csv_path}

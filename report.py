"""实验结果统计与报告生成。

从批量工作流运行结果中提取统计数据，输出终端表格、JSON 和 Markdown 报告。
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def _classify_error(compile_error: str) -> str:
    """将编译错误文本归类为简短的错误类别。"""
    if not compile_error or not compile_error.strip():
        return ""

    lower = compile_error.lower()

    if "boundaries" in lower and "numeric types" in lower:
        return "Parse error: sequence boundary not a type expression"
    if "parse error" in lower:
        return "Parse error: other"
    if "type mismatch" in lower:
        return "Type mismatch"
    if "expected a value" in lower and "found a type" in lower:
        return "Type used as value"
    if "not in scope" in lower:
        return "Not in scope"
    if "does not support" in lower:
        return "Unsupported operation on type"
    if "ambiguous" in lower:
        return "Ambiguous type"
    if "cannot evaluate" in lower:
        return "Cannot evaluate polymorphic value"
    if "infinite type" in lower:
        return "Infinite type"
    if "工作流异常" in lower or "timeout" in lower or "timed out" in lower:
        return "Workflow/compilation timeout"

    return "Other"


def _extract_spec(json_file_path: str) -> str:
    """从 JSON 路径中提取 FIPS spec 标识。"""
    for part in Path(json_file_path).parts:
        if re.fullmatch(r"FIPS\d+", part, re.IGNORECASE):
            return part.upper()
    return "UNKNOWN"


def _extract_function_name(result: dict) -> str:
    """从结果中提取函数名。"""
    func_data = result.get("function_data", {})
    name = func_data.get("name", "")
    if name:
        return name
    return Path(result.get("json_file_path", "unknown")).stem


def build_report(results: list[dict]) -> dict[str, Any]:
    """从工作流结果列表构建完整统计报告。

    Args:
        results: run_workflow() 返回字典的列表

    Returns:
        包含所有统计维度的报告字典
    """
    total = len(results)
    if total == 0:
        return {"total": 0, "success": 0, "failed": 0, "success_rate": 0.0}

    success_count = sum(1 for r in results if r.get("compile_success"))
    failed_count = total - success_count

    # ---- 按 spec 分组 ----
    by_spec: dict[str, dict] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
    for r in results:
        spec = _extract_spec(r.get("json_file_path", ""))
        by_spec[spec]["total"] += 1
        if r.get("compile_success"):
            by_spec[spec]["success"] += 1
        else:
            by_spec[spec]["failed"] += 1

    for spec_stats in by_spec.values():
        spec_stats["success_rate"] = (
            round(spec_stats["success"] / spec_stats["total"] * 100, 1)
            if spec_stats["total"] > 0 else 0.0
        )

    # ---- 修复轮次分布 ----
    round_dist: Counter = Counter()
    for r in results:
        retry = r.get("retry_count", 0)
        if r.get("compile_success"):
            round_dist[f"Pass@{retry}"] += 1
        else:
            round_dist["Failed"] += 1

    # ---- 错误类型统计（仅失败的） ----
    error_types: Counter = Counter()
    for r in results:
        if not r.get("compile_success"):
            err = r.get("compile_error", "") or r.get("workflow_error", "")
            error_types[_classify_error(err)] += 1

    # ---- 耗时统计 ----
    times = [r.get("elapsed_seconds", 0) for r in results if r.get("elapsed_seconds")]
    avg_time = round(sum(times) / len(times), 2) if times else 0.0
    total_time = round(sum(times), 2)

    # ---- 逐函数明细 ----
    details = []
    for r in results:
        details.append({
            "spec": _extract_spec(r.get("json_file_path", "")),
            "function_name": _extract_function_name(r),
            "json_file": r.get("json_file_path", ""),
            "success": r.get("compile_success", False),
            "retry_count": r.get("retry_count", 0),
            "error_type": _classify_error(r.get("compile_error", "") or r.get("workflow_error", "")) if not r.get("compile_success") else "",
            "compile_error_excerpt": (r.get("compile_error", "") or "")[:200],
            "output_path": r.get("output_path", ""),
            "elapsed_seconds": r.get("elapsed_seconds", 0),
        })

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "success": success_count,
        "failed": failed_count,
        "success_rate": round(success_count / total * 100, 1),
        "by_spec": dict(by_spec),
        "round_distribution": dict(round_dist),
        "error_types": dict(error_types),
        "avg_elapsed_seconds": avg_time,
        "total_elapsed_seconds": total_time,
        "details": details,
    }


def format_terminal_report(report: dict) -> str:
    """将报告字典格式化为终端可读的表格文本。"""
    lines = []

    lines.append("=" * 70)
    lines.append("  Agent4Cryptol Batch Experiment Report")
    lines.append(f"  {report.get('timestamp', '')}")
    lines.append("=" * 70)

    # 总览
    lines.append("")
    lines.append("=== Overall Results ===")
    total = report["total"]
    lines.append(
        f"Total: {total} | "
        f"Success: {report['success']} | "
        f"Failed: {report['failed']} | "
        f"Rate: {report['success_rate']}%"
    )
    lines.append(
        f"Avg Time: {report['avg_elapsed_seconds']}s | "
        f"Total Time: {report['total_elapsed_seconds']}s"
    )

    # 按 spec 分组
    lines.append("")
    lines.append("=== By Specification ===")
    lines.append(f"{'Spec':<12} | {'Total':>5} | {'Success':>7} | {'Failed':>6} | {'Rate':>7}")
    lines.append("-" * 50)
    for spec in sorted(report.get("by_spec", {})):
        s = report["by_spec"][spec]
        lines.append(
            f"{spec:<12} | {s['total']:>5} | {s['success']:>7} | {s['failed']:>6} | {s['success_rate']:>6.1f}%"
        )

    # 修复轮次
    lines.append("")
    lines.append("=== Fix Round Distribution ===")
    lines.append(f"{'Round':<12} | {'Count':>5} | {'Percentage':>10}")
    lines.append("-" * 35)
    round_dist = report.get("round_distribution", {})
    for key in sorted(round_dist, key=lambda k: (k == "Failed", k)):
        count = round_dist[key]
        pct = round(count / total * 100, 1) if total > 0 else 0.0
        label = key
        if key == "Pass@0":
            label += "  (首次通过)"
        elif key == "Failed":
            label += "  (修复耗尽)"
        lines.append(f"{label:<24} | {count:>5} | {pct:>9.1f}%")

    # 错误类型
    error_types = report.get("error_types", {})
    if error_types:
        lines.append("")
        lines.append("=== Common Error Types (Failed Only) ===")
        lines.append(f"{'Error Type':<50} | {'Count':>5}")
        lines.append("-" * 60)
        for err_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
            lines.append(f"{err_type:<50} | {count:>5}")

    # 逐函数结果（简表）
    lines.append("")
    lines.append("=== Per-Function Results ===")
    lines.append(f"{'Spec':<10} | {'Function':<30} | {'Result':<8} | {'Retries':>7} | {'Time':>7}")
    lines.append("-" * 75)
    for d in sorted(report.get("details", []), key=lambda x: (x["spec"], x["function_name"])):
        status = "OK" if d["success"] else "FAIL"
        lines.append(
            f"{d['spec']:<10} | {d['function_name']:<30} | {status:<8} | {d['retry_count']:>7} | {d['elapsed_seconds']:>6.1f}s"
        )

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def format_markdown_report(report: dict) -> str:
    """将报告字典格式化为 Markdown。"""
    lines = []

    lines.append("# Agent4Cryptol Batch Experiment Report")
    lines.append(f"\n> Generated: {report.get('timestamp', '')}")

    # 总览
    lines.append("\n## Overall Results\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Functions | {report['total']} |")
    lines.append(f"| Success | {report['success']} |")
    lines.append(f"| Failed | {report['failed']} |")
    lines.append(f"| Success Rate | {report['success_rate']}% |")
    lines.append(f"| Avg Time per Function | {report['avg_elapsed_seconds']}s |")
    lines.append(f"| Total Time | {report['total_elapsed_seconds']}s |")

    # 按 spec
    lines.append("\n## By Specification\n")
    lines.append("| Spec | Total | Success | Failed | Rate |")
    lines.append("|------|------:|--------:|-------:|-----:|")
    for spec in sorted(report.get("by_spec", {})):
        s = report["by_spec"][spec]
        lines.append(f"| {spec} | {s['total']} | {s['success']} | {s['failed']} | {s['success_rate']}% |")

    # 修复轮次
    total = report["total"]
    lines.append("\n## Fix Round Distribution\n")
    lines.append("| Round | Count | Percentage | Note |")
    lines.append("|-------|------:|-----------:|------|")
    round_dist = report.get("round_distribution", {})
    for key in sorted(round_dist, key=lambda k: (k == "Failed", k)):
        count = round_dist[key]
        pct = round(count / total * 100, 1) if total > 0 else 0.0
        note = ""
        if key == "Pass@0":
            note = "首次编译通过"
        elif key == "Failed":
            note = "修复耗尽仍失败"
        else:
            n = key.replace("Pass@", "")
            note = f"{n}轮修复后通过"
        lines.append(f"| {key} | {count} | {pct}% | {note} |")

    # 错误类型
    error_types = report.get("error_types", {})
    if error_types:
        lines.append("\n## Common Error Types (Failed Only)\n")
        lines.append("| Error Type | Count |")
        lines.append("|------------|------:|")
        for err_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
            lines.append(f"| {err_type} | {count} |")

    # 逐函数
    lines.append("\n## Per-Function Details\n")
    lines.append("| Spec | Function | Result | Retries | Time | Error |")
    lines.append("|------|----------|--------|--------:|-----:|-------|")
    for d in sorted(report.get("details", []), key=lambda x: (x["spec"], x["function_name"])):
        status = "Pass" if d["success"] else "Fail"
        err = d.get("error_type", "") or ""
        lines.append(
            f"| {d['spec']} | {d['function_name']} | {status} | {d['retry_count']} | {d['elapsed_seconds']}s | {err} |"
        )

    return "\n".join(lines)


def save_report(report: dict, output_dir: str | Path = "results") -> dict[str, Path]:
    """将报告保存为 JSON 和 Markdown 文件。

    Args:
        report: build_report() 的输出
        output_dir: 报告输出目录

    Returns:
        {"json": Path, "markdown": Path} 已保存的文件路径
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"batch_{ts}.json"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_path = output_dir / f"batch_{ts}.md"
    md_path.write_text(format_markdown_report(report), encoding="utf-8")

    return {"json": json_path, "markdown": md_path}

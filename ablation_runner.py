"""
Ablation runner for Agent4Cryptol.

Results are stored per spec so different FIPS runs do not mix together.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from batch_run import discover_functions
from report import build_report, save_report
from report_ablation import build_comparison, save_comparison


# ---------------------------------------------------------------------------
# 消融实验条件：4 个递进条件，逐步叠加组件
# ---------------------------------------------------------------------------

ABLATION_CONDITIONS: dict[str, dict] = {
    # 最弱基线：只有提示词，直接一次生成，无 RAG，无修复
    "baseline": {
        "experiment_name": "baseline",
        "enable_gen_rag": False,
        "enable_fix_rag": False,
        "enable_repair_history": True,
        "max_retries": 0,
    },
    # 加入 RAG：提示词 + RAG 增强，但不修复
    "+rag": {
        "experiment_name": "+rag",
        "enable_gen_rag": True,
        "enable_fix_rag": True,
        "enable_repair_history": True,
        "max_retries": 0,
    },
    # 加入修复：提示词 + 多轮修复 Agent，但不使用 RAG
    "+repair": {
        "experiment_name": "+repair",
        "enable_gen_rag": False,
        "enable_fix_rag": False,
        "enable_repair_history": True,
        "max_retries": 3,
    },
    # 完整系统：提示词 + RAG + 多轮修复 Agent
    "full": {
        "experiment_name": "full",
        "enable_gen_rag": True,
        "enable_fix_rag": True,
        "enable_repair_history": True,
        "max_retries": 3,
    },
}


def _extract_spec(json_path: Path) -> str:
    for part in json_path.parts:
        if re.fullmatch(r"FIPS\d+", part, re.IGNORECASE):
            return part.lower()
    return "misc"


def run_condition(
    condition_name: str,
    exp_config: dict,
    json_files: list[Path],
    output_dir: Path,
    spec_name: str,
) -> tuple[list[dict], Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    condition_dir = output_dir / "experiments" / spec_name / f"{condition_name}_{ts}"
    condition_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Spec:      {spec_name}")
    print(f"  Condition: {condition_name}")
    print(f"  Config:    {exp_config}")
    print(f"  Files:     {len(json_files)}")
    print(f"  Output:    {condition_dir}")
    print(f"{'=' * 60}")

    from workflow.runner import run_workflow

    results: list[dict] = []
    total = len(json_files)
    for idx, json_path in enumerate(json_files, 1):
        func_name = json_path.stem
        print(f"  [{idx}/{total}] {func_name} ...", end=" ", flush=True)
        try:
            result = run_workflow(str(json_path), experiment_config=exp_config)
        except Exception as exc:
            result = {
                "json_file_path": str(json_path),
                "function_data": {"name": func_name},
                "compile_success": False,
                "compile_error": "",
                "compile_output": "",
                "retry_count": 0,
                "output_path": "",
                "repair_history": [],
                "workflow_error": str(exc),
                "elapsed_seconds": 0,
                "experiment_config": exp_config,
            }
        status = "OK" if result.get("compile_success") else "FAIL"
        retries = result.get("retry_count", 0)
        print(f"{status} (retries={retries})")
        results.append(result)

    raw_path = condition_dir / "batch_results.json"
    raw_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    report = build_report(results)
    report["experiment_name"] = condition_name
    report["experiment_config"] = exp_config
    save_report(report, condition_dir)

    success = sum(1 for r in results if r.get("compile_success"))
    rate = round(success / total * 100, 1) if total else 0.0
    print(f"  => {condition_name}: {success}/{total} passed ({rate}%)")

    return results, condition_dir


def run_ablation(
    specs: list[str] | None,
    conditions: list[str],
    limit: int | None,
    output_dir: Path,
) -> None:
    json_files = discover_functions(specs)
    if not json_files:
        print("No function JSON files found.")
        sys.exit(1)

    if limit:
        json_files = json_files[:limit]

    print(f"Discovered {len(json_files)} function JSON files (limit={limit})")
    print(f"Conditions: {conditions}")

    files_by_spec: dict[str, list[Path]] = {}
    for json_file in json_files:
        files_by_spec.setdefault(_extract_spec(json_file), []).append(json_file)

    for spec_name, spec_files in files_by_spec.items():
        print(f"\nProcessing {spec_name} with {len(spec_files)} functions")
        all_results: dict[str, list[dict]] = {}

        for cond_name in conditions:
            if cond_name not in ABLATION_CONDITIONS:
                print(f"[WARN] Unknown condition: {cond_name}; skipped")
                continue

            exp_config = ABLATION_CONDITIONS[cond_name]
            results, _ = run_condition(cond_name, exp_config, spec_files, output_dir, spec_name)
            all_results[cond_name] = results

        if not all_results:
            print(f"No valid results for {spec_name}.")
            continue

        comparison_dir = output_dir / spec_name
        print(f"\nGenerating comparison report for {spec_name} ...")
        comparison = build_comparison(all_results)
        paths = save_comparison(comparison, comparison_dir)
        print(f"\nCompleted ablation for {spec_name}")
        print(f"  JSON:     {paths['json']}")
        print(f"  Markdown: {paths['markdown']}")
        print(f"  CSV:      {paths['csv']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Agent4Cryptol ablation experiments",
    )
    parser.add_argument(
        "--spec",
        nargs="+",
        default=None,
        help="Optional FIPS spec filter, e.g. FIPS203 FIPS204",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=list(ABLATION_CONDITIONS.keys()),
        help=f"Conditions to run. Options: {list(ABLATION_CONDITIONS.keys())}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N functions for quick validation",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Root output directory (default: results)",
    )
    args = parser.parse_args()

    run_ablation(
        specs=args.spec,
        conditions=args.conditions,
        limit=args.limit,
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()

"""
batch_run.py
============
批量处理 data/ 下所有函数 JSON 的工作流入口。

用法：
    python batch_run.py                          # 处理所有 FIPS 标准
    python batch_run.py --spec FIPS203           # 只处理 FIPS203
    python batch_run.py --spec FIPS203 FIPS204   # 处理多个标准
    python batch_run.py --skip-existing          # 跳过已有成功输出的函数
    python batch_run.py --dry-run                # 仅列出将要处理的文件，不执行

结果保存在 Cryptol/<spec>/ 目录（由工作流自动分类），
统计报告保存在 results/ 目录。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from report import build_report, format_terminal_report, save_report


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"


def _load_layer_order(spec_dir: Path) -> dict[str, int]:
    """读取 source/function_layer.json，返回 {函数文件名stem: 全局排序键} 映射。

    排序键格式为 layer * 1000 + 层内位置，保证同 layer 内按声明顺序排列。
    若文件不存在则返回空字典，调用方回退到文件名字典序。
    """
    layer_file = spec_dir / "source" / "function_layer.json"
    if not layer_file.exists():
        return {}
    try:
        data = json.loads(layer_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    order: dict[str, int] = {}
    for layer_entry in data.get("layers", []):
        layer_idx = layer_entry.get("layer", 0)
        for pos, func_stem in enumerate(layer_entry.get("functions", [])):
            order[func_stem] = layer_idx * 1000 + pos
    return order


def discover_functions(specs: list[str] | None = None) -> list[Path]:
    """发现 data/ 下所有函数 JSON 文件，按 function_layer.json 定义的 layer 顺序排列。

    Args:
        specs: 可选的 FIPS 标准过滤列表，如 ["FIPS203", "FIPS204"]。
               为 None 时返回所有标准。

    Returns:
        按 layer 层级（再按层内位置）排序的 JSON 文件路径列表。
        若某 spec 无 function_layer.json，则该 spec 的函数按文件名字典序排列。
        多 spec 时各 spec 结果顺序拼接。
    """
    spec_dirs: list[Path] = []
    if specs:
        for spec in specs:
            spec_dir = DATA_DIR / spec.upper()
            if (spec_dir / "ir" / "functions").exists():
                spec_dirs.append(spec_dir)
            else:
                print(f"[WARN] 标准目录不存在：{spec_dir / 'ir' / 'functions'}")
    else:
        for spec_dir in sorted(DATA_DIR.iterdir()):
            if spec_dir.is_dir() and re.fullmatch(r"FIPS\d+", spec_dir.name, re.IGNORECASE):
                if (spec_dir / "ir" / "functions").exists():
                    spec_dirs.append(spec_dir)

    result: list[Path] = []
    for spec_dir in spec_dirs:
        func_dir = spec_dir / "ir" / "functions"
        all_files = list(func_dir.glob("*.json"))
        layer_order = _load_layer_order(spec_dir)

        if layer_order:
            # 按 layer 排序；不在 layer 文件中的函数排到最后，按文件名保持相对顺序
            max_key = max(layer_order.values()) + 1
            all_files.sort(key=lambda p: (layer_order.get(p.stem, max_key), p.stem))
            missing = [p.stem for p in all_files if p.stem not in layer_order]
            if missing:
                print(f"[WARN] {spec_dir.name}: 以下函数不在 function_layer.json 中，将排在末尾：{missing}")
        else:
            all_files.sort()

        result.extend(all_files)

    return result


def _extract_spec_from_path(path: Path) -> str:
    """从路径中提取 FIPS 标识。"""
    for part in path.parts:
        if re.fullmatch(r"FIPS\d+", part, re.IGNORECASE):
            return part.lower()
    return "misc"


def _extract_function_name_from_json(path: Path) -> str:
    """从 JSON 文件中提取函数名，失败时回退到文件名。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("name", "") or path.stem
    except Exception:
        return path.stem


def _has_successful_output(json_path: Path) -> bool:
    """检查该函数是否已有成功的 Cryptol 输出（非 _failed 文件）。"""
    from workflow.settings import settings

    spec = _extract_spec_from_path(json_path)
    func_name = _extract_function_name_from_json(json_path)
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", func_name)
    output_path = settings.CRYPTOL_OUTPUT_DIR / spec / f"{sanitized}.cry"
    return output_path.exists()


def run_batch(
    json_files: list[Path],
    skip_existing: bool = False,
) -> list[dict]:
    """批量执行工作流。

    Args:
        json_files: 要处理的 JSON 文件路径列表
        skip_existing: 若为 True，跳过已有成功输出的函数

    Returns:
        每个函数的工作流结果字典列表
    """
    from workflow.runner import run_workflow

    results = []
    total = len(json_files)

    for idx, json_path in enumerate(json_files, 1):
        func_name = _extract_function_name_from_json(json_path)
        spec = _extract_spec_from_path(json_path)

        if skip_existing and _has_successful_output(json_path):
            print(f"[{idx}/{total}] SKIP {spec}/{func_name} (已有成功输出)")
            continue

        print(f"[{idx}/{total}] RUN  {spec}/{func_name} ...")

        try:
            result = run_workflow(str(json_path))
        except Exception as exc:
            print(f"[{idx}/{total}] ERROR {spec}/{func_name}: {exc}")
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
            }

        status = "OK" if result.get("compile_success") else "FAIL"
        retries = result.get("retry_count", 0)
        elapsed = result.get("elapsed_seconds", 0)
        print(f"[{idx}/{total}] {status} {spec}/{func_name} (retries={retries}, time={elapsed}s)")

        results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="批量处理 data/ 下的函数 JSON 并生成 Cryptol 代码",
    )
    parser.add_argument(
        "--spec",
        nargs="+",
        default=None,
        help="指定要处理的 FIPS 标准（如 FIPS203 FIPS204），默认处理所有",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过已有成功输出（.cry 文件）的函数",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅列出将要处理的文件，不实际执行工作流",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="报告输出目录（默认 results/）",
    )
    args = parser.parse_args()

    # 发现文件
    json_files = discover_functions(args.spec)
    if not json_files:
        print("未发现任何函数 JSON 文件。")
        sys.exit(1)

    print(f"共发现 {len(json_files)} 个函数 JSON 文件")
    if args.spec:
        print(f"过滤标准：{', '.join(args.spec)}")
    print()

    # dry-run 模式
    if args.dry_run:
        # 预加载各 spec 的 layer 顺序，用于 dry-run 显示
        _layer_cache: dict[str, dict[str, int]] = {}
        for idx, p in enumerate(json_files, 1):
            spec_upper = _extract_spec_from_path(p).upper()
            if spec_upper not in _layer_cache:
                spec_dir = DATA_DIR / spec_upper
                _layer_cache[spec_upper] = _load_layer_order(spec_dir)
            layer_order = _layer_cache[spec_upper]
            layer_key = layer_order.get(p.stem)
            layer_str = f"layer{layer_key // 1000}" if layer_key is not None else "layer?"
            spec = spec_upper.lower()
            name = _extract_function_name_from_json(p)
            skip_mark = " [SKIP]" if args.skip_existing and _has_successful_output(p) else ""
            print(f"  {idx:>3}. [{layer_str}] {spec}/{name}{skip_mark}")
        print(f"\n共 {len(json_files)} 个文件（dry-run 模式，未执行）")
        return

    # 批量执行
    results = run_batch(json_files, skip_existing=args.skip_existing)

    if not results:
        print("没有需要处理的函数（可能全部被跳过）。")
        return

    # 生成报告
    report = build_report(results)

    # 终端输出
    print()
    print(format_terminal_report(report))

    # 保存文件
    paths = save_report(report, args.output_dir)
    print(f"\n报告已保存：")
    print(f"  JSON:     {paths['json']}")
    print(f"  Markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()

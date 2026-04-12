"""Cryptol编译器模块 - 直接调用本地Cryptol编译器。"""

import logging
import re
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Tuple

from workflow.settings import settings


logger = logging.getLogger(__name__)


def extract_module_name(code: str) -> Optional[str]:
    """从 Cryptol 源码中提取模块名。

    规则：module\s+([A-Za-z_][A-Za-z0-9_]*)\s+where
    """
    pattern = r"module\s+([A-Za-z_][A-Za-z0-9_]*)\s+where"
    match = re.search(pattern, code)
    if match:
        return match.group(1)
    return None


def get_temp_filename(
    cryptol_code: str,
    module_name: Optional[str] = None,
    file_name: Optional[str] = None,
) -> str:
    """根据优先级确定临时文件名。"""
    if file_name:
        return file_name

    if module_name:
        if not module_name.endswith(".cry"):
            return f"{module_name}.cry"
        return module_name

    extracted_name = extract_module_name(cryptol_code)
    if extracted_name:
        return f"{extracted_name}.cry"

    random_id = str(uuid.uuid4())[:8]
    return f"temp_{random_id}.cry"


def get_temp_file_path(file_name: str) -> Path:
    """获取临时文件的完整路径。"""
    temp_dir = settings.PROJECT_ROOT / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir / file_name


@contextmanager
def managed_temp_file(code: str, file_name: Optional[str] = None):
    """上下文管理器：创建并管理临时Cryptol文件，确保清理。"""
    temp_filename = file_name or "temp.cry"
    temp_file_path = get_temp_file_path(temp_filename)

    try:
        temp_file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file_path.write_text(code, encoding="utf-8")
        logger.debug("已创建临时文件：%s", temp_file_path)
        yield temp_file_path
    finally:
        try:
            if temp_file_path.exists():
                temp_file_path.unlink()
                logger.debug("已删除临时文件：%s", temp_file_path)
        except Exception as exc:
            logger.warning("清理临时文件失败：%s error=%s", temp_file_path, str(exc))


def _is_warning_anchor(line: str) -> bool:
    """判断一行是否是 Cryptol warning 的起始行。"""
    return "[warning]" in line.lower()


def _is_error_anchor(line: str) -> bool:
    """判断一行是否是 Cryptol error 的起始行。

    Cryptol 3.3 的错误输出并不总是包含 `[error]`，例如：
    - `At ...: Type signature without a matching binding:`
    - `Parse error at ...`
    """
    stripped = line.strip()
    lowered = stripped.lower()

    if not stripped or _is_warning_anchor(line):
        return False

    return any(
        (
            "[error]" in lowered,
            lowered.startswith("parse error"),
            lowered.startswith("type signature without a matching binding"),
            bool(re.match(r"^at\s+.+:\d+:\d+.*:", stripped, re.IGNORECASE)),
        )
    )


def parse_compile_output(output: str) -> Tuple[bool, str, str, str]:
    """解析编译输出，分离 info、warning 和 error。"""
    lines = output.split("\n")
    has_error = any(_is_error_anchor(line) for line in lines)
    success = not has_error

    info_lines = []
    warning_lines = []
    error_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        if _is_warning_anchor(line):
            warning_block = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if _is_warning_anchor(next_line) or _is_error_anchor(next_line):
                    break
                if next_line and (next_line[0] in (" ", "\t")):
                    warning_block.append(next_line)
                    i += 1
                elif not next_line.strip():
                    warning_block.append(next_line)
                    i += 1
                else:
                    break

            warning_lines.extend(warning_block)

        elif _is_error_anchor(line):
            error_block = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if _is_warning_anchor(next_line) or _is_error_anchor(next_line):
                    break
                if next_line and (next_line[0] in (" ", "\t")):
                    error_block.append(next_line)
                    i += 1
                elif not next_line.strip():
                    error_block.append(next_line)
                    i += 1
                else:
                    break

            error_lines.extend(error_block)

        else:
            info_lines.append(line)
            i += 1

    info_text = "\n".join(info_lines).strip()
    warning_text = "\n".join(warning_lines).strip()
    error_text = "\n".join(error_lines).strip()

    return success, info_text, warning_text, error_text


def compile_cryptol_code(
    cryptol_code: str,
    module_name: Optional[str] = None,
    file_name: Optional[str] = None,
    cryptol_cmd: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Tuple[bool, str, str, str, str]:
    """编译 Cryptol 代码，直接调用本地Cryptol编译器。"""
    if not cryptol_code.strip():
        error_text = "Empty Cryptol source: refusing to compile blank output."
        logger.warning("编译输入为空，直接判定失败")
        return False, error_text, "", "", error_text

    cryptol_cmd = cryptol_cmd or settings.CRYPTOL_CMD
    timeout = timeout or settings.COMPILE_TIMEOUT
    temp_filename = get_temp_filename(cryptol_code, module_name, file_name)

    process = None
    try:
        with managed_temp_file(cryptol_code, temp_filename) as temp_file_path:
            relative_path = (
                temp_file_path.name
                if temp_file_path.parent == Path.cwd()
                else str(temp_file_path)
            )

            cmd = f":l {relative_path}"
            process = subprocess.Popen(
                [cryptol_cmd],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )

            try:
                stdout, _ = process.communicate(input=cmd + "\n:quit\n", timeout=timeout)
                compile_text = stdout.strip()
            except subprocess.TimeoutExpired:
                process.kill()
                logger.error("Cryptol编译超时")
                raise RuntimeError(f"Cryptol编译超时（{timeout}秒）")

    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("执行Cryptol失败：%s", str(exc))
        raise RuntimeError(f"执行Cryptol失败：{str(exc)}")

    success, info_text, warning_text, error_text = parse_compile_output(compile_text)

    logger.info("编译完成：success=%s", success)
    return success, compile_text, info_text, warning_text, error_text

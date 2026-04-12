"""函数元数据和文件操作工具。"""

import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from workflow.settings import settings


logger = logging.getLogger(__name__)


class FunctionInfo:
    """函数元数据薄包装，统一管理函数名和输出路径。"""

    def __init__(self, function_data: dict, json_file_path: str | None = None):
        """初始化函数信息。"""
        self.raw_data = function_data
        self.json_file_path = Path(json_file_path).resolve() if json_file_path else None
        self.name = self._sanitize_name()
        self.group = self._extract_group()

    def _sanitize_name(self) -> str:
        """从函数名提取合法的文件名。"""
        raw_name = str(self.raw_data.get("name", "")).strip()
        if not raw_name:
            raise ValueError("函数 JSON 缺少有效的 name 字段，无法生成输出文件名")

        sanitized_name = re.sub(r'[\\/:*?"<>|]', "_", raw_name)
        if sanitized_name != raw_name:
            logger.warning(
                "函数名包含非法文件名字符，已替换：raw=%s sanitized=%s",
                raw_name,
                sanitized_name,
            )
        return sanitized_name

    def _extract_group(self) -> str:
        """根据输入 JSON 路径推导输出分组，例如 FIPS203 -> fips203。"""
        if self.json_file_path is None:
            return "misc"

        for part in self.json_file_path.parts:
            if re.fullmatch(r"FIPS\d+", part, re.IGNORECASE):
                return part.lower()
        return "misc"

    def build_output_path(self, tag: Optional[str] = None) -> Path:
        """根据函数名和标签构造输出路径。"""
        output_dir = settings.CRYPTOL_OUTPUT_DIR / self.group
        output_dir.mkdir(parents=True, exist_ok=True)
        if tag:
            return output_dir / f"{self.name}_{tag}.cry"
        return output_dir / f"{self.name}.cry"

    def save_snapshot(self, code: str, tag: Optional[str] = None) -> Path:
        """保存某个阶段的 Cryptol 代码快照。"""
        output_path = self.build_output_path(tag)
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(code)
        logger.info("已保存代码版本：path=%s", output_path)
        return output_path


@contextmanager
def temp_cryptol_file(code: str, file_name: Optional[str] = None):
    """上下文管理器：创建临时 Cryptol 文件并在结束后清理。"""
    temp_dir = settings.LOGGER_DIR.parent / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    path = temp_dir / (file_name or "temp.cry")
    try:
        path.write_text(code, encoding="utf-8")
        yield path
    finally:
        path.unlink(missing_ok=True)
        logger.debug("已清理临时文件：%s", path)

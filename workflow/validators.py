"""数据验证模块。"""

from typing import Any, Optional
from pydantic import BaseModel, field_validator


class FunctionInput(BaseModel):
    """函数输入参数定义。"""

    name: str
    type: str
    description: Optional[str] = None


class FunctionOutput(BaseModel):
    """函数输出参数定义。"""

    name: str
    type: str
    description: Optional[str] = None


class FunctionData(BaseModel):
    """函数JSON数据验证模型。"""

    function_id: str
    name: str
    label: Optional[str] = None
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    body_raw: list[str] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证函数名不为空。"""
        if not v or not v.strip():
            raise ValueError("函数 name 不能为空")
        return v.strip()

    @field_validator("function_id")
    @classmethod
    def validate_function_id(cls, v: str) -> str:
        """验证函数ID不为空。"""
        if not v or not v.strip():
            raise ValueError("函数 function_id 不能为空")
        return v.strip()

    @field_validator("body_raw")
    @classmethod
    def validate_body(cls, v: list[str]) -> list[str]:
        """验证body_raw是字符串列表。"""
        if not isinstance(v, list):
            raise ValueError("body_raw 必须是列表")
        return [str(item).strip() for item in v if item]


class CryptolCompileRequest(BaseModel):
    """Cryptol 编译请求验证。"""

    cryptCode: str
    moduleName: Optional[str] = None
    fileName: Optional[str] = None

    @field_validator("cryptCode")
    @classmethod
    def validate_crypt_code(cls, v: str) -> str:
        """验证代码不为空。"""
        if not v or not v.strip():
            raise ValueError("cryptCode 不能为空")
        return v.strip()

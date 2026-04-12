"""模型工厂。"""

import os

from langchain_openai import ChatOpenAI

from workflow.settings import settings


def get_model() -> ChatOpenAI:
    """返回统一配置的兼容 OpenAI 接口模型实例。"""
    api_key = os.getenv(settings.LLM_API_KEY_ENV) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            f"未找到模型 API Key，请设置环境变量 {settings.LLM_API_KEY_ENV} 或 OPENAI_API_KEY"
        )

    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.LLM_BASE_URL,
        # timeout=settings.LLM_TIMEOUT,
    )

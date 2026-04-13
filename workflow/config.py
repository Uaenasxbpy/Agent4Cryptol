"""工作流配置兼容层，统一从 settings 导出当前仍在使用的配置。"""

from workflow.settings import settings

# === 向后兼容导出 ===
ROOT_DIR = settings.PROJECT_ROOT
RAG_DIR = settings.RAG_DIR
PROMPT_DIR = settings.PROMPT_DIR
LOGGER_DIR = settings.LOGGER_DIR
CRYPTOL_OUTPUT_DIR = settings.CRYPTOL_OUTPUT_DIR
LLM_MODEL = settings.LLM_MODEL
LLM_BASE_URL = settings.LLM_BASE_URL
LLM_API_KEY_ENV = settings.LLM_API_KEY_ENV
LLM_TIMEOUT = settings.LLM_TIMEOUT
CRYPTOL_CMD = settings.CRYPTOL_CMD
COMPILE_TIMEOUT = settings.COMPILE_TIMEOUT
MAX_RETRIES = settings.MAX_RETRIES
RETRY_DELAY = settings.RETRY_DELAY
ACTIVE_PARAMETER_SETS = settings.ACTIVE_PARAMETER_SETS

# === 默认输入 ===
DEFAULT_JSON_FILE = ROOT_DIR / "data" / "FIPS203" / "ir" / "functions" / "alg_012_base_case_multiply.json"

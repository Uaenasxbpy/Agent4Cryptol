"""RAG 检索与格式化工具，支持缓存。"""

import json
import re
from pathlib import Path
from typing import Optional

from workflow.config import RAG_DIR
from workflow.settings import settings


class RAGCache:
    """RAG数据缓存，避免重复读取JSONL文件。"""

    def __init__(self, enable_cache: bool = True):
        self.enable_cache = enable_cache
        self._rules_cache: Optional[list] = None
        self._patterns_cache: Optional[list] = None
        self._examples_cache: Optional[list] = None

    def get_rules(self) -> list:
        """懒加载语法规则。"""
        if not self.enable_cache or self._rules_cache is None:
            self._rules_cache = load_jsonl(RAG_DIR / "syntax_rules" / "syntax_rules.jsonl")
        return self._rules_cache

    def get_patterns(self) -> list:
        """懒加载代码模式。"""
        if not self.enable_cache or self._patterns_cache is None:
            self._patterns_cache = load_jsonl(
                RAG_DIR / "cryptol_patterns" / "cryptol_patterns.jsonl"
            )
        return self._patterns_cache

    def get_examples(self) -> list:
        """懒加载代码示例。"""
        if not self.enable_cache or self._examples_cache is None:
            self._examples_cache = load_jsonl(
                RAG_DIR / "cryptol_examples" / "cryptol_examples.jsonl"
            )
        return self._examples_cache

    def clear(self):
        """清空缓存。"""
        self._rules_cache = None
        self._patterns_cache = None
        self._examples_cache = None


# 全局缓存实例
_rag_cache = RAGCache(enable_cache=settings.RAG_ENABLE_CACHE)


def load_jsonl(path: Path) -> list:
    """读取 JSONL 文件，跳过格式不合法的行。"""
    records = []
    if not path.exists():
        return records

    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def extract_keywords(function_data: dict) -> set:
    """从函数 JSON 中提取关键词，供检索使用。"""
    keywords: set = set()

    name = function_data.get("name", "")
    words = re.findall(r"[A-Z][a-z]*|[a-z]+", name)
    keywords.update(word.lower() for word in words)

    body_text = " ".join(function_data.get("body_raw", [])).lower()
    domain_keywords = [
        "for", "loop", "array", "byte", "bit", "integer", "mod", "ntt",
        "shake", "hash", "xof", "sequence", "encode", "decode", "sample",
        "multiply", "inverse", "compress", "decompress", "keygen", "encrypt",
        "decrypt", "reduce", "transpose", "split", "join", "take", "drop",
        "fold", "recur", "permut", "substitut", "round", "schedule",
    ]
    for keyword in domain_keywords:
        if keyword in body_text or keyword in name.lower():
            keywords.add(keyword)

    for item in function_data.get("inputs", []) + function_data.get("outputs", []):
        if isinstance(item, dict):
            type_str = item.get("type", "").lower()
            keywords.update(re.findall(r"\b[a-z]\w*\b", type_str))

    return keywords


def score_record(record: dict, keywords: set) -> float:
    """根据关键词重叠度给 RAG 记录打分。"""
    text_parts = []
    for field in [
        "title", "rule", "intent", "pattern_summary", "explanation",
        "keywords", "retrieval_tags", "retrieval_text", "retrieval_hints",
        "applicable_when", "subtopic", "topic",
    ]:
        value = record.get(field, "")
        if isinstance(value, list):
            text_parts.append(" ".join(str(item) for item in value))
        elif isinstance(value, str):
            text_parts.append(value)

    combined = " ".join(text_parts).lower()
    score = sum(1 for keyword in keywords if keyword in combined)

    priority = record.get("priority", "low")
    if priority == "high":
        score += 2
    elif priority == "medium":
        score += 1

    return score


def format_syntax_rule(record: dict) -> str:
    """格式化语法规则片段。"""
    parts = [f"// [SyntaxRule] {record.get('title', '')}"]

    rule = record.get("rule", "")
    if rule:
        parts.append(f"// Rule: {rule}")

    positive_example = record.get("positive_example", "")
    if positive_example:
        parts.append(f"// Good:\n{positive_example}")

    negative_example = record.get("negative_example", "")
    if negative_example:
        parts.append(f"// Bad (avoid):\n{negative_example}")

    return "\n".join(parts)


def format_pattern(record: dict) -> str:
    """格式化代码模式片段。"""
    parts = [f"// [Pattern] {record.get('title', '')}"]

    intent = record.get("intent", "")
    if intent:
        parts.append(f"// Intent: {intent}")

    template = record.get("pattern_template", "")
    if template:
        parts.append(f"// Template:\n{template}")

    positive_example = record.get("positive_example", "")
    if positive_example and positive_example != template:
        parts.append(f"// Example:\n{positive_example}")

    return "\n".join(parts)


def format_example(record: dict) -> str:
    """格式化代码示例片段。"""
    parts = [f"// [Example] {record.get('title', '')}"]

    explanation = record.get("explanation", "")
    if explanation:
        parts.append(f"// {explanation}")

    code = record.get("code", "")
    if code:
        parts.append(code)

    return "\n".join(parts)


def extract_error_keywords(compile_error: str) -> set:
    """从编译错误文本中提取关键词，用于错误驱动的 RAG 检索。"""
    keywords: set = set()

    # 提取 not in scope / not defined 的符号名
    scope_matches = re.findall(r"`([^`]+)`\s+(?:is not|not)\s+(?:in scope|defined)", compile_error)
    for symbol in scope_matches:
        keywords.add(symbol.strip().lower())

    # 提取 parse error / type error / type mismatch 等分类词
    error_type_patterns = [
        r"\b(parse error)\b",
        r"\b(type mismatch)\b",
        r"\b(type error)\b",
        r"\b(expected type)\b",
        r"\b(not in scope)\b",
        r"\b(not defined)\b",
        r"\b(unexpected)\b",
    ]
    for pattern in error_type_patterns:
        if re.search(pattern, compile_error, re.IGNORECASE):
            keyword = re.search(pattern, compile_error, re.IGNORECASE).group(1).lower()
            keywords.update(keyword.split())

    # 提取错误中出现的 Cryptol 符号（camelCase 或 snake_case 标识符）
    identifiers = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]{2,})\b", compile_error)
    domain_relevant = {
        "shiftR", "shiftL", "fromIntegral", "fromInteger", "Integer",
        "sequence", "type", "signature", "module", "where", "let",
        "import", "foreign", "bit", "bitvector",
    }
    for ident in identifiers:
        if ident in domain_relevant:
            keywords.add(ident.lower())

    return keywords


def retrieve_rag_context(
    function_data: dict,
    top_k_rules: int | None = None,
    top_k_patterns: int | None = None,
    top_k_examples: int | None = None,
) -> str:
    """从三层知识库中检索最相关的上下文片段。

    Args:
        function_data: 函数数据
        top_k_rules: 检索的语法规则数（默认为settings配置值）
        top_k_patterns: 检索的代码模式数
        top_k_examples: 检索的代码示例数

    Returns:
        格式化的RAG上下文
    """
    top_k_rules = top_k_rules or settings.RAG_TOP_K_RULES
    top_k_patterns = top_k_patterns or settings.RAG_TOP_K_PATTERNS
    top_k_examples = top_k_examples or settings.RAG_TOP_K_EXAMPLES

    keywords = extract_keywords(function_data)

    # 使用缓存获取数据
    syntax_rules = _rag_cache.get_rules()
    patterns = _rag_cache.get_patterns()
    examples = _rag_cache.get_examples()

    top_rules = sorted(
        syntax_rules,
        key=lambda record: score_record(record, keywords),
        reverse=True,
    )[:top_k_rules]
    top_patterns = sorted(
        patterns,
        key=lambda record: score_record(record, keywords),
        reverse=True,
    )[:top_k_patterns]
    top_examples = sorted(
        examples,
        key=lambda record: score_record(record, keywords),
        reverse=True,
    )[:top_k_examples]

    sections = []
    if top_rules:
        sections.append("=== Syntax Rules ===")
        sections.extend(format_syntax_rule(record) for record in top_rules)

    if top_patterns:
        sections.append("\n=== Code Patterns ===")
        sections.extend(format_pattern(record) for record in top_patterns)

    if top_examples:
        sections.append("\n=== Code Examples ===")
        sections.extend(format_example(record) for record in top_examples)

    return "\n\n".join(sections)


def retrieve_rag_for_fix(
    compile_error: str,
    function_data: dict,
    top_k_rules: int | None = None,
    top_k_patterns: int | None = None,
    top_k_examples: int | None = None,
) -> str:
    """为修复节点检索 RAG 上下文：将错误关键词叠加到函数关键词上，优先返回与错误相关的规则。

    Args:
        compile_error: 编译器返回的错误文本
        function_data: 函数数据（用于补充函数上下文关键词）
        top_k_rules: 检索的语法规则数
        top_k_patterns: 检索的代码模式数
        top_k_examples: 检索的代码示例数

    Returns:
        格式化的 RAG 上下文
    """
    top_k_rules = top_k_rules or settings.RAG_TOP_K_RULES
    top_k_patterns = top_k_patterns or settings.RAG_TOP_K_PATTERNS
    top_k_examples = top_k_examples or settings.RAG_TOP_K_EXAMPLES

    # 关键词叠加：函数关键词（基础）+ 错误关键词（精准）
    function_keywords = extract_keywords(function_data)
    error_keywords = extract_error_keywords(compile_error)
    combined_keywords = function_keywords | error_keywords

    syntax_rules = _rag_cache.get_rules()
    patterns = _rag_cache.get_patterns()
    examples = _rag_cache.get_examples()

    # 错误关键词命中时额外加分，让错误相关规则优先排前
    def score_with_error_boost(record: dict) -> float:
        base_score = score_record(record, combined_keywords)
        error_boost = sum(2 for kw in error_keywords if kw in str(record).lower())
        return base_score + error_boost

    top_rules = sorted(syntax_rules, key=score_with_error_boost, reverse=True)[:top_k_rules]
    top_patterns = sorted(patterns, key=score_with_error_boost, reverse=True)[:top_k_patterns]
    top_examples = sorted(examples, key=score_with_error_boost, reverse=True)[:top_k_examples]

    sections = []
    if top_rules:
        sections.append("=== Syntax Rules ===")
        sections.extend(format_syntax_rule(record) for record in top_rules)

    if top_patterns:
        sections.append("\n=== Code Patterns ===")
        sections.extend(format_pattern(record) for record in top_patterns)

    if top_examples:
        sections.append("\n=== Code Examples ===")
        sections.extend(format_example(record) for record in top_examples)

    return "\n\n".join(sections)

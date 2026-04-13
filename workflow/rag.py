"""RAG 检索与格式化工具，支持缓存。"""

import json
import re
from pathlib import Path
from typing import Optional

from workflow.settings import settings


RAG_FILE_MAP = {
    "rules": "syntax_rules.jsonl",
    "rules_retrieval": "syntax_rules_retrieval.jsonl",
    "patterns": "cryptol_patterns.jsonl",
    "templates": "cryptol_templates.jsonl",
    "guardrails": "cryptol_guardrails.jsonl",
    "examples": "cryptol_examples.jsonl",
}


class RAGCache:
    """RAG 数据缓存，避免重复读取 JSONL 文件。"""

    def __init__(self, enable_cache: bool = True):
        self.enable_cache = enable_cache
        self._rules_cache: Optional[list] = None
        self._rules_retrieval_cache: Optional[list] = None
        self._patterns_cache: Optional[list] = None
        self._templates_cache: Optional[list] = None
        self._guardrails_cache: Optional[list] = None
        self._examples_cache: Optional[list] = None

    def _load_cached(self, cache_attr: str, filename: str) -> list:
        if not self.enable_cache or getattr(self, cache_attr) is None:
            setattr(self, cache_attr, load_jsonl(settings.RAG_DIR / filename))
        return getattr(self, cache_attr)

    def get_rules(self) -> list:
        """懒加载语法规则。"""
        return self._load_cached("_rules_cache", RAG_FILE_MAP["rules"])

    def get_rules_retrieval(self) -> list:
        """懒加载检索友好的语法规则。"""
        return self._load_cached(
            "_rules_retrieval_cache", RAG_FILE_MAP["rules_retrieval"]
        )

    def get_patterns(self) -> list:
        """懒加载代码模式。"""
        return self._load_cached("_patterns_cache", RAG_FILE_MAP["patterns"])

    def get_templates(self) -> list:
        """懒加载代码模板。"""
        return self._load_cached("_templates_cache", RAG_FILE_MAP["templates"])

    def get_guardrails(self) -> list:
        """懒加载生成/修复护栏规则。"""
        return self._load_cached("_guardrails_cache", RAG_FILE_MAP["guardrails"])

    def get_examples(self) -> list:
        """懒加载代码示例。"""
        return self._load_cached("_examples_cache", RAG_FILE_MAP["examples"])

    def clear(self):
        """清空缓存。"""
        self._rules_cache = None
        self._rules_retrieval_cache = None
        self._patterns_cache = None
        self._templates_cache = None
        self._guardrails_cache = None
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


def extract_keywords(function_data: dict) -> set[str]:
    """从函数 JSON 中提取关键词，供检索使用。"""
    keywords: set[str] = set()

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
        "guardrail", "scope", "template", "update", "tuple", "record",
    ]
    for keyword in domain_keywords:
        if keyword in body_text or keyword in name.lower():
            keywords.add(keyword)

    for item in function_data.get("inputs", []) + function_data.get("outputs", []):
        if isinstance(item, dict):
            type_str = item.get("type", "").lower()
            keywords.update(re.findall(r"\b[a-z]\w*\b", type_str))

    return keywords


def extract_error_keywords(compile_error: str) -> set[str]:
    """从编译错误文本中提取关键词，用于错误驱动的 RAG 检索。"""
    keywords: set[str] = set()
    error_text = compile_error.lower()

    scope_matches = re.findall(
        r"`([^`]+)`\s+(?:is not|not)\s+(?:in scope|defined)", compile_error
    )
    for symbol in scope_matches:
        keywords.add(symbol.strip().lower())

    phrase_patterns = [
        "parse error",
        "type mismatch",
        "type error",
        "expected type",
        "not in scope",
        "not defined",
        "unexpected",
        "expected a value named",
        "expected a type named",
        "boundaries of .. sequences",
        "value not in scope",
        "unsolvable constraint",
    ]
    for phrase in phrase_patterns:
        if phrase in error_text:
            keywords.update(phrase.split())

    identifiers = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]{2,})\b", compile_error)
    domain_relevant = {
        "shiftR", "shiftL", "fromIntegral", "fromInteger", "Integer",
        "sequence", "type", "signature", "module", "where", "let",
        "import", "foreign", "bit", "bitvector", "zext", "take",
        "drop", "split", "join", "undefined", "foldl", "foldr",
    }
    for ident in identifiers:
        if ident in domain_relevant:
            keywords.add(ident.lower())

    return keywords


def score_record(record: dict, keywords: set[str]) -> float:
    """根据关键词重叠度给 RAG 记录打分。"""
    text_parts = []
    for field in [
        "title",
        "rule",
        "intent",
        "pattern_summary",
        "explanation",
        "keywords",
        "retrieval_tags",
        "retrieval_text",
        "retrieval_hints",
        "applicable_when",
        "subtopic",
        "topic",
        "guardrail",
        "anti_pattern",
        "constraints",
        "notes",
        "template_code",
        "usage_notes",
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

    confidence = record.get("confidence", "low")
    if confidence == "high":
        score += 1
    elif confidence == "medium":
        score += 0.5

    return score


def format_syntax_rule(record: dict) -> str:
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


def format_guardrail(record: dict) -> str:
    parts = [f"// [Guardrail] {record.get('title', '')}"]

    guardrail = record.get("guardrail", "") or record.get("rule", "")
    if guardrail:
        parts.append(f"// Rule: {guardrail}")

    anti_pattern = record.get("anti_pattern", "")
    if anti_pattern:
        parts.append(f"// Avoid:\n{anti_pattern}")

    return "\n".join(parts)


def format_pattern(record: dict) -> str:
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


def format_template(record: dict) -> str:
    parts = [f"// [Template] {record.get('title', '')}"]

    usage_notes = record.get("usage_notes", "")
    if usage_notes:
        parts.append(f"// Notes: {usage_notes}")

    template_code = record.get("template_code", "")
    if template_code:
        parts.append(template_code)

    return "\n".join(parts)


def format_example(record: dict) -> str:
    parts = [f"// [Example] {record.get('title', '')}"]

    explanation = record.get("explanation", "")
    if explanation:
        parts.append(f"// {explanation}")

    code = record.get("code", "")
    if code:
        parts.append(code)

    return "\n".join(parts)


def _select_top(records: list, keywords: set[str], top_k: int) -> list:
    return sorted(
        records,
        key=lambda record: score_record(record, keywords),
        reverse=True,
    )[:top_k]


def _render_sections(
    rules: list,
    guardrails: list,
    patterns: list,
    templates: list,
    examples: list,
) -> str:
    sections = []

    if rules:
        sections.append("=== Syntax Rules ===")
        sections.extend(format_syntax_rule(record) for record in rules)

    if guardrails:
        sections.append("\n=== Guardrails ===")
        sections.extend(format_guardrail(record) for record in guardrails)

    if patterns:
        sections.append("\n=== Code Patterns ===")
        sections.extend(format_pattern(record) for record in patterns)

    if templates:
        sections.append("\n=== Code Templates ===")
        sections.extend(format_template(record) for record in templates)

    if examples:
        sections.append("\n=== Code Examples ===")
        sections.extend(format_example(record) for record in examples)

    return "\n\n".join(sections)


def retrieve_rag_context(
    function_data: dict,
    top_k_rules: int | None = None,
    top_k_guardrails: int | None = None,
    top_k_patterns: int | None = None,
    top_k_templates: int | None = None,
    top_k_examples: int | None = None,
) -> str:
    """生成阶段检索：rules_retrieval -> guardrails -> patterns -> templates -> examples。"""
    top_k_rules = top_k_rules or settings.RAG_TOP_K_RULES
    top_k_guardrails = top_k_guardrails or settings.RAG_TOP_K_GUARDRAILS
    top_k_patterns = top_k_patterns or settings.RAG_TOP_K_PATTERNS
    top_k_templates = top_k_templates or settings.RAG_TOP_K_TEMPLATES
    top_k_examples = top_k_examples or settings.RAG_TOP_K_EXAMPLES

    keywords = extract_keywords(function_data)

    rules = _rag_cache.get_rules_retrieval() or _rag_cache.get_rules()
    guardrails = _rag_cache.get_guardrails()
    patterns = _rag_cache.get_patterns()
    templates = _rag_cache.get_templates()
    examples = _rag_cache.get_examples()

    top_rules = _select_top(rules, keywords, top_k_rules)
    top_guardrails = _select_top(guardrails, keywords, top_k_guardrails)
    top_patterns = _select_top(patterns, keywords, top_k_patterns)
    top_templates = _select_top(templates, keywords, top_k_templates)
    top_examples = _select_top(examples, keywords, top_k_examples)

    return _render_sections(
        rules=top_rules,
        guardrails=top_guardrails,
        patterns=top_patterns,
        templates=top_templates,
        examples=top_examples,
    )


def retrieve_rag_for_fix(
    compile_error: str,
    function_data: dict,
    top_k_rules: int | None = None,
    top_k_guardrails: int | None = None,
    top_k_patterns: int | None = None,
    top_k_templates: int | None = None,
    top_k_examples: int | None = None,
) -> str:
    """修复阶段检索：error -> guardrails -> rules_retrieval -> patterns -> templates -> examples。"""
    top_k_rules = top_k_rules or settings.RAG_TOP_K_RULES
    top_k_guardrails = top_k_guardrails or settings.RAG_TOP_K_GUARDRAILS
    top_k_patterns = top_k_patterns or settings.RAG_TOP_K_PATTERNS
    top_k_templates = top_k_templates or settings.RAG_TOP_K_TEMPLATES
    top_k_examples = top_k_examples or settings.RAG_TOP_K_EXAMPLES

    function_keywords = extract_keywords(function_data)
    error_keywords = extract_error_keywords(compile_error)
    combined_keywords = function_keywords | error_keywords

    rules = _rag_cache.get_rules_retrieval() or _rag_cache.get_rules()
    guardrails = _rag_cache.get_guardrails()
    patterns = _rag_cache.get_patterns()
    templates = _rag_cache.get_templates()
    examples = _rag_cache.get_examples()

    def score_with_error_boost(record: dict) -> float:
        base_score = score_record(record, combined_keywords)
        record_text = json.dumps(record, ensure_ascii=False).lower()
        error_boost = sum(2 for kw in error_keywords if kw in record_text)
        return base_score + error_boost

    top_rules = sorted(rules, key=score_with_error_boost, reverse=True)[:top_k_rules]
    top_guardrails = sorted(
        guardrails, key=score_with_error_boost, reverse=True
    )[:top_k_guardrails]
    top_patterns = sorted(
        patterns, key=score_with_error_boost, reverse=True
    )[:top_k_patterns]
    top_templates = sorted(
        templates, key=score_with_error_boost, reverse=True
    )[:top_k_templates]
    top_examples = sorted(
        examples, key=score_with_error_boost, reverse=True
    )[:top_k_examples]

    return _render_sections(
        rules=top_rules,
        guardrails=top_guardrails,
        patterns=top_patterns,
        templates=top_templates,
        examples=top_examples,
    )

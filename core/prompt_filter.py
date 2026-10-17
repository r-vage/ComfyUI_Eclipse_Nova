# Shared whole-tag and prose filtering for prompt text nodes.

import re

from .regex_helper import is_tags_format, smart_phrase_removal

_FILTER_TOKEN_PATTERN = re.compile(r"\*|[^*_\s]+")
_WORD_SLOT_PATTERN = r"[^\W_]+(?:[-'][^\W_]+)*"
_TOKEN_SEPARATOR_PATTERN = r"[ \t_]+"
_LEFT_TOKEN_BOUNDARY = r"(?<![\w'-])"
_RIGHT_TOKEN_BOUNDARY = r"(?![\w'-])"


def normalize_parentheses(text: str) -> str:
    # Treat escaped and unescaped prompt parentheses as equivalent.
    text = re.sub(r"\\*\(", "(", text)
    return re.sub(r"\\*\)", ")", text)


def compile_literal_token(token: str) -> str:
    escaped = re.escape(token)
    return escaped.replace(r"\(", r"\\*\(").replace(r"\)", r"\\*\)")


def compile_filter_patterns(raw_patterns: list[str]) -> list[re.Pattern[str]]:
    sortable_patterns: list[tuple[int, int, re.Pattern[str]]] = []
    for raw_pattern in raw_patterns:
        tokens = _FILTER_TOKEN_PATTERN.findall(normalize_parentheses(raw_pattern))
        if not tokens:
            continue
        wildcard_count = tokens.count("*")
        token_patterns = [
            _WORD_SLOT_PATTERN if token == "*" else compile_literal_token(token)
            for token in tokens
        ]
        body = _TOKEN_SEPARATOR_PATTERN.join(token_patterns)
        regex = re.compile(
            _LEFT_TOKEN_BOUNDARY + body + _RIGHT_TOKEN_BOUNDARY,
            re.IGNORECASE,
        )
        sortable_patterns.append((len(tokens), wildcard_count, regex))

    # Prefer longer matches, then exact phrases over wildcard phrases.
    sortable_patterns.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in sortable_patterns]


def filter_tag_prompt(text: str, patterns: list[re.Pattern[str]]) -> str:
    # Remove complete tag fields so a match never leaves a partial tag.
    prompt_parts = re.split(r"([,\n])", text)
    for index in range(0, len(prompt_parts), 2):
        tag = prompt_parts[index].strip(" \t")
        if tag and any(pattern.fullmatch(tag) for pattern in patterns):
            prompt_parts[index] = ""
    return cleanup_prompt("".join(prompt_parts))


def cleanup_prompt(text: str) -> str:
    # Normalize horizontal whitespace and commas while preserving newlines.
    text = re.sub(r"[ \t]*,[ \t]*(?:[ \t]*,[ \t]*)*", ", ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = []
    for line in text.split("\n"):
        line = line.strip(" \t,")
        if line:
            lines.append(line)
    return "\n".join(lines)


def filter_prompt(input_string: str | None, filters: str | None) -> str:
    if not isinstance(input_string, str) or not input_string.strip():
        return ""
    # No filters means the original prompt passes through verbatim.
    if not isinstance(filters, str) or not filters.strip():
        return input_string

    raw_patterns = [part.strip() for line in filters.split("\n") for part in line.split(",") if part.strip()]
    patterns = compile_filter_patterns(raw_patterns)
    if is_tags_format(input_string):
        return filter_tag_prompt(input_string, patterns)
    return smart_phrase_removal(input_string, patterns, "filter_prompt")

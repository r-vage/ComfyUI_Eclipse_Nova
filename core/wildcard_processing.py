# Shared layout-preserving wildcard expansion and quoted substitutions.

import re

from .logger import log
from .wildcard_engine import process

_LOG_PREFIX = "Wildcard List"
_ASSIGNMENT_RE = re.compile(
    r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"((?:\\["\\]|[^"])*)"\s*$',
    re.DOTALL,
)
_REFERENCE_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
_ESCAPE_RE = re.compile(r'\\(["\\])')


def _split_substitution_assignments(text: str) -> list[str]:
    assignments: list[str] = []
    current: list[str] = []
    in_quotes = False
    index = 0

    while index < len(text):
        char = text[index]
        if in_quotes and char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if following in {'"', "\\"}:
                current.extend((char, following))
                index += 2
                continue
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
        elif not in_quotes and char in {",", "\n", "\r"}:
            segment = "".join(current).strip()
            if segment:
                assignments.append(segment)
            current.clear()
            if char == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                index += 1
        else:
            current.append(char)
        index += 1

    segment = "".join(current).strip()
    if segment:
        assignments.append(segment)
    return assignments


def parse_substitutions(text: str | None) -> dict[str, str]:
    if not isinstance(text, str) or not text.strip():
        return {}

    assignments = _split_substitution_assignments(text)
    substitutions: dict[str, str] = {}
    malformed = 0

    for assignment in assignments:
        match = _ASSIGNMENT_RE.fullmatch(assignment)
        if match is None:
            malformed += 1
            continue
        key, raw_value = match.groups()
        substitutions[key] = _ESCAPE_RE.sub(r"\1", raw_value)

    if malformed:
        log.warning(
            _LOG_PREFIX,
            f"Ignored {malformed} malformed substitution assignment(s)",
        )
    return substitutions


def apply_substitutions(text: str, substitutions: dict[str, str]) -> str:
    return _REFERENCE_RE.sub(
        lambda match: substitutions.get(match.group(1), match.group(0)), text
    )


def _protect_substitution_references(text: str) -> tuple[str, list[tuple[str, str]]]:
    protected: list[tuple[str, str]] = []

    def replace_reference(match: re.Match) -> str:
        token = f"\0ECLIPSE_SUBSTITUTION_{len(protected)}\0"
        protected.append((token, match.group(0)))
        return token

    return _REFERENCE_RE.sub(replace_reference, text), protected


def prompt_lines(text: str) -> list[str]:
    # ComfyUI needs an item to map downstream inputs, even for a blank prompt.
    return [line for line in text.splitlines() if line.strip()] or [""]


def expand_prompt(text: str, seed: int, substitutions: str | None = None) -> str:
    substituted = apply_substitutions(text, parse_substitutions(substitutions))
    protected_source, references = _protect_substitution_references(substituted)
    result = process(protected_source, seed=seed, preserve_layout=True)
    for token, reference in references:
        result = result.replace(token, reference)
    return result

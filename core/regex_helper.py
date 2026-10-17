# Regex helper utilities for text pattern analysis and content normalization

import re
import os
import json
from typing import Optional, Dict, Any
from .logger import log

_LOG_PREFIX = "RegexHelper"

# ============================================================================
# NSFW Detection - Loaded from nsfw.json
# ============================================================================

# Cache for NSFW patterns (loaded once from JSON)
_nsfw_patterns_cache: Optional[Dict[str, Any]] = None
_nsfw_json_mtime: float = 0.0


def _get_nsfw_patterns() -> Dict[str, Any]:
    # Load NSFW patterns from nsfw.json with caching.
    # Returns dict with 'x_rated' and 'mature' lists of terms.
    global _nsfw_patterns_cache, _nsfw_json_mtime

    # Find nsfw.json path — uses repo patterns/ folder directly
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(repo_dir, "patterns", "nsfw.json")

    if not os.path.exists(json_path):
        log.warning(_LOG_PREFIX, "nsfw.json not found, using empty patterns")
        return {"x_rated": [], "mature": []}

    # Check if file changed (reload if needed)
    try:
        current_mtime = os.path.getmtime(json_path)
    except OSError:
        current_mtime = 0.0

    if _nsfw_patterns_cache is not None and current_mtime == _nsfw_json_mtime:
        return _nsfw_patterns_cache

    # Load and parse JSON
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        components = data.get("components", {})
        detection_levels = data.get("detection_levels", {})

        # Build term lists from detection_levels mapping
        x_rated_terms = []
        mature_terms = []

        for component_name in detection_levels.get("x_rated", []):
            x_rated_terms.extend(components.get(component_name, []))

        for component_name in detection_levels.get("mature", []):
            mature_terms.extend(components.get(component_name, []))

        _nsfw_patterns_cache = {"x_rated": x_rated_terms, "mature": mature_terms}
        _nsfw_json_mtime = current_mtime

        log.debug(
            _LOG_PREFIX,
            f"Loaded NSFW patterns from {json_path}: {len(x_rated_terms)} X-rated, {len(mature_terms)} Mature terms",
        )
        return _nsfw_patterns_cache

    except Exception as e:
        log.error(_LOG_PREFIX, f"Error loading nsfw.json: {e}")
        return {"x_rated": [], "mature": []}


# ============================================================================
# Text Format Detection
# ============================================================================


def is_tags_format(text: str) -> bool:
    """
    Detect if text is in tag format (comma-separated) vs prose format.

    Tag format examples:
    - "1girl, long hair, blue eyes, standing"
    - "masterpiece, best quality, outdoor, sunset"

    Prose format examples:
    - "A young woman with long hair and blue eyes standing in a field."
    - "The image shows a beautiful sunset over the mountains."

    Args:
        text: Input text to analyze

    Returns:
        True if tag format, False if prose format
    """
    if not text or len(text.strip()) < 10:
        return False

    # Count commas vs periods
    comma_count = text.count(",")
    period_count = text.count(".")

    # Tag format typically has many commas and few/no periods
    # Prose has more periods and fewer commas
    if comma_count > 3 and period_count <= 1:
        return True

    # Check for common tag-style patterns
    # Tags are typically short phrases without articles
    has_articles = bool(re.search(r"\b(a|an|the)\s+", text, re.IGNORECASE))
    has_verbs = bool(
        re.search(r"\b(is|are|was|were|has|have|shows|depicts)\s+", text, re.IGNORECASE)
    )

    # If has many commas but no articles/verbs, likely tags
    if comma_count > 2 and not has_articles and not has_verbs:
        return True

    # If has articles and verbs, likely prose
    if has_articles and has_verbs:
        return False

    # Default to prose if unclear
    return False


def smart_phrase_removal(text: str, patterns: list, removal_type: str) -> str:
    """
    Remove phrases while maintaining grammar and readability.

    Handles:
    - Comma cleanup after removal
    - Leading/trailing punctuation
    - Extra whitespace
    - Grammar preservation (e.g., "A image of X" removal leaves proper grammar)

    Args:
        text: Input text
        patterns: List of compiled regex patterns to remove
        removal_type: Type of removal for logging (e.g., 'image_styles', 'nsfw')

    Returns:
        Text with phrases removed and grammar cleaned up
    """
    if not text:
        return text

    original = text

    # Apply all pattern removals
    for pattern in patterns:
        text = pattern.sub("", text)

    # Grammar cleanup
    # Remove double commas
    text = re.sub(r",\s*,", ",", text)
    # Remove comma before period
    text = re.sub(r",\s*\.", ".", text)
    # Remove leading comma/space
    text = re.sub(r"^\s*,\s*", "", text)
    # Remove trailing comma
    text = re.sub(r",\s*$", "", text)
    # Collapse multiple spaces
    text = re.sub(r"\s{2,}", " ", text)
    # Fix spacing around punctuation
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)

    # Trim
    text = text.strip()

    if text != original:
        log.debug(
            _LOG_PREFIX,
            f"Smart removal ({removal_type}): {len(original) - len(text)} chars removed",
        )

    return text


def detect_nsfw_level(text: str) -> str:
    # Detect NSFW level based on content keywords from nsfw.json.
    #
    # Levels:
    # - "X": Explicit adult content (sexual acts, genitalia, explicit nudity)
    # - "Mature": Suggestive/mature content (revealing clothing, nudity, suggestive poses)
    # - "None": Safe for work content
    #
    # Args:
    #     text: Input text to analyze
    #
    # Returns:
    #     One of: "X", "Mature", "None"
    if not text:
        return "None"

    text_lower = text.lower()

    # Load patterns from nsfw.json (cached)
    patterns = _get_nsfw_patterns()

    # Check for X-rated content first (explicit)
    for term in patterns.get("x_rated", []):
        # Escape special regex chars and add word boundaries
        escaped = re.escape(term)
        pattern = rf"\b{escaped}\b"
        if re.search(pattern, text_lower):
            log.debug(_LOG_PREFIX, f"Detected X-rated content: matched '{term}'")
            return "X"

    # Check for Mature content (suggestive)
    for term in patterns.get("mature", []):
        escaped = re.escape(term)
        pattern = rf"\b{escaped}\b"
        if re.search(pattern, text_lower):
            log.debug(_LOG_PREFIX, f"Detected Mature content: matched '{term}'")
            return "Mature"

    # No NSFW content detected
    return "None"


def validate_nsfw_level(level: str) -> str:
    """
    Validate and normalize NSFW level string.

    Args:
        level: Input level string

    Returns:
        Normalized level: "X", "Mature", or "None"
    """
    if not level:
        return "None"

    level_upper = level.upper()

    if level_upper in ("X", "EXPLICIT", "ADULT"):
        return "X"
    elif level_upper in ("MATURE", "M", "SUGGESTIVE"):
        return "Mature"
    else:
        return "None"

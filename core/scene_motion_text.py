"""Keep reference appearance clauses out of transferred scene movement."""
import re

from .regex_helper import smart_phrase_removal

_COLORS = r"(?:black|white|gr[ae]y|brown|blue|green|red|yellow|orange|purple|pink|teal|blond[e]?|brunette|auburn|ginger|silver|golden|platinum)"
_HAIR_DETAILS = rf"(?:{_COLORS}|long|short|curly|wavy|straight|braided|dark|light)"
_PERSON = r"(?:woman|man|girl|boy|person|subject|performer)"
_STATIC_PREFIX = re.compile(r"^(?:against|in front of|background\b|setting\b|lighting\b)", re.IGNORECASE)
_IDENTITY_PREFIX = re.compile(rf"^(?:(?:a|an|the|young|older|adult)\s+)*{_PERSON}\s+(?:with|has|having)\b", re.IGNORECASE)
# Clothing may be a bare noun phrase in audit metadata but a wearing clause in
# the generated paragraph. Its removal must not depend on those strings matching.
# Stop before attached pose/action clauses instead of consuming "with arms crossed".
_POSE_PART = r"(?:hands?|arms?|fingers?|head|eyes?|legs?|feet|shoulders?|mouth|teeth|gaze)\b"
_POSE_VERB = (
    r"(?:stands?|standing|sits?|sitting|seated|holds?|holding|raises?|raising|"
    r"lowers?|lowering|moves?|moving|turns?|turning|looks?|looking|smiles?|smiling|"
    r"leans?|leaning|keeps?|keeping|maintains?|maintaining|nods?|nodding|"
    r"crosses|crossing|folds?|folding|points?|pointing|reaches?|reaching|"
    r"grasps?|grasping|touches|touching)\b"
)
_WORN_CLAUSE = re.compile(
    r"(?:,\s*)?\b(?:(?:is|are)\s+)?(?:wear(?:s|ing)?|dressed in|clad in)\s+"
    # "Wearing a broad smile" is an expression, not a source outfit.
    r"(?!(?:[\w-]+\s+){0,3}(?:smile|grin|frown|expression)\b)"
    r"[^,;.!?]+?"
    rf"(?=\s+(?:with\s+(?:(?:their|the|a|an|both|one|left|right|raised|crossed)\s+)*{_POSE_PART}|"
    rf"(?:and\s+)?{_POSE_VERB}|while\b|as\b|then\b)|[,;.!?]|$)"
    r",?(?P<conjunction>\s+and\s+)?", re.IGNORECASE,
)
_STATIC_BACKGROUND = re.compile(
    r"(?:,\s*)?\b(?:against|in front of|with)\s+(?:(?:a|an|the)\s+)?"
    rf"(?:(?:plain|neutral|simple|solid|dark|bright|{_COLORS})\s+)*(?:background|backdrop)\b",
    re.IGNORECASE,
)
_PIERCING_DETAIL = re.compile(
    r"\b(?:nose|septum|lip|eyebrow|ear)\s+(?:rings?|studs?|piercings?)"
    r"(?:\s+(?:present|visible)|\s+in\s+(?:the\s+)?(?:left|right)\s+nostril)?\b", re.IGNORECASE,
)
_PERFORMANCE_LABELS = re.compile(
    r"\b(?:framing|camera(?: motion)?|(?:start|end|opening|final) pose(?:, already present)?|"
    r"motion|actions?(?: in order)?|expression|gaze(?: and expression)?)\s*:", re.IGNORECASE,
)
_ROUTINE_LIPS = re.compile(
    r"\b(?:mouth|lips?)\s+(?:(?:repeatedly|rhythmically)\s+)?"
    r"(?:open(?:s|ing)?\s+(?:and|then)\s+clos(?:e[sd]?|ing)|"
    r"clos(?:e[sd]?|ing)\s+(?:and|then)\s+open(?:s|ing)?)\b"
    r"|\bopen(?:s|ing)?\s+(?:and|then)\s+clos(?:e[sd]?|ing)\s+"
    r"(?:(?:the|their|her|his)\s+)?(?:mouth|lips?)\b", re.IGNORECASE,
)
_DISTINCT_MOUTH_GESTURE = re.compile(
    r"\b(?:yawn\w*|laugh\w*|pout\w*|purs\w*|kiss\w*|grimac\w*|snarl\w*|"
    r"tongue|chew\w*|bit(?:e|es|ing)|blow\w*|whistl\w*|gasp\w*)\b", re.IGNORECASE,
)
_OTHER_PERFORMANCE = re.compile(
    r"\b(?:hands?|fingers?|arms?|shoulders?|head|body|gaze|eyes?|brows?|eyebrows?|"
    r"nose|torso|legs?|feet|camera|framing|close[- ]up|portrait|"
    r"look(?:s|ing)?|glanc\w*|stares?|staring|turn(?:s|ing)?|tilt\w*|nod\w*|"
    r"lean\w*|sway\w*|shrug\w*|blink\w*|wink\w*|smil\w*|frown\w*|"
    r"waves|waving|points|pointing)\b", re.IGNORECASE,
)


def performance_prompt_issue(text):
    """Validate the public scene paragraph contract without rebuilding audit fields."""
    if not isinstance(text, str) or not text.strip():
        return "performance_prompt is required; rerun Scene Motion Analysis"
    if len(text.split()) > 80:
        return "performance_prompt exceeds 80 words; rerun with a concise visual performance paragraph"
    if "\n" in text.strip() or _PERFORMANCE_LABELS.search(text):
        return "performance_prompt must be one natural paragraph without field labels or lists"
    return None


def performance_motion_text(text, appearances=()):
    """Clean the supplied paragraph without synthesizing a prompt from audit data."""
    text = motion_only_text(text, appearances)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentence for sentence in sentences if not (
        _ROUTINE_LIPS.search(sentence) and not _DISTINCT_MOUTH_GESTURE.search(sentence)
        and not _OTHER_PERFORMANCE.search(sentence)))


def _neutral_features(text):
    # Keep the body part and its movement: blue eyes widen -> eyes widen.
    text = re.sub(rf"\b(?:{_HAIR_DETAILS}\s+)+hair\b", "hair", text, flags=re.IGNORECASE)
    text = re.sub(rf"\b(?:{_COLORS}\s+)+(eyes?|skin)\b", r"\1", text, flags=re.IGNORECASE)
    return re.sub(
        r"\bhair\s+(?:(?:tied|styled|pulled)\s+)?(?:up\s+)?in\s+"
        r"(?:(?:a|an|one|two|high|low|messy|tight|top|\d+)\s+)*(?:buns?|ponytails?|pigtails?|braids?|top\s*knot)\b",
        "hair", text, flags=re.IGNORECASE,
    )


def _remove_worn_clause(match):
    conjunction = match.group("conjunction")
    # "The subject is clad in X and raises a hand" -> "The subject raises a hand".
    # Keep the conjunction when another predicate already precedes the outfit.
    if conjunction and not re.search(r"\b(?:the subject|they)\s*$", match.string[:match.start()], re.IGNORECASE):
        return conjunction
    return " "


def motion_only_text(text, appearances=()):
    """Remove copied appearance clauses; preserve pose, contact and expression.

    Source appearance is audit metadata, never a prompt. Matching its descriptive
    clauses also handles saved analyses made before the motion-only task policy.
    This is bounded text cleanup, not a general semantic appearance classifier.
    """
    text = _neutral_features(" ".join(text.split()))
    text = smart_phrase_removal(text, [_PIERCING_DETAIL], "scene appearance")
    clauses = set()
    garments = set()
    for appearance in appearances:
        appearance = _neutral_features(" ".join(appearance.split()))
        for clause in re.split(r"[,;.]\s*", appearance):
            clause = clause.strip()
            if _STATIC_PREFIX.match(clause) or _IDENTITY_PREFIX.match(clause):
                clauses.add(clause)
                # Clothing details may be absent from a contaminated pose.
                if _STATIC_PREFIX.match(clause):
                    clauses.add(re.split(r"\s+with\s+", clause, maxsplit=1, flags=re.IGNORECASE)[0])
        for match in re.finditer(r"\b(?:wearing|dressed in|clad in)\s+(?:a\s+|an\s+|the\s+)?([^,;.]+)", appearance, re.IGNORECASE):
            garment = re.split(r"\s+(?:with|and)\s+", match[1], maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if garment:
                garments.add(garment)
    for clause in sorted(clauses, key=len, reverse=True):
        pattern = re.compile(r"\b(?:(?:a|an|the)\s+)?" + re.escape(clause) + r"(?!\w)", re.IGNORECASE)
        if _IDENTITY_PREFIX.match(clause):
            text = re.sub(pattern.pattern + r"(?:,\s*)?", "the subject ", text, flags=re.IGNORECASE)
        else:
            text = smart_phrase_removal(text, [pattern], "scene appearance")
    text = _WORN_CLAUSE.sub(_remove_worn_clause, text)
    text = smart_phrase_removal(text, [_STATIC_BACKGROUND], "scene appearance")
    # Preserve clothing contact without requesting the reference video's garment.
    for garment in sorted(garments, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(garment) + r"\b", "clothing", text, flags=re.IGNORECASE)
    text = re.sub(rf"\b(?:(?:young|older|adult)\s+)*{_PERSON}\b", "subject", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:her|his)\s+(?=(?:hands?|head|hair|eyes?|face|arms?|legs?|body)\b)", "their ", text, flags=re.IGNORECASE)
    # A removed identity prefix must not leave an empty subject-only pose clause.
    empty_subject = re.compile(r"(?:^|(?<=[;.]))\s*(?:(?:a|an|the)\s+)?subject\s*(?=[;.]|$)", re.IGNORECASE)
    text = smart_phrase_removal(text, [empty_subject], "scene appearance")
    return text.strip(" ,;")

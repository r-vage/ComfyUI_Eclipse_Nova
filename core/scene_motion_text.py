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
    r"grasps?|grasping|touches|touching|tilts?|tilting|steps?|stepping|walks?|walking|"
    r"faces?|facing|extends?|extending|lifts?|lifting|waves?|waving|blinks?|blinking)\b"
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


# Apply the stricter policy only when exporting source text for a separate
# reference image. The saved response and the user's global direction are independent.
_MOUTH = (
    r"mouth(?:s|ed|ing)?|lip(?:s|ped|stick)?|lip[- ]?sync\w*|teeth|tooth\w*|tongue\w*|jaws?|"
    r"smil(?:e[sd]?|ing)|grin(?:s|ned|ning)?|smirk\w*|snarl\w*|grimac\w*|"
    r"pout\w*|pucker\w*|laugh\w*|yawn\w*|kiss(?:es|ed|ing)?|"
    r"speaks?|speaking|sings?|singing|speech|oral articulation"
)
_GARMENT = (
    r"shirts?|t[- ]?shirts?|hoodies?|sweaters?|sweatshirts?|jackets?|coats?|blazers?|"
    r"dress(?:es)?|sleeves?|collars?|blouses?|skirts?|trousers|pants|jeans|leggings|shorts|"
    r"(?:tank|crop|tube) tops?|costumes?|uniforms?|scar(?:f|ves)|hats?|beanies"
)
_OUTFIT_OR_HAIR = (
    r"hair(?:style|cut|do|line)?s?|bangs|fringe|ponytails?|pigtails?|braids?|"
    r"buns?|dreadlocks?|afro|beard\w*|moustache\w*|mustache\w*|wigs?|"
    rf"clothing|clothes|outfits?|attire|garments?|{_GARMENT}|"
    r"necklaces?|earrings?|headphones|sunglasses|glasses"
)
_EXCLUDED = re.compile(rf"\b(?:{_MOUTH}|{_OUTFIT_OR_HAIR})\b", re.IGNORECASE)
_HAIR_ON_SUBJECT = re.compile(
    rf"\b(?:(?:{_HAIR_DETAILS})[- ]haired|blond[e]?|brunette|redheaded)\s+(?=subject\b)", re.IGNORECASE,
)
_DRESSED_SUBJECT = re.compile(
    rf"\b((?:a |the )?subject|they)\s+(?:with|in)\s+[^,;.!?]{{0,120}}?\b(?:{_OUTFIT_OR_HAIR})\b"
    rf"\s+(?={_POSE_VERB})", re.IGNORECASE,
)
_HAIR_LANDMARK = re.compile(
    r"\b((?:touch(?:es|ing)?|brush(?:es|ing)?|grasp(?:s|ing)?)\s+)(?:(?:their|the)\s+)?"
    r"hair\s+(?=(?:near|beside|above|below|behind)\s+)", re.IGNORECASE,
)
_HAIR_GESTURE = re.compile(
    r"\b((?:brush|push)(?:es|ed|ing)?|sweep(?:s|ing)?|swept|tuck(?:s|ed|ing)?|"
    r"pull(?:s|ed|ing)?|flip(?:s|ped|ping)?)\s+(?:(?:their|the)\s+)?(?:hair|bangs|ponytail|braids?)\s+"
    r"(?=back\b|aside\b|up(?:ward)?\b|down(?:ward)?\b|away\b|behind\b|over\b)", re.IGNORECASE,
)
_FABRIC_CONTACT = re.compile(
    rf"\b((?:hold(?:s|ing)?|grip(?:s|ping)?|tug(?:s|ging)?|pull(?:s|ing)?)\s+(?:(?:on|at)\s+)?)"
    rf"(?:(?:their|the|a|an)\s+)?(?:{_COLORS}\s+)?(?:{_GARMENT})(?:\s+sleeves?)?\b", re.IGNORECASE,
)
_MOUTH_CONTACT = re.compile(
    r"\b((?:cover(?:s|ing|ed)?|touch(?:es|ing|ed)?)\s+|"
    r"(?:hands?|fingers?)\s+(?:(?:moves?|raised?|rises?|up)\s+){0,2}(?:to|toward[s]?|near|over|across|in front of)\s+)"
    r"(?:(?:the|their)\s+)?(?:mouth|lips?)\b",
    re.IGNORECASE,
)
_EXPRESSION_ADJECTIVES = re.compile(
    r"\b(gentle|wide|broad|relaxed|subtle|playful|tight|slight|sustained),\s+"
    rf"(?=(?:[\w-]+ ){{1,2}}(?:{_MOUTH})\b)", re.IGNORECASE,
)
_LINK_WORD = r"(?:and|or|but|while|when|as|before|after|then|with|in|into|behind|beneath|showing|revealing)"
_LINKED_PHRASE = re.compile(rf"(?:^|\s+{_LINK_WORD}\s+)(.+?)(?=\s+{_LINK_WORD}\s+|$)", re.IGNORECASE)
_INITIAL_LINK = re.compile(r"^(?:and|with|while|as)\s+", re.IGNORECASE)
_TRANSFER_CUE = re.compile(
    rf"\b(?:{_POSE_VERB}|head|torso|body|face|hands?|wrists?|palms?|fingers?|arms?|"
    r"shoulders?|legs?|knees?|feet|chin|temple|gaze|eyes?|eyed|eyebrows?|brows?|"
    r"cheeks?|nose|forehead|facial|expression|grip\w*|tug\w*|fabric|"
    r"camera|shot|close[- ]up|framing|pan\w*|zoom\w*|leans?|glanc\w*|sweeps?|"
    r"static|centered|forward|upright|crouch\w*|kneel\w*|jump\w*|pivot\w*|spin\w*|danc\w*|kick\w*|"
    r"fists?|elbows?|hips?|ankles?|maintain\w* eye contact)\b", re.IGNORECASE,
)
_BODY_ACTION = re.compile(
    rf"\b(?:hands?|fingers?|arms?|head|torso|legs?|knees?|shoulders?|eyes?|brows?|face)\s+"
    rf"(?:(?:is|are|slowly|slightly)\s+)?{_POSE_VERB}", re.IGNORECASE,
)


def has_source_detail(text):
    return bool(_EXCLUDED.search(text))


def _transfer_clause(clause):
    if not _EXCLUDED.search(clause):
        return clause
    # A negative inventory does not establish a positive action.
    if re.match(r"(?:no\b|without\b)", clause, re.IGNORECASE):
        return ""
    # Keep contiguous clean phrases in their original order. Independent motion
    # can occur on either side of a disallowed phrase in the same sentence.
    retained = []
    start = None
    stop = 0
    for phrase in _LINKED_PHRASE.finditer(clause):
        part = phrase[1]
        if _EXCLUDED.search(part):
            if start is not None:
                retained.append(clause[start:stop])
            start = None
            # An inseparable action (such as a hand holding an ambiguously
            # described object) is more useful to the editor than a missing gesture.
            if _BODY_ACTION.search(part):
                retained.append(part)
        elif start is not None or _TRANSFER_CUE.search(part):
            # Colour, texture or an implied oral action cannot restart a subject
            # that was removed ("hair falls straight and smooth over their shoulders").
            if start is None and re.match(r"(?:smooth|straight|wavy|curly)\b", part, re.IGNORECASE):
                continue
            if start is None:
                start = phrase.start(1)
            stop = phrase.end(1)
    if start is not None:
        retained.append(clause[start:stop])
    return ", ".join(retained)


def transferred_scene_text(text, appearances=()):
    """Keep recognized motion in source prose. An empty result requests manual review."""
    text = motion_only_text(text, appearances)
    text = _HAIR_ON_SUBJECT.sub("", text)
    text = _DRESSED_SUBJECT.sub(r"\1 ", text)
    # Keep observed contact with an anatomical landmark without copying styling.
    text = _HAIR_LANDMARK.sub(r"\1the area ", text)
    text = _HAIR_GESTURE.sub(r"\1 ", text)
    text = _FABRIC_CONTACT.sub(r"\1the fabric", text)
    text = _MOUTH_CONTACT.sub(r"\1the lower face", text)
    if not _EXCLUDED.search(text):
        return text if re.search(r"\w", text) else ""
    # An adjective pair can belong to one excluded noun ("a relaxed, content smile").
    text = _EXPRESSION_ADJECTIVES.sub(r"\1 ", text)
    chunks = []
    for match in re.finditer(r"([^.;!?]+)([.;!?]*)", text):
        sentence, punctuation = match.groups()
        if _EXCLUDED.search(sentence):
            clauses = []
            follows_exclusion = False
            for clause in sentence.split(","):
                clean = _transfer_clause(clause.strip())
                if clean and (not follows_exclusion or _TRANSFER_CUE.search(clean)):
                    if not clauses and follows_exclusion:
                        clean = _INITIAL_LINK.sub("", clean)
                        if sentence.lstrip()[:1].isupper():
                            clean = clean[:1].upper() + clean[1:]
                    clauses.append(clean)
                follows_exclusion = not clean
            sentence = ", ".join(clauses)
        if sentence.strip():
            chunks.append(sentence.strip() + punctuation)
    return " ".join(chunks).rstrip(" ,;")

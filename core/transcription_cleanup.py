# Remove the observed Whisper attribution artifact from recognition only.
import copy
import re

_ARTIFACT = re.compile(r"(?<!\w)satsang[\W_]+with[\W_]+mooji(?!\w)", re.IGNORECASE)
_EDGES = " \t\r\n.,;:!?—–-\"'()[]"


def filter_recognition_artifacts(segments):
    cleaned, removed = [], []
    for index, source in enumerate(segments, 1):
        words = source.get("words") or []
        text = source.get("text", " ".join(word["word"] for word in words))
        matches = list(_ARTIFACT.finditer(text))
        if not matches:
            cleaned.append(source)
            continue
        segment = copy.deepcopy(source)
        removed.append({"segment": index, "text": source.get("text", text),
                        "reason": "known Whisper attribution artifact: Satsang with Mooji"})
        segment["text"] = _ARTIFACT.sub("", text).strip()
        if not text[:matches[0].start()].strip(_EDGES):
            segment["text"] = segment["text"].lstrip(_EDGES)
        if not text[matches[-1].end():].strip(_EDGES):
            segment["text"] = segment["text"].rstrip(_EDGES)
        if not any(char.isalnum() for char in segment["text"]):
            continue
        if words:
            # Match over the word stream so all three words lose their timing,
            # while surrounding lyrics keep their original observed intervals.
            joined = " ".join(word["word"] for word in words)
            spans = [(match.start(), match.end()) for match in _ARTIFACT.finditer(joined)]
            kept, offset = [], 0
            for word in segment["words"]:
                value = word["word"]
                remaining = "".join(char for i, char in enumerate(value, offset)
                                    if not any(start <= i < end for start, end in spans))
                offset += len(value) + 1
                if any(char.isalnum() for char in remaining):
                    word["word"] = remaining
                    kept.append(word)
            segment["words"] = kept
            if kept:
                segment.update(start=kept[0].get("start"), end=kept[-1].get("end"))
        cleaned.append(segment)
    return cleaned, removed

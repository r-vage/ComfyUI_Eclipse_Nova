# Optional Qwen word timing with verified local models and first-use download.
import copy
import gc
import hashlib
import json
import math
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from threading import Lock

import folder_paths

from .logger import log
from .lyric_cache import TimingCache, audio_key
from .lyric_timing import (
    analysis_audio,
    audio_data,
    from_alignment,
    timing_coverage,
    validate_timing,
)

REVISION = "qwen-word-timing-v1"
MODEL_ID = "Qwen/Qwen3-ForcedAligner-0.6B-hf"
MODEL_REVISION = "c07281df297b9905d24a508279258cccf987a064"
CHOICES = {"whisper": "Whisper", "qwen3_compare": "Qwen3 · compare only", "qwen3": "Qwen3"}
TIP = ("Whisper keeps the existing timing. Qwen3 retimes supported phrases with the local forced aligner; "
       "compare only keeps the existing timestamps and puts Qwen's estimates in the report. "
       "The first Qwen run downloads missing model files (about 1.85 GB for a full install). "
       "Singing accuracy varies: review disagreements. Manual corrected timing always takes priority.")
LANGUAGES = {"en": "English", "zh": "Chinese", "yue": "Cantonese", "fr": "French", "de": "German",
             "it": "Italian", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian", "es": "Spanish"}
MODEL_HASHES = {
    "model.safetensors": ("sha256", "00568245ceca5af1991d28562a75fe1ddc9bfeb041c27fda66947ea05c47fb86"),
    "tokenizer.json": ("sha256", "cadfb9cbd9ff8f4e309075ec6a71b063295ff796afb4b5dbc0fd2873fbb301f2"),
    "config.json": ("git", "74b91ca23584bdebd82ffaaeb21f72444baa2dd8"),
    "processor_config.json": ("git", "a07dff48032bed341260501d6688036c6fd7f3ef"),
    "tokenizer_config.json": ("git", "aa62b6c06ab8a704dc0895420fb1d2515954a49c"),
    "chat_template.jinja": ("git", "1d6020e0ee6f66499d674a3fc2bbae5a99482c0e"),
}
_CACHE = TimingCache()
_MARKER = "eclipse_word_timing"
_DOWNLOAD_LOCK = Lock()


def model_path():
    return Path(folder_paths.models_dir) / "qwen3_forced_aligner" / "Qwen3-ForcedAligner-0.6B-hf"


def model_identity():
    return tuple((name, p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                 for name in MODEL_HASHES if (p := model_path() / name).is_file())


@lru_cache(maxsize=2)
def _verify(root, identity):
    if len(identity) != len(MODEL_HASHES):
        raise ValueError("Missing Qwen3 ForcedAligner files. Follow the optional Qwen setup in Readme/Lyric_Captions.md.")
    for name, (kind, expected) in MODEL_HASHES.items():
        path = Path(root) / name
        digest = hashlib.sha256() if kind == "sha256" else hashlib.sha1()
        if kind == "git":
            digest.update(f"blob {path.stat().st_size}\0".encode())
        with path.open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"Unverified Qwen3 artifact: {name}. Download the documented pinned revision.")
    return root


def ensure_model():
    import comfy.model_management as mm

    mm.throw_exception_if_processing_interrupted()
    # Concurrent node executions recheck after the first installer completes.
    # Hub's own per-file locks and .incomplete files also protect other processes.
    with _DOWNLOAD_LOCK:
        mm.throw_exception_if_processing_interrupted()
        root = model_path()
        missing = [name for name in MODEL_HASHES if not (root / name).is_file()]
        if missing:
            try:
                from huggingface_hub import hf_hub_download
                from huggingface_hub.utils import tqdm
            except ImportError as error:
                raise RuntimeError("Qwen3 download requires requirements-qwen.txt. Install it with ComfyUI's Python and restart.") from error

            interrupted = False

            def check_interrupted():
                nonlocal interrupted
                if interrupted:
                    raise mm.InterruptProcessingException()
                try:
                    mm.throw_exception_if_processing_interrupted()
                except mm.InterruptProcessingException:
                    interrupted = True
                    raise

            class DownloadProgress(tqdm):
                def update(self, n=1):
                    check_interrupted()
                    return super().update(n)

            log.msg("QwenWordTiming", f"Downloading {len(missing)} missing Qwen3 model files to {root}; a full install is about 1.85 GB.")
            try:
                root.mkdir(parents=True, exist_ok=True)
                for name in missing:
                    check_interrupted()
                    hf_hub_download(repo_id=MODEL_ID, filename=name, revision=MODEL_REVISION,
                                    local_dir=root, endpoint="https://huggingface.co", token=False,
                                    tqdm_class=DownloadProgress)
            except mm.InterruptProcessingException:
                raise
            except Exception as error:
                # Some transfer backends wrap a progress callback's exception.
                check_interrupted()
                raise RuntimeError("Could not download Qwen3 ForcedAligner. Check internet access, free disk space and model-folder permissions, then retry; completed files are reused. For offline setup see Readme/Lyric_Captions.md.") from error
            check_interrupted()
        verified = _verify(str(root), model_identity())
        if missing:
            log.msg("QwenWordTiming", "Qwen3 model download verified; subsequent runs use the local files.")
        return verified


@contextmanager
def aligner(device):
    import comfy.model_management as mm
    import torch

    mm.throw_exception_if_processing_interrupted()
    try:
        from transformers import AutoModelForTokenClassification, AutoProcessor
        from transformers.models.qwen3_asr import (
            Qwen3ASRForTokenClassification,  # noqa: F401
        )
    except ImportError as error:
        raise RuntimeError("Qwen3 word timing requires the optional requirements-qwen.txt dependencies. Restart ComfyUI after installing them.") from error
    target = "cuda" if device == "auto" and torch.cuda.is_available() else ("cpu" if device == "auto" else device)
    if target not in ("cpu", "cuda") or (target == "cuda" and not torch.cuda.is_available()):
        raise ValueError("Qwen3 requires an available CPU or CUDA device.")
    root = ensure_model()
    dtype = torch.float32 if target == "cpu" else (torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)
    model = processor = None
    try:
        if target == "cuda":
            # Leave room for the longest supported phrase window as well as weights.
            mm.free_memory(5 * 1024**3, torch.device("cuda", torch.cuda.current_device()))
        processor = AutoProcessor.from_pretrained(root, local_files_only=True, trust_remote_code=False)
        model = AutoModelForTokenClassification.from_pretrained(
            root, local_files_only=True, trust_remote_code=False, dtype=dtype, attn_implementation="sdpa",
        ).to(target).eval()

        def predict(samples, text, language):
            mm.throw_exception_if_processing_interrupted()
            inputs, words = processor.prepare_forced_aligner_inputs(audio=samples, transcript=text, language=language)
            inputs = inputs.to(model.device, model.dtype)
            with torch.inference_mode():
                output = model(**inputs)
                result = processor.decode_forced_alignment(
                    logits=output.logits, input_ids=inputs["input_ids"], word_lists=words,
                    timestamp_token_id=model.config.timestamp_token_id,
                )[0]
            mm.throw_exception_if_processing_interrupted()
            return result

        yield predict
    finally:
        model = processor = None
        gc.collect()
        if target == "cuda":
            mm.soft_empty_cache()


def _normalized(text):
    return "".join(c for c in text.casefold() if c.isalnum())


def candidate_line(line, predictions, start, end, duration, language):
    # The official tokenizer strips punctuation and may split CJK characters.
    # Map its units back to exact source spans; never replace the user's wording.
    text = line["text"]
    positions = [i for i, char in enumerate(text) for c in char.casefold() if c.isalnum()]
    if not predictions or "".join(_normalized(p["text"]) for p in predictions) != _normalized(text):
        raise ValueError("Qwen tokens do not match the complete phrase.")
    words, cursor, previous, character_end = [], 0, start, 0
    for prediction in predictions:
        count = len(_normalized(prediction["text"]))
        if not count:
            raise ValueError("Qwen returned an empty word.")
        a, b = positions[cursor], positions[cursor + count - 1] + 1
        cursor += count
        while a > character_end and not text[a - 1].isspace() and not text[a - 1].isalnum():
            a -= 1
        while b < len(text) and not text[b].isspace() and not text[b].isalnum():
            b += 1
        left, right = prediction["start_time"], prediction["end_time"]
        if (type(left) not in (float, int) or type(right) not in (float, int)
                or not math.isfinite(left) or not math.isfinite(right)):
            raise ValueError("Qwen returned non-finite timestamps.")
        left, right = round(start + left, 6), round(start + right, 6)
        if not previous <= left < right <= end + 0.001:
            raise ValueError("Qwen returned zero-length, overlapping or out-of-window words.")
        words.append({"word": text[a:b], "start": left, "end": min(right, end)})
        previous, character_end = right, b
    return from_alignment(text, {"segments": [{"words": words}]}, duration, language)["lines"][0]


def _digest(data):
    content = {k: v for k, v in data.items() if k != _MARKER}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def refine_timing(audio, data, mode="whisper", device="auto", vocals=None, language="Auto"):
    import comfy.model_management as mm

    if mode not in CHOICES:
        raise ValueError("Select Whisper, Qwen3, or Qwen3 compare-only word timing.")
    if mode == "whisper":
        return data, None
    data = validate_timing(data)
    if not any(line["start"] is not None for key in ("lines", "extra_occurrences", "transcribed_passages")
               for line in data.get(key, [])):
        return data, {"mode": mode, "skipped": "No timed phrases to refine.", "warnings": []}
    selected_language = data.get("language") if language == "Auto" else language
    if selected_language not in LANGUAGES:
        raise ValueError("Qwen3 word timing supports en, zh, yue, fr, de, it, ja, ko, pt, ru and es. Select a supported language or Whisper.")
    source, source_name = analysis_audio(audio, vocals)
    identity = (audio_key(audio, vocals), selected_language, device, MODEL_REVISION, REVISION)
    marker = {"identity": list(identity), "digest": _digest(data)}
    if mode == "qwen3" and data.get(_MARKER) == marker:
        return data, {"mode": mode, "reused": True, "warnings": []}
    key = (*identity, str(model_path()), model_identity(), marker["digest"], mode)
    cached = _CACHE.get(key)
    mm.throw_exception_if_processing_interrupted()
    if cached is not None:
        cached[1]["cache_hit"] = True
        return cached
    import torchaudio.functional as AF

    waveform, rate = audio_data(source)
    samples = AF.resample(waveform.mean(0), rate, 16000).numpy()
    duration = min(data["duration"], len(samples) / 16000)
    output = copy.deepcopy(data)
    lines = sorted((line for name in ("lines", "extra_occurrences", "transcribed_passages")
                    for line in output.get(name, []) if line["start"] is not None), key=lambda line: line["start"])
    # Snapshot bounds before retiming so earlier predictions cannot move later windows.
    windows = [(max(0, line["start"] - 1, (lines[i - 1]["end"] + line["start"]) / 2 if i else 0),
                min(duration, line["end"] + 1, (line["end"] + lines[i + 1]["start"]) / 2 if i + 1 < len(lines) else duration))
               for i, line in enumerate(lines)]
    report = {"mode": mode, "model": MODEL_ID, "model_revision": MODEL_REVISION, "algorithm_revision": REVISION,
              "analysis_source": source_name, "cache_hit": False, "phrases": [], "warnings": []}
    began = time.monotonic()
    with aligner(device) as predict:
        for index, (line, (start, end)) in enumerate(zip(lines, windows), 1):
            mm.throw_exception_if_processing_interrupted()
            record = {"phrase": index, "text": line["text"], "original_words": copy.deepcopy(line["words"]), "applied": False}
            report["phrases"].append(record)
            if not 0 < end - start <= 300:
                record["rejected"] = "Phrase window is empty or exceeds Qwen's five-minute limit."
                continue
            if timing_coverage([line])["partial_lines"]:
                record["rejected"] = "Partial reference: keep supported words without forcing an unheard continuation."
                continue
            offset, stop = round(start * 16000), round(end * 16000)
            start, end = offset / 16000, stop / 16000
            predictions = predict(samples[offset:stop], line["text"], LANGUAGES[selected_language])
            record["window"] = [start, end]
            # Relative predictions remain diagnostic even when a line is rejected.
            record["predictions"] = [
                {key: None if isinstance(value, float) and not math.isfinite(value) else value
                 for key, value in prediction.items()}
                for prediction in predictions
            ]
            try:
                candidate = candidate_line(line, predictions, start, end, data["duration"], selected_language)
                if timing_coverage([candidate])["partial_lines"]:
                    raise ValueError("Qwen did not provide timing for the complete phrase.")
                record["candidate_words"] = candidate["words"]
                old_by_span = {(w["char_start"], w["char_end"]): w for w in line["words"] if w["start"] is not None}
                record["disagreements"] = [
                    {"text": word["text"], "original_start": old["start"], "qwen_start": word["start"]}
                    for word in candidate["words"]
                    if (old := old_by_span.get((word["char_start"], word["char_end"]))) is not None
                    and abs(word["start"] - old["start"]) >= 0.5
                ]
                if mode == "qwen3":
                    # Validate against neighbors, including already accepted candidates.
                    original = dict(line)
                    line.update(candidate)
                    try:
                        validate_timing(output)
                    except ValueError:
                        line.clear()
                        line.update(original)
                        raise
                    record["applied"] = True
            except ValueError as error:
                record["rejected"] = str(error)
    report["elapsed_seconds"] = round(time.monotonic() - began, 3)
    report["warnings"].append("Qwen forced alignment is a model estimate, not an accuracy score. Singing and sustained notes can disagree with Whisper; review the preview and per-phrase report.")
    if any("rejected" in record for record in report["phrases"]):
        report["warnings"].append("Rejected Qwen phrases retain their original timing; no timestamps were invented for missing words.")
    if mode == "qwen3":
        output[_MARKER] = {"identity": list(identity), "digest": _digest(output)}
    mm.throw_exception_if_processing_interrupted()
    # First-use download changes the file identity; the next queue should hit
    # the cache immediately, just like an installation that was already present.
    key = (*identity, str(model_path()), model_identity(), marker["digest"], mode)
    _CACHE.put(key, (output, report))
    log.msg("QwenWordTiming", f"{mode}: {len(lines)} phrases in {report['elapsed_seconds']:.2f}s.")
    return output, report

# Review text during the current queue without rerunning its source.

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from uuid import uuid4

WIDGET_TYPE = "ECLIPSE_NOVA_PROMPT_REVIEW"
MAX_TEXT_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 8 * MAX_TEXT_BYTES
MAX_PROMPTS = 2048
DEFAULT_CONFIGURATION = json.dumps({"version": 1, "pause": False, "source": "", "edits": []})


def validate_texts(values):
    if not isinstance(values, list) or len(values) > MAX_PROMPTS or any(not isinstance(v, str) for v in values):
        raise ValueError(f"Expected a list of at most {MAX_PROMPTS} text prompts.")
    if sum(len(value.encode("utf-8")) for value in values) > MAX_TEXT_BYTES:
        raise ValueError("Prompt text exceeds the 1 MB review limit.")
    return list(values)


def validate_configuration(raw):
    if isinstance(raw, list) and len(raw) == 1:
        raw = raw[0]
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValueError("Invalid prompt review configuration size.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid prompt review configuration JSON.") from error
    if (not isinstance(config, dict) or config.keys() != {"version", "pause", "source", "edits"}
            or type(config["version"]) is not int or config["version"] != 1
            or type(config["pause"]) is not bool or not isinstance(config["source"], str)
            or not re.fullmatch(r"(?:[a-f0-9]{64})?", config["source"])):
        raise ValueError("Invalid prompt review configuration fields.")
    validate_texts(config["edits"])
    return config


def prepare_review(prompts, first_prompt, config):
    prompts = validate_texts(prompts if prompts is not None else [])
    has_first = first_prompt is not None
    if has_first and (not isinstance(first_prompt, list) or len(first_prompt) != 1):
        raise ValueError("Connect exactly one first prompt; connect prompt lists to prompts.")
    originals = validate_texts((first_prompt if has_first else []) + prompts)
    source = hashlib.sha256(json.dumps([has_first, originals], ensure_ascii=False).encode("utf-8")).hexdigest()
    # Pause off is an exact passthrough, including after a previous edited run.
    edits = config["edits"] if config["pause"] and config["source"] == source else originals
    if len(edits) != len(originals):
        edits = originals
    return {"source": source, "has_first": has_first, "originals": originals, "texts": list(edits)}


def outputs(packet):
    texts = packet["texts"]
    first = texts[0] if packet["has_first"] else ""
    prompts = texts[1:] if packet["has_first"] else texts
    return list(prompts), first


@dataclass
class Review:
    packet: dict
    client_id: str
    event: threading.Event = field(default_factory=threading.Event)
    action: str | None = None
    texts: list | None = None


class ReviewBroker:
    # Only text and per-queue tokens cross the worker/server thread boundary.

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}

    def begin(self, packet, *, client_id, prompt_id, node_id, workflow_id):
        review = Review({**packet, "token": uuid4().hex, "prompt_id": prompt_id,
                         "node_id": node_id, "workflow_id": workflow_id, "status": "waiting"}, client_id)
        with self._lock:
            self._pending[review.packet["token"]] = review
        return review

    def pending(self, client_id, workflow_id):
        with self._lock:
            return [r.packet for r in self._pending.values()
                    if r.client_id == client_id and r.packet["workflow_id"] == workflow_id and r.action is None]

    def decide(self, *, token, prompt_id, client_id, action, texts=None):
        if action not in {"continue", "cancel"}:
            raise ValueError("Choose Continue or Cancel.")
        if action == "continue":
            texts = validate_texts(texts)
        with self._lock:
            review = self._pending.get(token)
            if (review is None or review.action is not None or review.client_id != client_id
                    or review.packet["prompt_id"] != prompt_id):
                return False
            if action == "continue":
                if len(texts) != len(review.packet["originals"]):
                    raise ValueError("Keep one text entry per incoming prompt, in the original order.")
                for before, after in zip(review.packet["originals"], texts, strict=True):
                    if before.strip() and not after.strip():
                        raise ValueError("A nonempty prompt cannot be cleared; reset it or enter replacement text.")
            review.action, review.texts = action, texts
            review.event.set()
        return True

    def close(self, review):
        with self._lock:
            self._pending.pop(review.packet["token"], None)

    def wait(self, review, check_interrupt):
        try:
            while not review.event.wait(.1):
                check_interrupt()
            check_interrupt()
            if review.action == "cancel":
                from comfy.model_management import InterruptProcessingException

                raise InterruptProcessingException()
            return {**review.packet, "texts": review.texts, "status": "continued"}
        finally:
            self.close(review)


broker = ReviewBroker()


def review_prompts(packet, hidden):
    from comfy.model_management import throw_exception_if_processing_interrupted
    from comfy_execution.utils import get_executing_context
    from server import PromptServer

    server = getattr(PromptServer, "instance", None)
    client_id = getattr(server, "client_id", None)
    context = get_executing_context()
    if context is None or not client_id:
        raise ValueError("Pause requires a ComfyUI client. Disable Pause for unattended runs.")
    node_id = str(hidden.unique_id)
    if hidden.dynprompt is not None:
        node_id = str(hidden.dynprompt.get_display_node_id(node_id))
    workflow_id = (hidden.extra_pnginfo or {}).get("workflow", {}).get("id")
    review = broker.begin(packet, client_id=client_id, prompt_id=context.prompt_id,
                          node_id=node_id, workflow_id=workflow_id)
    try:
        server.send_sync("eclipse-nova.prompt-review", review.packet, client_id)
        return broker.wait(review, throw_exception_if_processing_interrupted)
    finally:
        broker.close(review)
        server.send_sync("eclipse-nova.prompt-review", {
            "token": review.packet["token"], "prompt_id": context.prompt_id,
            "node_id": node_id, "workflow_id": workflow_id, "status": "closed",
        }, client_id)

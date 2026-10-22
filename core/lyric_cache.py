# Bounded caches keep only serialized timing data, never waveforms or models.
import hashlib
import json
import threading
from collections import OrderedDict

from .lyric_timing import audio_data


def audio_key(*sources):
    digest = hashlib.sha256()
    for source in sources:
        if source is None:
            digest.update(b"absent")
            continue
        waveform, rate = audio_data(source)
        digest.update(str((rate, tuple(waveform.shape))).encode())
        for channel in waveform:
            for chunk in channel.split(1024 * 1024):
                digest.update(chunk.contiguous().numpy().tobytes())
    return digest.hexdigest()


class TimingCache:
    def __init__(self, max_entries=8, max_bytes=16 * 1024 * 1024):
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._items = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key):
        with self._lock:
            payload = self._items.get(key)
            if payload is not None:
                self._items.move_to_end(key)
        return json.loads(payload) if payload is not None else None

    def put(self, key, value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if len(payload) > self.max_bytes:
            return
        with self._lock:
            self._items[key] = payload
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries or sum(map(len, self._items.values())) > self.max_bytes:
                self._items.popitem(last=False)

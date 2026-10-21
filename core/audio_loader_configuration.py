# Versioned configuration for the Load Audio panel. Trim inputs override local seconds.

import json

from .audio_loading import SOURCES
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET = "ECLIPSE_NOVA_LOAD_AUDIO"
SECONDS = number("Seconds", 0.0, 0.0, 86400.0, 0.1)


def default_configuration():
    return {"version": 1, "audio": "", "source": "Auto", "start_time": 0.0, "duration": 0.0, "stop": False}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Audio configuration must be a JSON string of at most 16 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid audio configuration JSON.") from error
    require_fields(config, default_configuration())
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 audio configuration.")
    if not isinstance(config["audio"], str) or len(config["audio"]) > 4096 or "\x00" in config["audio"]:
        raise ValueError("Invalid audio filename.")
    require_choice(config["source"], SOURCES, "Source")
    if type(config["stop"]) is not bool:
        raise ValueError("Stop must be enabled or disabled.")
    for name in ("start_time", "duration"):
        require_number(config[name], SECONDS)
    return config


def resolved_trim(config, start_time=None, duration=None):
    values = (config["start_time"] if start_time is None else start_time,
              config["duration"] if duration is None else duration)
    for value in values:
        require_number(value, SECONDS)
    return values

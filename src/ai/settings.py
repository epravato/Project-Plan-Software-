import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "settings.json"

DEFAULTS = {
    "ai_provider": "ollama",
    "anthropic_api_key": "",
    "context_paths": [
        {"label": "H2M Standards", "path": r"J:\AIR AI Taskforce\EAP\Projects\Project plan software"},
    ],
}


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return {**DEFAULTS, **data}


def save_settings(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")

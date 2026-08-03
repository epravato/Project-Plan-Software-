import json
from pathlib import Path

import keyring

SETTINGS_PATH = Path(__file__).parent.parent.parent / "data" / "settings.json"
# The API key lives in the OS credential store (Windows Credential Manager), never in
# settings.json or anywhere else on disk in plaintext.
KEYRING_SERVICE = "h2m-project-plan-software"
KEYRING_USERNAME = "anthropic_api_key"

DEFAULTS = {
    "ai_provider": "ollama",
    "context_paths": [
        {"label": "H2M Standards", "path": r"J:\AIR AI Taskforce\EAP\Projects\Project plan software"},
    ],
}


def load_settings() -> dict:
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) if SETTINGS_PATH.exists() else {}
    settings = {**DEFAULTS, **data}
    stored_key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    legacy_key = data.get("anthropic_api_key")
    if not stored_key and legacy_key:
        # One-time migration for a key saved before the keyring switch — move it into
        # the credential store, then scrub it from the file via save_settings below.
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, legacy_key)
        stored_key = legacy_key
        save_settings({**settings, "anthropic_api_key": legacy_key})
    settings["anthropic_api_key"] = stored_key or ""
    return settings


def save_settings(settings: dict):
    key = settings.get("anthropic_api_key")
    if key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key)
    on_disk = {k: v for k, v in settings.items() if k != "anthropic_api_key"}
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(on_disk, indent=2), encoding="utf-8")

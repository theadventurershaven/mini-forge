"""mini-forge: photo or description to a printable tabletop miniature."""

import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _version() -> str:
    try:
        return json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


__version__ = _version()

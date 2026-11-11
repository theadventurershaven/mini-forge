"""Write the mini-forge overlays as Bambu Studio user process presets.

Import them in Bambu Studio with File > Import > Import Configs. Run from the repo root:
    uv run --project plugins/mini-forge python scripts/export_bambu_presets.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAYS = ROOT / "plugins/mini-forge/mini_forge/overlays"
OUT = ROOT / "bambu-presets"
VERSION = "2.8.0.5"  # Bambu Studio 02.08 profile version

TITLES = {
    "standard-0.4": "mini-forge 0.12mm slim trees (0.4 nozzle)",
    "creature-0.4-stout": "mini-forge 0.12mm stout trees (0.4 nozzle)",
    "standard-0.4-stout": "mini-forge 0.12mm stout trees, plate only (0.4 nozzle)",
    "detail-0.2-slim": "mini-forge 0.06mm slim trees (0.2 nozzle)",
    "detail-0.2-stout": "mini-forge 0.06mm stout trees (0.2 nozzle)",
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for path in sorted(OVERLAYS.glob("*.json")):
        overlay = json.loads(path.read_text(encoding="utf-8"))
        name = TITLES[path.stem]
        preset = {k: v for k, v in overlay.items() if not k.startswith("_") and k not in ("type", "name")}
        preset.update({"from": "User", "name": name, "print_settings_id": name, "version": VERSION})
        preset = dict(sorted(preset.items()))
        (OUT / f"{name}.json").write_text(json.dumps(preset, indent=4) + "\n", encoding="utf-8")
        print(OUT / f"{name}.json")


if __name__ == "__main__":
    main()

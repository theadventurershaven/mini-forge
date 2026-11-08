"""Build complete slicer profiles on this computer from the installed Bambu Studio.

mini-forge ships only its own setting changes ("overlays", in `overlays/`). Bambu's full
profiles and start/end G-code come from the user's Bambu Studio install, so nothing of
Bambu's is redistributed and profiles always match the installed version.

Two Bambu Studio CLI behaviours make this necessary (found on 02.08.02):
1. The CLI drops a machine profile's `include` list, so the printer's start/end G-code
   never reaches the output (no bed levelling, no purge line). `setup` inlines them.
2. Profile inheritance can silently fall back to generic defaults (200 C nozzle, cool
   plate). Every slice therefore gets fully resolved profiles, saved next to the job.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import BED_TYPES, OVERLAY_DIR, Settings, profile_dir, system_profile_dir

GCODE_KEYS = ("machine_start_gcode", "machine_end_gcode", "time_lapse_gcode",
              "change_filament_gcode", "layer_change_gcode", "machine_pause_gcode")


class ProfileError(ValueError):
    pass


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _index(system_dir: Path, kind: str) -> dict[str, Path]:
    category = system_dir / kind
    if not category.is_dir():
        raise ProfileError(f"Bambu Studio system profiles not found at {category}")
    return {p.stem: p for p in category.rglob("*.json")}


def resolve(data: dict, system_dir: Path, origin: str = "profile") -> dict:
    """Merge a profile with its complete chain of system parents and includes."""
    kind = data.get("type")
    if kind not in {"machine", "process", "filament"}:
        raise ProfileError(f"unsupported profile type in {origin}: {kind!r}")
    index = _index(system_dir, kind)

    def walk(own: dict, name: str, visiting: tuple[str, ...]) -> dict:
        if name in visiting:
            raise ProfileError(f"cyclic profile inheritance: {name}")
        result: dict = {}
        for parent in ([own["inherits"]] if own.get("inherits") else []) + own.get("include", []):
            if parent not in index:
                raise ProfileError(f"{name}: Bambu system profile {parent!r} not found in this Bambu Studio")
            result.update(walk(_load(index[parent]), parent, (*visiting, name)))
        result.update(own)
        result.pop("include", None)
        return result

    return walk(data, origin, ())


def _single(values: dict) -> dict:
    """Collapse per-extruder lists whose entries are identical (CLI loads them more reliably)."""
    for key, value in list(values.items()):
        if isinstance(value, list) and len(value) > 1 and all(v == value[0] for v in value):
            values[key] = [value[0]]
    return values


def nozzle_tag(nozzle: float) -> str:
    return f"{nozzle:g}"


def system_machine_name(settings: Settings, nozzle: float) -> str:
    return f"{settings.printer_model} {nozzle_tag(nozzle)} nozzle"


def machine_name(settings: Settings, nozzle: float) -> str:
    return f"mini-forge {settings.printer_model.removeprefix('Bambu Lab ')} {nozzle_tag(nozzle)} nozzle"


def build_machine(settings: Settings, nozzle: float) -> Path:
    system_dir = system_profile_dir(settings.slicer_path)
    index = _index(system_dir, "machine")
    leaf = system_machine_name(settings, nozzle)
    if leaf not in index:
        raise ProfileError(f"no Bambu machine profile named {leaf!r}; check PRINTER_MODEL and NOZZLE")
    gcode: dict[str, str] = {}
    name = leaf
    while name:  # nearest ancestor (or its includes) wins
        data = _load(index[name])
        for inc in data.get("include", []):
            tpl = _load(index[inc])
            for k in GCODE_KEYS:
                if k in tpl and k not in gcode:
                    gcode[k] = tpl[k]
        for k in GCODE_KEYS:
            if k in data and k not in gcode:
                gcode[k] = data[k]
        name = data.get("inherits", "")
    missing = [k for k in ("machine_start_gcode", "machine_end_gcode", "layer_change_gcode") if k not in gcode]
    if missing:
        raise ProfileError(f"could not find {missing} for {leaf}")
    profile = {"type": "machine", "name": machine_name(settings, nozzle), "inherits": leaf, "from": "User",
               "instantiation": "true", "printer_settings_id": machine_name(settings, nozzle),
               "nozzle_diameter": [nozzle_tag(nozzle)], **gcode}
    return _dump(profile_dir() / "machine" / f"{profile['name']}.json", profile)


def filament_name(settings: Settings, nozzle: float) -> str:
    return f"mini-forge {settings.filament} {nozzle_tag(nozzle)} nozzle"


def filament_fits(system_dir: Path, name: str, printer_model: str, nozzle: float = 0.4) -> bool:
    """True if Bambu lists this filament profile for the printer (no list counts as a fit)."""
    index = _index(system_dir, "filament")
    listed = resolve(_load(index[name]), system_dir, name).get("compatible_printers") or []
    return not listed or f"{printer_model} {nozzle_tag(nozzle)} nozzle" in listed


def fitting_filament(system_dir: Path, name: str, printer_model: str) -> str:
    """Bambu's variant of a filament profile made for this printer.

    Brands ship one profile per printer family ("@BBL X1C" also covers the P1S, "@BBL P1P" only the
    P1P), and the variants differ in bed temperature and fan settings, so a P1P profile on a P1S
    prints with the wrong values.
    """
    index = _index(system_dir, "filament")
    if name in index and filament_fits(system_dir, name, printer_model):
        return name
    prefix = name.split(" @")[0] + " @"
    for candidate in sorted(index):
        if (candidate.startswith(prefix) and not candidate.endswith(" nozzle") and "@base" not in candidate
                and filament_fits(system_dir, candidate, printer_model)):
            return candidate
    if name not in index:
        raise ProfileError(f"no Bambu filament profile named {name!r}; "
                           "pick one Bambu Studio lists, e.g. 'Bambu PLA Basic @BBL X1C'")
    return name


def build_filament(settings: Settings, nozzle: float, overrides: dict | None = None) -> Path:
    """Resolve the chosen Bambu filament profile, preferring its variant for small nozzles."""
    system_dir = system_profile_dir(settings.slicer_path)
    index = _index(system_dir, "filament")
    candidates = [f"{settings.filament} {nozzle_tag(nozzle)} nozzle", settings.filament]
    source = next((c for c in candidates if c in index), None)
    if source is None:
        raise ProfileError(f"no Bambu filament profile named {settings.filament!r}; "
                           "pick one Bambu Studio lists, e.g. 'Bambu PLA Basic @BBL X1C'")
    data = _single(resolve(_load(index[source]), system_dir, source))
    name = filament_name(settings, nozzle)
    data.update({"name": name, "inherits": source, "from": "User", "instantiation": "true",
                 "filament_settings_id": [name], **(overrides or {})})
    return _dump(profile_dir() / "filament" / f"{name}.json", data)


def overlays() -> dict[str, dict]:
    return {p.stem: _load(p) for p in sorted(OVERLAY_DIR.glob("*.json"))}


def overlay_nozzle(overlay: dict) -> float:
    return 0.2 if "0.2 nozzle" in overlay["inherits"] else 0.4


def materialize(settings: Settings, overlay: str | Path, out_dir: Path,
                changes: dict | None = None) -> tuple[Path, Path, Path, float]:
    """Write fully resolved machine/process/filament profiles for one slice into out_dir."""
    path = Path(overlay)
    if path.suffix != ".json":
        path = OVERLAY_DIR / f"{overlay}.json"
    if not path.exists():
        raise ProfileError(f"no overlay {overlay!r}; available: {', '.join(overlays())}")
    own = {k: v for k, v in _load(path).items() if not k.startswith("_")}
    own.update(changes or {})
    nozzle = overlay_nozzle(own)
    system_dir = system_profile_dir(settings.slicer_path)
    machine_file = profile_dir() / "machine" / f"{machine_name(settings, nozzle)}.json"
    filament_file = profile_dir() / "filament" / f"{filament_name(settings, nozzle)}.json"
    for f in (machine_file, filament_file):
        if not f.exists():
            raise ProfileError(f"{f.name} not built yet; run `mini-forge setup` (with NOZZLE={nozzle:g})")
    compatible = [system_machine_name(settings, nozzle), machine_name(settings, nozzle)]
    bed_process, _ = BED_TYPES[settings.bed]
    process = resolve(own, system_dir, path.name)
    process.update({"compatible_printers": compatible, "print_settings_id": own["name"],
                    "curr_bed_type": bed_process})
    machine = resolve(_load(machine_file), system_dir, machine_file.name)
    filament = resolve(_load(filament_file), system_dir, filament_file.name)
    filament["compatible_printers"] = compatible
    dest = out_dir / "resolved-profiles"
    return (_dump(dest / "machine.json", machine).resolve(), _dump(dest / "process.json", process).resolve(),
            _dump(dest / "filament.json", filament).resolve(), nozzle)

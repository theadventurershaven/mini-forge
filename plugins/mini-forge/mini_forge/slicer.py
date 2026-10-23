"""Slice STLs on one plate with the Bambu Studio CLI and fully resolved mini-forge profiles."""

from __future__ import annotations

import json
import re
import subprocess
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .profiles import ProfileError, materialize


class SliceError(RuntimeError):
    pass


@dataclass
class SliceResult:
    overlay: str
    nozzle: float
    package: Path          # compact printer package (.gcode.3mf)
    project: Path          # editable project with meshes (.project.3mf)
    gcode: Path
    preview_png: Path | None
    estimated_time_s: int | None
    filament_g: float | None
    layer_height: float | None
    objects: list[tuple[str, str]] = field(default_factory=list)
    elapsed_s: float = 0.0

    def summary(self) -> str:
        t = self.estimated_time_s
        eta = f"{t // 3600}h {(t % 3600) // 60}m" if t else "unknown"
        return (f"{self.overlay}: nozzle {self.nozzle:g} mm, layer {self.layer_height} mm, "
                f"about {eta}, {self.filament_g} g -> {self.package.name}")


def _run(cmd: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def _time_to_seconds(text: str) -> int | None:
    total, found = 0, False
    for num, unit in re.findall(r"(\d+)\s*([dhms])", text):
        found = True
        total += int(num) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return total if found else None


def slice_plate(stls: list[Path], overlay: str, out_dir: Path, name: str, *, copies: int = 1,
                changes: dict | None = None, settings: Settings | None = None) -> SliceResult:
    """Arrange the models on one plate and slice. `changes` adds per-job setting overrides."""
    settings = settings or Settings.load()
    if not settings.slicer_path.exists():
        raise SliceError(f"Bambu Studio not found at {settings.slicer_path}; set SLICER_PATH")
    stls = [Path(s).resolve() for s in stls]
    for s in stls:
        if not s.exists():
            raise SliceError(f"model missing: {s}")
    # The CLI runs inside out_dir and resolves relative paths against it: always pass absolute paths.
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        machine, process, filament, nozzle = materialize(settings, overlay, out_dir, changes)
    except ProfileError as exc:
        raise SliceError(str(exc)) from exc
    package, project, gcode = out_dir / f"{name}.gcode.3mf", out_dir / f"{name}.project.3mf", out_dir / "plate_1.gcode"
    for stale in (package, project, gcode, out_dir / "result.json"):
        stale.unlink(missing_ok=True)
    base = [str(settings.slicer_path), "--load-settings", f"{machine};{process}",
            "--load-filaments", str(filament), "--outputdir", str(out_dir)]
    clone = ["--clone-objects", ",".join([str(copies)] * len(stls))] if copies > 1 else []
    t0 = time.time()
    # Pass 1 exports an unsliced project so each object gets an id; only then does the slicer
    # label objects in the G-code (needed to skip a failed object on the printer).
    proc = _run(base + clone + ["--arrange", "1", "--orient", "0", "--export-3mf", project.name]
                + [str(s) for s in stls], cwd=out_dir)
    if proc.returncode != 0 or not project.exists():
        raise SliceError(f"project export failed (exit {proc.returncode}):\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
    proc = _run(base + ["--slice", "0", "--min-save", "--export-3mf", package.name, str(project)], cwd=out_dir)
    result_file = out_dir / "result.json"
    result = json.loads(result_file.read_text()) if result_file.exists() else {}
    if proc.returncode != 0 or result.get("return_code", 0) != 0 or not package.exists():
        raise SliceError(f"slicing failed (exit {proc.returncode}, {result.get('error_string', 'no result.json')}):\n"
                         f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    with zipfile.ZipFile(package) as z:
        names = z.namelist()
        plates = [n for n in names if re.fullmatch(r"Metadata/plate_\d+\.gcode", n)]
        if plates != ["Metadata/plate_1.gcode"]:
            raise SliceError(f"models do not fit on one plate ({len(plates)} plates); reduce copies")
        text = z.read("Metadata/plate_1.gcode").decode("utf-8", "replace")
        png = None
        if "Metadata/plate_1.png" in names:
            png = out_dir / f"{name}-preview.png"
            png.write_bytes(z.read("Metadata/plate_1.png"))
    gcode.write_text(text, encoding="utf-8")
    m = re.search(r"total estimated time: ([^;\n]+)", text) or re.search(r"model printing time: ([^;\n]+)", text)
    grams = re.search(r"; total filament weight \[g\] : ([\d.]+)", text)
    layer = re.search(r"^; layer_height = ([\d.]+)", text, re.MULTILINE)
    with zipfile.ZipFile(project) as z:
        settings_xml = z.read("Metadata/model_settings.config").decode("utf-8", "replace")
    names_by_id = {oid: (re.search(r'key="name" value="([^"]+)"', block) or [None, f"object {oid}"])[1]
                   for oid, block in re.findall(r'<object id="(\d+)">(.*?)</object>', settings_xml, re.DOTALL)}
    objects = []
    for inst in re.findall(r"<model_instance>(.*?)</model_instance>", settings_xml, re.DOTALL):
        oid = re.search(r'key="object_id" value="(\d+)"', inst)
        ident = re.search(r'key="identify_id" value="(\d+)"', inst)
        if oid and ident:
            objects.append((ident.group(1), names_by_id.get(oid.group(1), "object")))
    return SliceResult(
        overlay=Path(overlay).stem if str(overlay).endswith(".json") else str(overlay), nozzle=nozzle, package=package, project=project, gcode=gcode, preview_png=png,
        estimated_time_s=_time_to_seconds(m.group(1)) if m else None,
        filament_g=float(grams.group(1)) if grams else None,
        layer_height=float(layer.group(1)) if layer else None, objects=objects, elapsed_s=time.time() - t0)


def bed_temperature(gcode_text: str) -> list[str]:
    """Bed temperature commands in the start G-code; a wrong plate type shows up here first."""
    return re.findall(r"^M1(?:40|90) S(\d+)", gcode_text, re.MULTILINE)

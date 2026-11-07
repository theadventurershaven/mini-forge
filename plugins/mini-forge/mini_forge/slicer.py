"""Slice STLs on one plate with the Bambu Studio CLI and fully resolved mini-forge profiles."""

from __future__ import annotations

import json
import math
import re
import subprocess
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

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
    painted: dict[str, int] = field(default_factory=dict)  # enforcer faces per mesh file
    turn_deg: float = 0.0   # turn about Z applied to every arranged figure
    attempts: list[dict] = field(default_factory=list)

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


# Turns tried, in order, when a slice is not accepted. Where Bambu plants a tree depends on how the
# figure sits on the plate: alone, auto-arrange turned a printed creature 72 degrees and a claw start
# went from 75% supported (on its printed plate) to 0%; turned back to the printed angle it matched
# again. Each turn's checks run on its own G-code, which is what prints.
TURNS_DEG = (0.0, 90.0, 180.0, 270.0, 45.0, 135.0, 225.0, 315.0)
MIN_GAP_MM = 2.0


def slice_plate(stls: list[Path], overlay: str, out_dir: Path, name: str, *, copies: int = 1,
                changes: dict | None = None, settings: Settings | None = None,
                enforcers: dict[Path, list] | None = None, accept=None,
                turns: tuple[float, ...] = TURNS_DEG) -> SliceResult:
    """Arrange the models on one plate and slice. `changes` adds per-job setting overrides;
    `enforcers` maps an STL to points (in its own coordinates) painted as support enforcers.
    `accept(result) -> (ok, problems)` judges a slice; while it refuses, every arranged figure is
    turned in place by the next of `turns` and the same project is re-sliced. If no turn is
    accepted, the turn with the fewest problems is sliced again and returned (its checks rerun
    through `accept`). Without `accept` only the arranged angle is sliced."""
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
    arranged = out_dir / f"{name}.arranged.3mf"
    for stale in (package, project, gcode, arranged, out_dir / "result.json"):
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
    import trimesh

    from .support_paint import mesh_files_by_stl, paint_plate
    meshes = {str(s): trimesh.load(s, force="mesh") for s in stls}
    by_file = mesh_files_by_stl(project, {s: len(m.faces) for s, m in meshes.items()})
    painted: dict[str, int] = {}
    wanted = {str(Path(k).resolve()): v for k, v in (enforcers or {}).items() if v}
    if wanted:
        objs = {f: {"points": wanted[s]} for f, s in by_file.items() if s in wanted}
        tmp = project.with_name(project.stem + ".painting.3mf")
        painted = paint_plate(project, tmp, objs)
        tmp.replace(project)
    project.replace(arranged)
    hulls = {f: _xy_hull(meshes[s]) for f, s in by_file.items()}
    bed = _bed_polygon(machine)
    attempts: list[dict] = []
    result, ok, best = None, False, None
    for turn in (turns if accept else turns[:1]):
        if not turn_items(arranged, project, turn, hulls, bed):
            attempts.append({"turn_deg": turn, "skipped": "figures would touch or leave the plate"})
            continue
        result = _slice_project(base, project, package, gcode, out_dir, overlay, nozzle, t0, painted)
        result.turn_deg, result.attempts = turn, attempts
        ok, problems = accept(result) if accept else (True, 0)
        attempts.append({"turn_deg": turn, "accepted": ok, "problems": problems})
        if ok:
            break
        if best is None or problems < best[1]:
            best = (turn, problems)
    if not ok and best and result and best[0] != result.turn_deg:
        turn_items(arranged, project, best[0], hulls, bed)
        result = _slice_project(base, project, package, gcode, out_dir, overlay, nozzle, t0, painted)
        result.turn_deg, result.attempts = best[0], attempts
        accept(result)
        attempts.append({"turn_deg": best[0], "kept": "no turn passed; fewest problems"})
    arranged.unlink(missing_ok=True)
    if result is None:
        raise SliceError("no turn of the arranged plate fits on the bed; reduce copies")
    return result


def _slice_project(base: list[str], project: Path, package: Path, gcode: Path, out_dir: Path, overlay: str,
                   nozzle: float, t0: float, painted: dict[str, int]) -> SliceResult:
    for stale in (package, gcode, out_dir / "result.json"):
        stale.unlink(missing_ok=True)
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
            png = out_dir / f"{package.name.removesuffix('.gcode.3mf')}-preview.png"
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
        layer_height=float(layer.group(1)) if layer else None, objects=objects, elapsed_s=time.time() - t0, painted=painted)


def _xy_hull(mesh):
    from shapely.geometry import MultiPoint
    return MultiPoint(mesh.vertices[:, :2]).convex_hull


def _bed_polygon(machine_json: Path):
    from shapely.geometry import Polygon
    try:
        area = json.loads(Path(machine_json).read_text(encoding="utf-8")).get("printable_area") or []
        return Polygon([tuple(float(v) for v in p.split("x")) for p in area]) if len(area) >= 3 else None
    except (OSError, ValueError):
        return None


_ITEM = re.compile(r'(<item objectid="(\d+)"[^>]*?transform=")([^"]+)(")')


def turn_items(src: Path, dst: Path, turn_deg: float, hulls: dict, bed=None) -> bool:
    """Write `dst`: the project `src` with every plate item turned `turn_deg` about Z around its own
    origin. Copies of one figure first take the rotation of the first copy (arrange turns copies
    differently, and a turn that suits one would then not suit the others). Painted supports live
    in object coordinates and turn with it. Returns False, writing nothing, if two figures'
    footprints would come within MIN_GAP_MM or one would leave the bed. `hulls` maps a mesh file
    ("3D/Objects/object_1.model") to its XY convex hull in STL coordinates."""
    from shapely import affinity
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
    rz = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    with zipfile.ZipFile(src) as zi:
        model = zi.read("3D/3dmodel.model").decode()
        mesh_of = {m.group(1): m.group(2).lstrip("/") for m in re.finditer(
            r'<object id="(\d+)"[^>]*>\s*<components>\s*<component p:path="([^"]+)"', model)}
        shapes, turned, first = [], {}, {}
        for m in _ITEM.finditer(model):
            v = [float(x) for x in m.group(3).split()]
            mesh = mesh_of.get(m.group(2), "")
            r0 = first.setdefault(mesh or m.group(2), np.array(v[:9]).reshape(3, 3))
            r = r0 @ rz  # 3MF transforms act on row vectors: [x y z] @ R + t
            turned[m.group(0)] = r.ravel().tolist() + v[9:]
            hull = hulls.get(mesh)
            if hull is not None:
                shapes.append(affinity.affine_transform(hull, [r[0, 0], r[1, 0], r[0, 1], r[1, 1], v[9], v[10]]))
        for i, a in enumerate(shapes):
            if bed is not None and not bed.contains(a):
                return False
            if any(a.distance(b) < MIN_GAP_MM for b in shapes[i + 1:]):
                return False
        text = _ITEM.sub(lambda m: m.group(1) + " ".join(f"{x:.9g}" for x in turned[m.group(0)]) + m.group(4), model)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
            for it in zi.infolist():
                # Plate pictures from the arranged export would show the old angle (the printer also uses
                # top/pick to skip objects); without them, slicing draws them again.
                if it.filename.startswith("Metadata/") and it.filename.endswith(".png"):
                    continue
                data = text.encode() if it.filename == "3D/3dmodel.model" else zi.read(it.filename)
                if it.filename == "Metadata/model_settings.config":
                    data = re.sub(rb'\s*<metadata key="(?:thumbnail_file|thumbnail_no_light_file|top_file|pick_file)" value="[^"]*"/>', b"", data)
                elif it.filename == "_rels/.rels":
                    data = re.sub(rb'\s*<Relationship Target="/Metadata/[^"]+\.png"[^>]*/>', b"", data)
                zo.writestr(it, data)
    return True


def bed_temperature(gcode_text: str) -> list[str]:
    """Bed temperature commands in the start G-code; a wrong plate type shows up here first."""
    return re.findall(r"^M1(?:40|90) S(\d+)", gcode_text, re.MULTILINE)

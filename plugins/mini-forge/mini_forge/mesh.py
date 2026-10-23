"""Mesh preparation: GLB to a clean solid, review renders, landmark scaling onto a round base,
and a screening check.

Detail policy: no smoothing, remeshing, decimation or global thickening of the production
mesh. Decimated copies are used only for renders and thickness sampling. A thin warning is a
prompt to review which features carry load, not a reason to thicken the sculpt.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from .config import FEATURE_FLOOR_MM, review_font


# ---- import -------------------------------------------------------------------------------
def load_glb(path: Path, max_repair_edges: int = 30) -> tuple[trimesh.Trimesh, dict]:
    """Load a Meshy GLB (Y-up) as a Z-up closed solid, keeping the largest body.

    Only tiny seam defects are repaired (collapsing a handful of sub-0.02-unit open edges).
    Anything bigger stops for review instead of being patched silently.
    """
    m = trimesh.load(path, force="mesh")
    m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    m.merge_vertices(merge_tex=True, merge_norm=True)
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    parts = m.split(only_watertight=False)
    info = sorted(({"faces": len(p.faces), "volume": float(abs(p.volume)), "closed": bool(p.is_volume)} for p in parts),
                  key=lambda d: -d["volume"])
    body = max(parts, key=lambda p: abs(p.volume))
    collapsed = []
    for _ in range(5):
        if body.is_volume:
            break
        counts = np.bincount(body.edges_unique_inverse)
        bad = body.edges_unique[counts != 2]
        if not len(bad):
            trimesh.repair.fix_normals(body)
            break
        lengths = np.linalg.norm(body.vertices[bad[:, 0]] - body.vertices[bad[:, 1]], axis=1)
        if len(bad) > max_repair_edges or lengths.max() > 0.02:
            raise ValueError(f"mesh has {len(bad)} open edges (longest {lengths.max():.3f}); review before repairing")
        collapsed += lengths.tolist()
        for a, b in bad:
            body.vertices[a] = body.vertices[b] = (body.vertices[a] + body.vertices[b]) / 2
        body.merge_vertices()
        body.update_faces(body.nondegenerate_faces())
        body.remove_unreferenced_vertices()
    if not body.is_volume:
        raise ValueError("not a closed solid after light repair; inspect the GLB")
    return body, {"components": info, "kept_faces": len(body.faces), "collapsed_edges": len(collapsed)}


def normalize(m: trimesh.Trimesh, height_mm: float = 40.0) -> trimesh.Trimesh:
    """Review copy: uniform scale to a fixed height, centred, standing on z=0. Landmarks are read here."""
    m = m.copy()
    m.apply_scale(height_mm / m.extents[2])
    m.apply_translation([-m.bounds.mean(axis=0)[0], -m.bounds.mean(axis=0)[1], -m.bounds[0, 2]])
    return m


# ---- renders ------------------------------------------------------------------------------
def render_views(m: trimesh.Trimesh, out: Path, title: str, faces: int = 150_000) -> Path:
    """Front, side and back flat-shaded views with a millimetre grid (painter's algorithm)."""
    from PIL import Image, ImageDraw
    small = m.simplify_quadric_decimation(face_count=faces) if len(m.faces) > faces else m
    t = small.triangles
    height = float(m.bounds[1, 2])
    k = 600 / max(height, 1)
    font = review_font(18)
    im = Image.new("RGB", (2100, 760), "#f1f1ec")
    d = ImageDraw.Draw(im)
    for col, (yaw, label) in enumerate([(0, "front"), (90, "side"), (180, "back")]):
        az = math.radians(yaw)
        right = np.array([math.cos(az), math.sin(az), 0])
        depth = np.array([math.sin(az), -math.cos(az), 0])
        x, y, dep = t @ right, t[..., 2], t @ depth
        light = depth * 0.8 + np.array([-0.3, 0, 0.6])
        light /= np.linalg.norm(light)
        shade = np.clip(140 + 80 * (small.face_normals @ light), 40, 240).astype(int)
        ox, oy = col * 700 + 350, 700
        step = 2 if height <= 50 else 5
        for z in range(0, int(height) + 1, step):
            d.line((col * 700 + 40, oy - z * k, col * 700 + 680, oy - z * k), fill="#d8d8cf" if z % (5 * step) else "#b9b9ad")
            d.text((col * 700 + 6, oy - z * k - 9), str(z), fill="#447777", font=font)
        for i in np.argsort(dep.mean(axis=1)):
            d.polygon([(ox + a * k, oy - b * k) for a, b in zip(x[i], y[i])], fill=(int(shade[i]),) * 3)
        d.text((col * 700 + 40, 12), f"{title}: {label} (mm)", fill="black", font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


# ---- landmarks ----------------------------------------------------------------------------
def section_area(m: trimesh.Trimesh, z: float) -> float:
    s = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if s is None:
        return 0.0
    planar, _ = s.to_2D()
    return float(sum(p.area for p in planar.polygons_full))


def suggest_base_top(m: trimesh.Trimesh, search_mm: float = 6.0, step: float = 0.25) -> float | None:
    """Height where a sculpted base ends: the first sharp drop in cross-section area.

    Returns None when there is no clear drop (no sculpted base); read the side view then.
    """
    zs = np.arange(0.5, min(search_mm, m.bounds[1, 2] / 3), step)
    areas = [section_area(m, z) for z in zs]
    for z, a0, a1 in zip(zs[1:], areas, areas[1:]):
        if a0 > 0 and a1 < 0.7 * a0:
            return float(z)
    return None


# ---- scaling onto a base ------------------------------------------------------------------
def scale_to_eye_height(mesh: trimesh.Trimesh, *, feet_z_mm: float, eyes_z_mm: float,
                        target_eye_height_mm: float = 32.0, base_diameter_mm: float = 25.0,
                        base_thickness_mm: float = 2.0) -> tuple[trimesh.Trimesh, float]:
    """Cut off the old base at the sole plane, scale uniformly so feet-to-eyes is the target,
    and union a plain round base. Landmarks must be read from this exact mesh."""
    values = (feet_z_mm, eyes_z_mm, target_eye_height_mm, base_diameter_mm, base_thickness_mm)
    if not all(math.isfinite(v) for v in values) or min(values[2:]) <= 0:
        raise ValueError("landmarks and dimensions must be finite and positive")
    if not mesh.is_volume:
        raise ValueError("scaling requires a closed solid")
    low, high = mesh.bounds
    if not low[2] < feet_z_mm < eyes_z_mm < high[2]:
        raise ValueError("feet and eyes must be ordered inside the mesh height")
    factor = target_eye_height_mm / (eyes_z_mm - feet_z_mm)
    cut_z = feet_z_mm + 0.0001  # cutting exactly on the old base top can leave a zero-thickness rim
    clip_low = np.array([low[0] - 1, low[1] - 1, cut_z])
    clip = trimesh.creation.box(extents=high + 1 - clip_low)
    clip.apply_translation((clip_low + high + 1) / 2)
    body = trimesh.boolean.intersection([mesh, clip], engine="manifold")
    if body.is_empty:
        raise ValueError("base removal left no body")
    body.vertices[np.isclose(body.vertices[:, 2], cut_z, atol=1e-5, rtol=0), 2] = feet_z_mm
    centre = (low[:2] + high[:2]) / 2
    body.apply_translation([-centre[0], -centre[1], -feet_z_mm])
    body.apply_scale(factor)
    body.apply_translation([0, 0, base_thickness_mm])
    base = trimesh.creation.cylinder(radius=base_diameter_mm / 2, height=base_thickness_mm, sections=128)
    base.apply_translation([0, 0, base_thickness_mm / 2])
    result = trimesh.boolean.union([body, base], engine="manifold")
    if not result.is_volume:
        raise ValueError("scaled body and base did not form a valid solid")
    return result, factor


def contacts_on_base(m: trimesh.Trimesh, base_diameter_mm: float, base_thickness_mm: float) -> list[dict]:
    """Cross-sections just above the base top: what stands on it and how much lies inside the rim."""
    from shapely.geometry import Point, Polygon
    rim = Point(0, 0).buffer(base_diameter_mm / 2)
    s = m.section(plane_origin=[0, 0, base_thickness_mm + 0.05], plane_normal=[0, 0, 1])
    out = []
    for loop in (s.discrete if s is not None else []):
        poly = Polygon(loop[:, :2]).buffer(0)
        if poly.area > 0.1:
            out.append({"area_mm2": round(poly.area, 2), "on_base_fraction": round(poly.intersection(rim).area / poly.area, 4),
                        "center_xy": [round(v, 2) for v in poly.centroid.coords[0]]})
    return out


# ---- screening check ----------------------------------------------------------------------
@dataclass
class CheckResult:
    path: str
    nozzle: float
    floor_mm: float
    faces: int
    watertight: bool
    components: int
    height_mm: float
    footprint_mm: tuple[float, float]
    thickness_median_mm: float
    thickness_p10_mm: float
    thin_fraction: float
    overhang_fraction: float
    passed: bool
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{'PASS' if self.passed else 'FAIL'} {Path(self.path).name}: closed={self.watertight} pieces={self.components} "
                f"height={self.height_mm:.1f} mm thickness median={self.thickness_median_mm:.2f} p10={self.thickness_p10_mm:.2f} "
                f"thinner than {self.floor_mm} mm={self.thin_fraction:.0%} overhang={self.overhang_fraction:.0%}"
                + (f" | {'; '.join(self.reasons)}" if self.reasons else ""))


def check_mesh(path: Path, nozzle: float, thin_limit: float = 0.10, height_range_mm: tuple[float, float] = (15, 80),
               max_faces: int = 120_000, samples: int = 4000) -> CheckResult:
    """Closed single body, plausible height, share of surface thinner than the nozzle's floor.
    Thickness is ray-sampled on a decimated copy (full meshes need tens of GB)."""
    floor = FEATURE_FLOOR_MM.get(nozzle, 3 * nozzle)
    full = trimesh.load(path, force="mesh")
    small = full.simplify_quadric_decimation(face_count=max_faces) if len(full.faces) > max_faces else full
    ext = full.extents
    parts = full.split(only_watertight=False)
    pts, fid = trimesh.sample.sample_surface(small, samples)
    th = trimesh.proximity.thickness(small, pts, exterior=False, normals=small.face_normals[fid], method="ray")
    th = th[np.isfinite(th)]
    th = th if th.size else np.array([0.0])
    thin = float((th < floor).mean())
    down = small.face_normals[:, 2] < -math.sin(math.radians(60))
    overhang = float(small.area_faces[down].sum() / small.area) if small.area else 0.0
    reasons = []
    if not full.is_watertight:
        reasons.append("not watertight")
    if len(parts) > 1:
        reasons.append(f"{len(parts)} separate pieces")
    if thin > thin_limit:
        reasons.append(f"{thin:.0%} of surface thinner than {floor} mm: review which parts carry load")
    if not height_range_mm[0] <= ext[2] <= height_range_mm[1]:
        reasons.append(f"height {ext[2]:.1f} mm outside {height_range_mm[0]}-{height_range_mm[1]} mm")
    return CheckResult(str(path), nozzle, floor, len(full.faces), bool(full.is_watertight), len(parts), float(ext[2]),
                       (float(ext[0]), float(ext[1])), float(np.median(th)), float(np.percentile(th, 10)), thin, overhang,
                       not reasons, reasons)


def save_json(path: Path, data) -> Path:
    path.write_text(json.dumps(asdict(data) if hasattr(data, "__dataclass_fields__") else data, indent=2) + "\n")
    return path

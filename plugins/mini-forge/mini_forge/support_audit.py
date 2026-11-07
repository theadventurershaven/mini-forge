"""Audit the support structures actually written into sliced G-code.

Reads the support toolpaths layer by layer, groups them into columns, follows each
column upward, and reports its height, how far it leans from its footprint, and how
thick its walls are for the nozzle in use. Refuses a package whose supports are too
tall and slender to stand: a figure's shield support failed this way even though every
setting value was a proven one.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

# Calibrated against G-code of printed jobs. A failed 0.2 mm slice had a slim 29 mm tree
# standing alone outside the base rim, leaning 17 degrees to reach under a sword blade; that
# tree was found lying on the plate. Another figure's 30.7 mm slim tree survived, so height and
# lean alone do not separate the two: one of two tall slim trees failed. Rule: on the 0.2 mm nozzle a tree taller than 20 mm must be stout
# (branch >= 1.6 mm and two walls). Lean limits catch the other failure shape.
SLIM_HEIGHT_LIMIT_MM = {0.2: 20.0, 0.4: 30.0}
STOUT_HEIGHT_LIMIT_MM = {0.2: 36.0, 0.4: 40.0}
SLIM_LEAN_LIMIT_DEG = {0.2: 35.0, 0.4: 45.0}
STOUT_LEAN_LIMIT_DEG = {0.2: 45.0, 0.4: 50.0}
LEAN_MIN_HEIGHT_MM = 8.0


@dataclass
class Column:
    base_z: float
    top_z: float
    base_xy: tuple[float, float]
    top_xy: tuple[float, float]
    layers: int
    min_area_mm2: float = 0.0   # thinnest dilated cross-section along the body
    min_area_z: float = 0.0

    @property
    def height(self) -> float:
        return self.top_z - self.base_z

    @property
    def lean_mm(self) -> float:
        return math.dist(self.base_xy, self.top_xy)

    @property
    def lean_deg(self) -> float:
        return math.degrees(math.atan2(self.lean_mm, self.height)) if self.height > 0 else 0.0


@dataclass
class SupportAudit:
    gcode: str
    nozzle_mm: float
    branch_diameter_mm: float | None
    wall_count: int | None
    support_line_width_mm: float | None
    stout: bool
    columns: int
    tallest_mm: float
    max_lean_deg: float
    limit_mm: float
    passed: bool
    reasons: list[str] = field(default_factory=list)
    worst: list[dict] = field(default_factory=list)


def _header(g: str, key: str) -> str | None:
    m = re.search(rf"^; {re.escape(key)} = (.+)$", g, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else None


def support_points_by_layer(g: str) -> dict[float, np.ndarray]:
    """Midpoints of support extrusion moves, keyed by layer Z."""
    z = None
    feature = ""
    px = py = None
    pts: dict[float, list] = {}
    move = re.compile(r"^G1 (?:X(-?[\d.]+))?\s*(?:Y(-?[\d.]+))?.*?(?:E(-?[\d.]+))?\s*$")
    for line in g.splitlines():
        if line.startswith("; Z_HEIGHT:"):
            z = float(line.split(":")[1])
            continue
        if line.startswith("; FEATURE:"):
            feature = line
            continue
        if not line.startswith("G1 "):
            continue
        m = move.match(line)
        if not m:
            continue
        x = float(m.group(1)) if m.group(1) else px
        y = float(m.group(2)) if m.group(2) else py
        e = m.group(3)
        if px is not None and x is not None and y is not None and e and float(e) > 0 and z is not None and "Support" in feature:
            pts.setdefault(z, []).append(((px + x) / 2, (py + y) / 2))
        px, py = x, y
    return {k: np.array(v) for k, v in pts.items()}


GRID_MM = 0.5
NEIGHBOUR_MM = 1.0


BAND_MM = 0.2


def merge_layer_bands(layers: dict[float, np.ndarray], band_mm: float = BAND_MM) -> dict[float, np.ndarray]:
    """Union support points into fixed height bands.

    With several objects on a plate, each object's support is printed on its own layer
    heights, interleaved with the others'. Stacked layer by layer, every tree then appears
    only on alternate slices and falls apart into fragments of a millimetre or two, so tall
    trees passed the audit. Each band
    holds every object's support layer in that height range; the band's Z is its highest layer.
    """
    bands: dict[int, list] = {}
    tops: dict[int, float] = {}
    for z, pts in layers.items():
        k = int(z // band_mm)
        bands.setdefault(k, []).append(pts)
        tops[k] = max(tops.get(k, z), z)
    return {tops[k]: np.vstack(v) for k, v in bands.items()}


def trace_columns(layers: dict[float, np.ndarray]) -> list[Column]:
    """Measure connected support bodies in 3D.

    Each layer's support points are painted onto a grid, dilated by NEIGHBOUR_MM, and the
    layers are stacked into a volume. Connected bodies (26-connectivity) are the trees;
    a leaning or branching tree stays one body. Height, lean between base and top, and
    the thinnest cross-section along the way are reported per body.
    """
    from scipy import ndimage
    if not layers:
        return []
    layers = merge_layer_bands(layers)
    zs = sorted(layers)
    allp = np.vstack([layers[z] for z in zs])
    lo = allp.min(axis=0) - 4; hi = allp.max(axis=0) + 4
    nx, ny = (math.ceil(v) for v in (hi - lo) / GRID_MM)
    r = round(NEIGHBOUR_MM / GRID_MM); yy, xx = np.ogrid[-r:r + 1, -r:r + 1]; disk = (xx * xx + yy * yy) <= r * r
    vol = np.zeros((len(zs), nx, ny), dtype=bool)
    for i, z in enumerate(zs):
        idx = ((layers[z] - lo) / GRID_MM).astype(int)
        m = np.zeros((nx, ny), dtype=bool); m[idx[:, 0], idx[:, 1]] = True
        vol[i] = ndimage.binary_dilation(m, structure=disk)
    # Join across one empty band: a sparse object's support can skip a band entirely.
    vol = ndimage.binary_dilation(vol, structure=np.ones((3, 1, 1), dtype=bool))
    lab, n = ndimage.label(vol, structure=np.ones((3, 3, 3)))
    cols: list[Column] = []
    for k in range(1, n + 1):
        zi, xi, yi = np.nonzero(lab == k)
        if zi.max() - zi.min() < 4:
            continue
        z0, z1 = zi.min(), zi.max()
        base = np.array([xi[zi == z0].mean(), yi[zi == z0].mean()]) * GRID_MM + lo
        top = np.array([xi[zi == z1].mean(), yi[zi == z1].mean()]) * GRID_MM + lo
        areas = np.bincount(zi - z0) * GRID_MM * GRID_MM
        c = Column(float(zs[z0]), float(zs[z1]), (float(base[0]), float(base[1])), (float(top[0]), float(top[1])), int(z1 - z0 + 1))
        c.min_area_mm2 = float(areas[areas > 0].min()); c.min_area_z = float(zs[z0 + int(np.argmin(np.where(areas > 0, areas, np.inf)))])
        cols.append(c)
    return cols


def audit_supports(gcode_path: Path, nozzle_mm: float) -> SupportAudit:
    g = Path(gcode_path).read_text()
    branch = _header(g, "tree_support_branch_diameter")
    walls = _header(g, "tree_support_wall_count")
    lw = _header(g, "support_line_width")
    branch_f = float(branch) if branch else None
    walls_i = int(float(walls)) if walls else None
    stout = bool(branch_f and branch_f >= 1.6 and walls_i is not None and walls_i >= 2)
    limit = (STOUT_HEIGHT_LIMIT_MM if stout else SLIM_HEIGHT_LIMIT_MM).get(nozzle_mm, 18.0)
    lean_limit = (STOUT_LEAN_LIMIT_DEG if stout else SLIM_LEAN_LIMIT_DEG).get(nozzle_mm, 35.0)
    cols = [c for c in trace_columns(support_points_by_layer(g)) if c.layers >= 5]
    reasons = []
    tallest = max((c.height for c in cols), default=0.0)
    max_lean = max((c.lean_deg for c in cols), default=0.0)
    for c in cols:
        if c.height > limit:
            reasons.append(f"support column {c.height:.1f} mm tall at ({c.base_xy[0]:.0f},{c.base_xy[1]:.0f}) exceeds {limit:.0f} mm for {'stout' if stout else 'slim'} trees on a {nozzle_mm} mm nozzle")
        if c.lean_deg > lean_limit and c.height > LEAN_MIN_HEIGHT_MM:
            reasons.append(f"support column leans {c.lean_deg:.0f} degrees over {c.height:.1f} mm at ({c.base_xy[0]:.0f},{c.base_xy[1]:.0f}); limit {lean_limit:.0f} degrees for {'stout' if stout else 'slim'} trees on a {nozzle_mm} mm nozzle")
    worst = sorted(cols, key=lambda c: -c.height)[:5]
    return SupportAudit(
        gcode=str(gcode_path), nozzle_mm=nozzle_mm, branch_diameter_mm=branch_f, wall_count=walls_i,
        support_line_width_mm=float(lw) if lw else None, stout=stout, columns=len(cols), tallest_mm=round(tallest, 2),
        max_lean_deg=round(max_lean, 1), limit_mm=limit, passed=not reasons, reasons=reasons,
        worst=[{"height_mm": round(c.height, 2), "lean_deg": round(c.lean_deg, 1), "lean_mm": round(c.lean_mm, 1), "base_z": c.base_z, "top_z": c.top_z,
                "base_xy": [round(v, 1) for v in c.base_xy], "min_area_mm2": round(c.min_area_mm2, 1), "min_area_z": c.min_area_z} for c in worst],
    )


def write_audit(gcode_path: Path, nozzle_mm: float, out: Path | None = None) -> SupportAudit:
    a = audit_supports(gcode_path, nozzle_mm)
    out = out or Path(gcode_path).with_name("support-audit.json")
    out.write_text(json.dumps(asdict(a), indent=2) + "\n")
    return a

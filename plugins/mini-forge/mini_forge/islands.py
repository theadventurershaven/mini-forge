"""Features that start in mid-air, before and after slicing.

Printed bottom-up, every hand, claw tip, cloth corner or weapon tip whose lowest point is not
connected to anything below starts as an "island" in open air. Slicer-wide support settings and
audits do not show whether a particular island got support under it; these checks do.

1. `mesh_islands` (before slicing): where islands start, how far from the rest of the layer,
   and how soon they join the body. Fix large, distant ones in the reference picture or mesh.
2. `landing_coverage` (after slicing): for model paths that start in air, the share that has a
   support path under it just below the top gap. Rule from failed prints: a feature more than
   3 mm out with under 20% coverage is a likely lost feature; fix it before printing.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import trimesh


# ---- mesh -------------------------------------------------------------------------------
def _layer_polys(m: trimesh.Trimesh, z: float) -> list:
    from shapely.geometry import Polygon
    s = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if s is None:
        return []
    shape = None
    for loop in s.discrete:
        if len(loop) < 3:
            continue
        p = Polygon(loop[:, :2]).buffer(0)
        shape = p if shape is None else shape.symmetric_difference(p)
    if shape is None or shape.is_empty:
        return []
    return [g for g in getattr(shape, "geoms", [shape]) if g.area > 0.005]


def mesh_islands(path: Path, z_from: float, step: float = 0.06, max_faces: int = 300_000) -> list[dict]:
    """Islands above z_from (use just above the base top). Analysis copy only."""
    from shapely.ops import unary_union
    m = trimesh.load(path, force="mesh")
    if len(m.faces) > max_faces:
        m = m.simplify_quadric_decimation(face_count=max_faces)
    prev, tracked, found = [], [], []
    for z in np.arange(z_from, m.bounds[1, 2], step):
        cur = _layer_polys(m, z)
        below = unary_union(prev) if prev else None
        if prev:
            for p in cur:
                if below is None or not p.intersects(below):
                    gap = min((p.distance(q) for q in cur if q is not p), default=None)
                    rec = {"start_z": round(float(z), 2), "area_mm2": round(p.area, 3),
                           "xy": [round(c, 2) for c in p.centroid.coords[0]],
                           "gap_to_rest_mm": round(gap, 2) if gap is not None else None,
                           "max_gap_mm": gap or 0.0, "joined_z": None, "_poly": p}
                    found.append(rec)
                    tracked.append(rec)
        still = []
        for rec in tracked:
            mine = [p for p in cur if p.intersects(rec["_poly"])]
            if not mine:
                rec["joined_z"] = "ended"
                continue
            p = max(mine, key=lambda q: q.area)
            rec["_poly"] = p
            if below is not None and len([q for q in prev if q.intersects(p)]) > 1:
                rec["joined_z"] = round(float(z), 2)
                continue
            rec["max_gap_mm"] = max(rec["max_gap_mm"], min((p.distance(q) for q in cur if q is not p), default=0.0))
            still.append(rec)
        tracked, prev = still, cur
    return [{**{k: v for k, v in r.items() if k != "_poly"}, "max_gap_mm": round(r["max_gap_mm"], 2)} for r in found]


# ---- sliced G-code ------------------------------------------------------------------------
def load_paths(gcode: Path) -> dict[float, dict[str, np.ndarray]]:
    """Extrusion midpoints per layer, split into model ('m') and support ('s')."""
    z, feature, px, py, layers = None, "", None, None, {}
    move = re.compile(r"^G[123] (?:X(-?[\d.]+))?\s*(?:Y(-?[\d.]+))?.*?(?:E(-?[\d.]+))?\s*$")
    for line in Path(gcode).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("; Z_HEIGHT:"):
            z = float(line.split(":")[1])
            continue
        if line.startswith("; FEATURE:"):
            feature = line
            continue
        if not line.startswith(("G1 ", "G2 ", "G3 ")):
            continue
        mm = move.match(line)
        if not mm:
            continue
        x = float(mm.group(1)) if mm.group(1) else px
        y = float(mm.group(2)) if mm.group(2) else py
        e = mm.group(3)
        if px is not None and x is not None and e and float(e) > 0 and z is not None:
            d = layers.setdefault(z, {"m": [], "s": []})
            (d["s"] if "Support" in feature else d["m"]).append(((px + x) / 2, (py + y) / 2))
        px, py = x, y
    return {z: {k: np.array(v) if v else np.zeros((0, 2)) for k, v in d.items()} for z, d in layers.items()}


def landing_coverage(gcode: Path, top_gap_mm: float, base_top_mm: float, island_mm: float = 0.8,
                     bead_mm: float = 0.4, link_mm: float = 1.5) -> dict:
    """Cluster model paths that start in air and report their distance out and support coverage."""
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    layers = load_paths(gcode)
    zs = sorted(layers)
    rows = []
    for i, z in enumerate(zs):
        if i < 3 or z < base_top_mm or not len(layers[z]["m"]):
            continue
        below = layers[zs[i - 1]]["m"]
        if not len(below):
            continue
        d, _ = cKDTree(below).query(layers[z]["m"])
        mask = d > island_mm
        new, dist = layers[z]["m"][mask], d[mask]
        if len(new) < 3:
            continue
        tree = cKDTree(new)
        n, lab = connected_components(tree.sparse_distance_matrix(tree, link_mm), directed=False)
        sup = [layers[zt]["s"] for zt in zs if (z - top_gap_mm - 0.2) <= zt <= (z - top_gap_mm + 0.02) and len(layers[zt]["s"])]
        sup = np.vstack(sup) if sup else np.zeros((0, 2))
        for k in range(n):
            pts, dd = new[lab == k], dist[lab == k]
            if len(pts) < 3:
                continue
            covered = float((cKDTree(sup).query(pts)[0] < bead_mm).mean()) if len(sup) else 0.0
            out = float(np.median(dd))
            if (covered < 0.5 and out > 1.0) or out > 2.0:
                c = pts.mean(axis=0)
                rows.append({"z": round(z, 2), "points": len(pts), "xy": [round(float(c[0]), 1), round(float(c[1]), 1)],
                             "from_model_mm": round(out, 1), "support_coverage": round(covered, 2)})
    risky = [r for r in rows if r["from_model_mm"] > 3 and r["support_coverage"] < 0.2]
    return {"gcode": str(gcode), "top_gap_mm": top_gap_mm, "islands": rows, "risky": risky, "passed": not risky}


def top_gap_from_gcode(gcode: Path) -> float:
    m = re.search(r"^; support_top_z_distance = ([\d.]+)", Path(gcode).read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
    if not m:
        raise ValueError("support_top_z_distance not found in G-code")
    return float(m.group(1))

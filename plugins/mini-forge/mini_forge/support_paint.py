"""Paint support enforcers onto flagged mid-air starts in the project before it is sliced.

Bambu's automatic tree supports skip some small mid-air starts, such as a hanging tail tip
or the bottom of a lowered elbow, even with small-overhang removal off. Painting those faces
as enforcers makes the slicer plant a tree there and nowhere else, while the rest of the
supports keep the overlay's recipe. This is the fix for an uncovered start; turning off
"critical regions only" is not (it multiplies supports everywhere and is refused by the audit).

Faces are painted whole (`paint_supports="4"`, the 3MF encoding of an unsplit enforcer
triangle) when they face downward and lie within a radius of a flagged point, given in the
same coordinates as the sliced STL (Z from the plate).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import numpy as np

ENFORCE = "4"
BLOCK = "8"
# Islands closer than this to the rest of their layer are left to the slicer (they usually bridge
# or get a tree anyway); smaller than MIN_AREA_MM2 is a sliver of mesh noise.
MIN_GAP_MM = 1.0
MIN_AREA_MM2 = 0.005


def enforcer_points(islands: list[dict], min_gap_mm: float = MIN_GAP_MM, min_area_mm2: float = MIN_AREA_MM2) -> list[tuple[float, float, float]]:
    """Points to paint, from `mesh_islands` output (islands.json)."""
    out = []
    for i in islands:
        gap = i.get("gap_to_rest_mm")
        if (gap is None or gap >= min_gap_mm) and i["area_mm2"] >= min_area_mm2:
            out.append((i["xy"][0], i["xy"][1], i["start_z"] + 0.1))
    return out


def mesh_files_by_stl(project: Path, face_counts: dict[str, int]) -> dict[str, str]:
    """Map each mesh file in the project to the STL (key of `face_counts`) with the closest
    triangle count. The project stores each imported STL unchanged. Copies made with
    --clone-objects share their original's mesh file and leave empty stub files, which are skipped."""
    out = {}
    with zipfile.ZipFile(project) as z:
        for n in z.namelist():
            if n.startswith("3D/Objects/") and n.endswith(".model"):
                k = len(re.findall(rb"<triangle ", z.read(n)))
                if k:
                    out[n] = min(face_counts, key=lambda s: abs(face_counts[s] - k))
    return out


def paint_plate(project: Path, out: Path, objects: dict[str, dict], radius_mm: float = 1.2,
                max_normal_z: float = -0.3) -> dict[str, int]:
    """`objects` maps a mesh file ("3D/Objects/object_1.model") to {"points": [(x, y, z), ...]
    in that model's STL coordinates, "block": [(x, y, z, radius), ...]}; block regions are
    painted as support blockers. Returns painted face counts per mesh file."""
    counts: dict[str, int] = {}
    with zipfile.ZipFile(project) as zi:
        model = zi.read("3D/3dmodel.model").decode()
        offsets = {m.group(1).lstrip("/"): np.array([float(v) for v in m.group(2).split()[9:12]])
                   for m in re.finditer(r'<component p:path="([^"]+)" objectid="\d+"[^>]*transform="([^"]+)"', model)}
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
            for n in zi.namelist():
                data = zi.read(n)
                spec = objects.get(n) or {}
                if spec.get("points") or spec.get("block"):
                    offset = offsets.get(n, np.zeros(3))
                    text, counts[n] = data.decode(), 0
                    if spec.get("points"):
                        text, counts[n] = _paint(text, np.array(spec["points"], float) - offset, radius_mm, max_normal_z)
                    for bx, by, bz, br in spec.get("block", []):
                        text, k = _paint(text, np.array([(bx, by, bz)], float) - offset, br, max_normal_z, BLOCK)
                        counts[n + " blocked"] = counts.get(n + " blocked", 0) + k
                    data = text.encode()
                zo.writestr(n, data)
    return counts


def _paint(text: str, pts: np.ndarray, radius: float, max_nz: float, state: str = ENFORCE) -> tuple[str, int]:
    from scipy.spatial import cKDTree
    vert = np.array(re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', text), float)
    tri_re = re.compile(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"(?: paint_supports="\w+")?/>')
    tris = np.array([m.groups() for m in tri_re.finditer(text)], int)
    a, b, c = vert[tris[:, 0]], vert[tris[:, 1]], vert[tris[:, 2]]
    n = np.cross(b - a, c - a)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    near = np.zeros(len(tris), bool)
    for idx in cKDTree((a + b + c) / 3).query_ball_point(pts, radius):
        near[idx] = True
    sel = near & (n[:, 2] < max_nz)
    it = iter(sel)

    def sub(m: re.Match) -> str:
        return f'<triangle v1="{m.group(1)}" v2="{m.group(2)}" v3="{m.group(3)}" paint_supports="{state}"/>' if next(it) else m.group(0)

    return tri_re.sub(sub, text), int(sel.sum())

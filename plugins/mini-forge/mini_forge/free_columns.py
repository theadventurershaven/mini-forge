"""Find features that print as free-standing columns before they join the body.

A feature that starts in mid-air below the part it hangs from (a drooping tail, a hanging hand) prints
upward from its own support tip and only meets the body several millimetres higher. Supports fix the
start but not the column: on one retry plate a dog figure's tail and a soldier's
hanging arm were both 100% supported at their starts and both still came off, the tail with its support.
The island check only asks whether a start has something under it; this check measures what grows on it.

Each slice of the mesh is split into separate regions; regions that overlap between neighbouring slices
are connected. A region is free while nothing below connects it to the base. For each free group the
report gives its height before it joins the body, its thinnest section, and the area through which it
joins (the overlap of its last free slice with the body region above).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon

# A free column at least FREE_HEIGHT_MM tall is flagged when it joins the body through less than JOIN_MM2,
# or when its thinnest section carries too much column (mm2 of section per mm of free height < NECK_RATIO).
# Calibration (2026-10-28): failed on 0.2 mm: a dog tail 5.4 mm / 1.22 mm2 / join 2.68 (twice), a hanging forearm
# 11.2 mm / 0.43 mm2 (twice). Printed fine: a raised elbow 2.8 mm / 1.40 mm2 (ratio 0.51). A quadruped
# tail (5.7 mm / 0.81 mm2, 0.4 mm nozzle) is flagged but printed acceptably; physical tail quality was not reported.
# 2026-11-07: two curled claw tips on a creature (2.3 and 2.5 mm / 0.3 mm2 / join 1.1-1.2 mm2, 0.4 mm nozzle) were
# flagged at 2 mm but printed on a plate the owner called one of the strongest (no breakage reported). Every column
# that broke was 5.4 mm or taller and every one that printed fine was 2.8 mm or shorter, so the floor is 3 mm.
FREE_HEIGHT_MM = 3.0
JOIN_MM2 = 3.0
NECK_RATIO = 0.3


@dataclass
class FreeColumn:
    start_z: float
    joined_z: float | None
    height_mm: float
    xy: tuple[float, float]
    min_area_mm2: float
    min_area_z: float
    join_area_mm2: float
    risky: bool


def _polys(mesh: trimesh.Trimesh, z: float) -> list[Polygon]:
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return []
    planar, T = sec.to_2D()
    to3 = lambda c: trimesh.transform_points(np.column_stack([np.asarray(c), np.zeros(len(c))]), T)[:, :2]
    out = []
    for p in planar.polygons_full:
        q = Polygon(to3(p.exterior.coords), [to3(h.coords) for h in p.interiors]).buffer(0)
        if q.area > 1e-4:
            out.append(q)
    return out


def free_columns(stl: Path, layer_mm: float = 0.06, base_top_mm: float = 2.0) -> list[FreeColumn]:
    mesh = trimesh.load(stl, force="mesh")
    z0, z1 = mesh.bounds[0][2], mesh.bounds[1][2]
    prev: list[tuple[object, Polygon]] = []  # (label, polygon); label "base" or an int group id
    groups: dict[int, dict] = {}
    alias: dict[int, int] = {}
    done: list[FreeColumn] = []
    nxt = 0

    def g(label):
        while label in alias:
            label = alias[label]
        return label

    for z in np.arange(z0 + layer_mm / 2, z1, layer_mm):
        z = round(float(z), 3)
        cur = []
        for p in _polys(mesh, z):
            below = [(g(lab), q) for lab, q in prev if p.intersects(q)]
            labels = {lab for lab, _ in below}
            if z - z0 <= base_top_mm * 0.5 or "base" in labels:
                for lab in labels - {"base"}:  # free groups joining the body here
                    rec = groups.pop(lab)
                    alias[lab] = "base"  # other regions in this slice that touch the group now touch the body
                    join = sum(p.intersection(q).area for l2, q in below if l2 == lab)
                    done.append(_finish(rec, z, join))
                cur.append(("base", p))
            elif not labels:
                groups[nxt] = {"start_z": z, "xy": tuple(round(float(v), 2) for v in p.centroid.coords[0]), "areas": {}}
                cur.append((nxt, p)); nxt += 1
            else:
                keep, *rest = sorted(labels)
                for lab in rest:
                    groups[keep]["start_z"] = min(groups[keep]["start_z"], groups[lab]["start_z"])
                    groups.pop(lab); alias[lab] = keep
                cur.append((keep, p))
        cur = [(g(lab), p) for lab, p in cur]
        for lab, p in cur:
            if lab != "base":
                a = groups[lab]["areas"]; a[z] = a.get(z, 0) + p.area
        prev = cur
    for rec in groups.values():
        done.append(_finish(rec, None, 0.0))
    return sorted(done, key=lambda c: c.start_z)


def _finish(rec: dict, joined_z: float | None, join_area: float) -> FreeColumn:
    areas = rec["areas"]
    top = max(areas) if areas else rec["start_z"]
    height = (joined_z if joined_z is not None else top) - rec["start_z"]
    body = {z: a for z, a in areas.items() if z >= rec["start_z"] + 0.5} or areas or {rec["start_z"]: 0.0}
    zmin = min(body, key=body.get)
    risky = height >= FREE_HEIGHT_MM and (joined_z is None or join_area < JOIN_MM2 or body[zmin] / height < NECK_RATIO)
    return FreeColumn(rec["start_z"], joined_z, round(height, 2), rec["xy"], round(body[zmin], 3), zmin, round(join_area, 3), risky)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from dataclasses import asdict
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stl", type=Path)
    ap.add_argument("--min-height", type=float, default=0.5)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    cols = [c for c in free_columns(a.stl) if c.height_mm >= a.min_height]
    for c in cols:
        print(f"{'RISKY ' if c.risky else '      '}start z{c.start_z:6.2f} at {c.xy} free {c.height_mm:5.2f} mm, "
              f"thinnest {c.min_area_mm2:6.2f} mm2 at z{c.min_area_z:.2f}, joins at z{c.joined_z} through {c.join_area_mm2:.2f} mm2")
    if a.json:
        a.json.write_text(json.dumps([asdict(c) for c in cols], indent=1))
    return 1 if any(c.risky for c in cols) else 0


if __name__ == "__main__":
    raise SystemExit(main())

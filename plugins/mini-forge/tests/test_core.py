import json
import zipfile

import numpy as np
import pytest
import trimesh

from mini_forge.config import Settings
from mini_forge.islands import landing_coverage
from mini_forge.mesh import scale_to_eye_height, suggest_base_top
from mini_forge.meshy import Ledger, Meshy
from mini_forge.printer import PrinterError, plate_nozzle
from mini_forge.support_audit import audit_supports


def figure_on_base():
    base = trimesh.creation.cylinder(radius=6, height=1.0, sections=64)
    base.apply_translation([0, 0, 0.5])
    body = trimesh.creation.cylinder(radius=2, height=20, sections=64)
    body.apply_translation([0, 0, 10.9])
    return trimesh.boolean.union([base, body], engine="manifold")


def test_scale_to_eye_height_puts_eyes_at_target_on_new_base():
    m = figure_on_base()
    assert suggest_base_top(m, step=0.25) == pytest.approx(1.0, abs=0.26)
    result, factor = scale_to_eye_height(m, feet_z_mm=1.0, eyes_z_mm=17.0, target_eye_height_mm=32)
    assert factor == pytest.approx(2.0)
    assert result.is_volume
    assert result.bounds[1, 2] == pytest.approx(2 + (20.9 - 1.0) * 2, abs=0.01)
    assert result.extents[0] == pytest.approx(25, abs=0.05)


def test_scale_rejects_unordered_landmarks():
    with pytest.raises(ValueError):
        scale_to_eye_height(figure_on_base(), feet_z_mm=17, eyes_z_mm=2)


def gcode(layers, header="", feature_of=None):
    """layers: {z: [(x0, y0, x1, y1, kind)]} with kind 'Support' or 'Outer wall'."""
    lines = [header]
    for z in sorted(layers):
        lines.append(f"; Z_HEIGHT: {z}")
        for x0, y0, x1, y1, kind in layers[z]:
            lines += [f"; FEATURE: {kind}", f"G1 X{x0} Y{y0} F3000", f"G1 X{x1} Y{y1} E0.1"]
    return "\n".join(lines) + "\n"


def column(x, y, z0, z1, step=0.2, kind="Support"):
    return {round(z, 2): [(x - 0.5, y, x + 0.5, y, kind), (x, y - 0.5, x, y + 0.5, kind)]
            for z in np.arange(z0, z1, step)}


def test_support_audit_rejects_tall_slim_tree_on_fine_nozzle(tmp_path):
    header = "; tree_support_branch_diameter = 1.2\n; tree_support_wall_count = 1\n"
    tall = tmp_path / "tall.gcode"
    tall.write_text(gcode(column(100, 100, 0.2, 25), header))
    short = tmp_path / "short.gcode"
    short.write_text(gcode(column(100, 100, 0.2, 12), header))
    assert not audit_supports(tall, 0.2).passed
    assert audit_supports(short, 0.2).passed


def test_landing_coverage_flags_unsupported_island_far_out(tmp_path):
    layers = {}
    for z in np.arange(1.0, 6.0, 0.2):  # a model column
        layers[round(z, 2)] = [(100, 100, 101, 100, "Outer wall"), (100, 100, 100, 101, "Outer wall")]
    island = [(105, 100, 106, 100, "Outer wall"), (105, 100.5, 106, 100.5, "Outer wall"), (105, 101, 106, 101, "Outer wall")]
    for z in (5.0, 5.2, 5.4):
        layers[z] = layers[z] + island
    bare = tmp_path / "bare.gcode"
    bare.write_text(gcode(layers))
    report = landing_coverage(bare, top_gap_mm=0.2, base_top_mm=0.5)
    assert report["risky"] and not report["passed"]
    supported = {**layers, 4.8: layers[4.8] + [(x, y, x + 1, y, "Support") for x in (105,) for y in (100, 100.5, 101)]}
    ok = tmp_path / "ok.gcode"
    ok.write_text(gcode(supported))
    assert landing_coverage(ok, top_gap_mm=0.2, base_top_mm=0.5)["passed"]


def test_analyze_sends_thin_wall_fields(monkeypatch, tmp_path):
    client = Meshy.__new__(Meshy)
    sent = []
    monkeypatch.setattr(client, "_charged", lambda op, path, body, est: sent.append(body) or {})
    client.analyze("task", "fdm", 37.6)
    client.analyze("task", None, None)
    assert sent == [{"input_task_id": "task", "printer_type": "fdm", "intended_print_height_mm": 37.6},
                    {"input_task_id": "task"}]


def test_ledger_tracks_unresolved_tasks(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.record("image-to-3d", "t1", None, status="submitted")
    assert ledger.unresolved == {"t1"} and ledger.total == 0
    ledger.record("image-to-3d", "t1", 25, status="completed")
    assert ledger.unresolved == set() and ledger.total == 25
    assert list(ledger.tasks("image-to-3d")) == ["t1"]


def package(tmp_path, nozzles):
    p = tmp_path / "job.gcode.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Metadata/plate_1.gcode", "".join(f"; nozzle_diameter = {n}\n" for n in nozzles))
    return p


def test_plate_nozzle_reads_single_value(tmp_path):
    assert plate_nozzle(package(tmp_path, ["0.2"])) == 0.2
    with pytest.raises(PrinterError):
        plate_nozzle(package(tmp_path, ["0.2", "0.4"]))


def test_redact_hides_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("MINI_FORGE_HOME", str(tmp_path))
    monkeypatch.setenv("MESHY_API_KEY", "msy_secret_value")
    monkeypatch.setenv("PRINTER_ACCESS_CODE", "12345678")
    s = Settings.load()
    assert s.redact("key msy_secret_value code 12345678") == "key [redacted] code [redacted]"


@pytest.mark.skipif(not Settings.load().slicer_path.exists(), reason="Bambu Studio not installed")
def test_profiles_build_and_materialize(monkeypatch, tmp_path):
    from mini_forge.profiles import build_filament, build_machine, materialize
    monkeypatch.setenv("MINI_FORGE_HOME", str(tmp_path))
    monkeypatch.setenv("PRINTER_MODEL", "Bambu Lab P1S")
    monkeypatch.setenv("FILAMENT", "Bambu PLA Basic @BBL X1C")
    s = Settings.load()
    machine = json.loads(build_machine(s, 0.2).read_text())
    assert "M190" in machine["machine_start_gcode"] or "M140" in machine["machine_start_gcode"]
    build_filament(s, 0.2)
    _m, p, _f, nozzle = materialize(s, "detail-0.2-stout", tmp_path / "job")
    process = json.loads(p.read_text())
    assert nozzle == 0.2
    assert process["support_top_z_distance"] == "0.16"
    assert process["curr_bed_type"] == "Textured PEI Plate"
    assert "Bambu Lab P1S 0.2 nozzle" in process["compatible_printers"]
    assert not any(k.startswith("_") for k in process)


def test_support_audit_sees_trees_on_interleaved_layers(tmp_path):
    """Two objects whose support layers alternate (independent support heights) must not split trees."""
    header = "; tree_support_branch_diameter = 1.2\n; tree_support_wall_count = 1\n"
    a = column(100, 100, 0.2, 25, step=0.24)
    b = column(140, 100, 0.32, 25, step=0.24)
    g = tmp_path / "two.gcode"
    g.write_text(gcode({**a, **b}, header))
    audit = audit_supports(g, 0.2)
    assert audit.tallest_mm > 20 and not audit.passed


def test_support_audit_refuses_tree_strong_and_critical_only_off(tmp_path):
    body = gcode(column(100, 100, 0.2, 10))
    for header, words in (("; support_style = tree_strong\n", "tree_strong"),
                          ("; support_critical_regions_only = 0\n", "critical_regions_only")):
        g = tmp_path / "g.gcode"
        g.write_text(header + body)
        a = audit_supports(g, 0.4)
        assert not a.passed and any(words in r for r in a.reasons)
    ok = tmp_path / "ok.gcode"
    ok.write_text("; support_style = tree_slim\n; support_critical_regions_only = 1\n" + body)
    assert audit_supports(ok, 0.4).passed


def test_support_audit_refuses_supports_rooted_on_the_base(tmp_path):
    def patch(z0, z1):  # a 4 x 4 mm block of support lines, like a trunk's footprint
        return {round(z, 2): [(98 + i * 0.5, 98 + j * 0.5, 98.4 + i * 0.5, 98 + j * 0.5, "Support")
                              for i in range(8) for j in range(8)] for z in np.arange(z0, z1, 0.2)}
    on_base, plate = patch(2.2, 10), patch(0.2, 10)
    g = tmp_path / "base.gcode"
    g.write_text(gcode(on_base))
    a = audit_supports(g, 0.4, base_top_mm=2.0)
    assert a.base_root_share == 1.0 and not a.passed
    g.write_text(gcode(plate))
    assert audit_supports(g, 0.4, base_top_mm=2.0).base_root_share == 0.0


def test_free_columns_flags_a_hanging_feature(tmp_path):
    from mini_forge.free_columns import free_columns
    base = trimesh.creation.cylinder(radius=8, height=2, sections=48); base.apply_translation([0, 0, 1])
    body = trimesh.creation.cylinder(radius=2.5, height=20, sections=48); body.apply_translation([0, 0, 11.9])
    arm = trimesh.creation.box(extents=[6, 2, 1.5]); arm.apply_translation([4.5, 0, 16])
    hang = trimesh.creation.cylinder(radius=0.4, height=7.5, sections=24); hang.apply_translation([7, 0, 12])
    m = trimesh.boolean.union([base, body, arm, hang], engine="manifold")
    stl = tmp_path / "m.stl"; m.export(stl)
    cols = free_columns(stl, layer_mm=0.1)
    risky = [c for c in cols if c.risky]
    assert len(risky) == 1 and risky[0].start_z == pytest.approx(8.25, abs=0.15) and risky[0].xy[0] == pytest.approx(7, abs=0.2)
    upright = trimesh.boolean.union([base, body], engine="manifold"); upright.export(stl)
    assert not any(c.risky for c in free_columns(stl, layer_mm=0.1))


def test_enforcer_points_and_painting(tmp_path):
    from mini_forge.support_paint import enforcer_points, mesh_files_by_stl, paint_plate
    isl = [{"start_z": 8.0, "area_mm2": 0.4, "xy": [7, 0], "gap_to_rest_mm": 4.0},
           {"start_z": 5.0, "area_mm2": 0.4, "xy": [1, 0], "gap_to_rest_mm": 0.3},
           {"start_z": 6.0, "area_mm2": 0.001, "xy": [3, 0], "gap_to_rest_mm": 5.0}]
    assert enforcer_points(isl) == [(7, 0, 8.1)]
    # A one-object project: a downward-facing triangle at z 8 and an upward one at z 8 (object placed at x+100).
    verts = [(6, -1, 8), (8, -1, 8), (7, 1, 8)]
    obj = ("<model><resources><object id=\"1\"><mesh><vertices>"
           + "".join(f'<vertex x="{x - 7}" y="{y}" z="{z}"/>' for x, y, z in verts)
           + '</vertices><triangles><triangle v1="0" v2="2" v3="1"/><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object></resources></model>')
    top = ('<model><resources><object id="2"><components><component p:path="/3D/Objects/object_1.model" objectid="1" '
           'transform="1 0 0 0 1 0 0 0 1 7 0 0"/></components></object></resources></model>')
    proj = tmp_path / "p.3mf"
    with zipfile.ZipFile(proj, "w") as z:
        z.writestr("3D/3dmodel.model", top)
        z.writestr("3D/Objects/object_1.model", obj)
    assert mesh_files_by_stl(proj, {"a.stl": 2, "b.stl": 500}) == {"3D/Objects/object_1.model": "a.stl"}
    out = tmp_path / "painted.3mf"
    counts = paint_plate(proj, out, {"3D/Objects/object_1.model": {"points": [(7, 0, 8.1)]}})
    assert counts == {"3D/Objects/object_1.model": 1}
    text = zipfile.ZipFile(out).read("3D/Objects/object_1.model").decode()
    assert text.count('paint_supports="4"') == 1 and '<triangle v1="0" v2="2" v3="1" paint_supports="4"/>' in text

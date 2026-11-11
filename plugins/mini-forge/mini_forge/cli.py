"""mini-forge command line. Each job lives in ./minis/<job>/ (override with MINI_FORGE_JOBS).

Order of work: setup -> new -> [picture] -> convert -> inspect -> scale -> islands -> slice -> print (optional).
Paid Meshy calls and print starts need --yes; the skill asks the user before passing it.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

import click

from . import __version__
from .config import BED_TYPES, Settings, config_file, profile_dir, system_profile_dir


def jobs_root() -> Path:
    return Path(os.getenv("MINI_FORGE_JOBS") or Path.cwd() / "minis")


def job_dir(job: str, must_exist: bool = True) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", job):
        raise click.BadParameter("job names use lowercase letters, digits and dashes")
    d = jobs_root() / job
    if must_exist and not d.is_dir():
        raise click.ClickException(f"no job {job!r} under {jobs_root()}; create it with `mini-forge new {job}`")
    return d


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def update_job(d: Path, **values) -> dict:
    data = read_json(d / "job.json")
    data.update(values)
    write_json(d / "job.json", data)
    return data


@click.group()
@click.version_option(__version__)
def main() -> None:
    """Photo or description to a printable tabletop miniature."""


# ---- setup -------------------------------------------------------------------------------
@main.command()
@click.option("--printer-model", help='Bambu machine name without nozzle, e.g. "Bambu Lab P1S", "Bambu Lab A1".')
@click.option("--nozzle", type=click.Choice(["0.2", "0.4"]), help="Nozzle installed now.")
@click.option("--filament", help='Bambu Studio filament profile, e.g. "Bambu PLA Basic @BBL X1C".')
@click.option("--bed", type=click.Choice(list(BED_TYPES)), help="Build plate type.")
@click.option("--slicer-path", type=click.Path(dir_okay=False), help="Bambu Studio executable if not in the default place.")
@click.option("--ams-slot", type=click.IntRange(0, 4), help="AMS slot to print from (1-4), 0 for the external spool.")
def setup(printer_model, nozzle, filament, bed, slicer_path, ams_slot) -> None:
    """Save non-secret settings and build machine/filament profiles from the installed Bambu Studio.

    Secrets (MESHY_API_KEY, PRINTER_ACCESS_CODE, PRINTER_SERIAL, PRINTER_HOST) go into the
    config file by hand; this command never prints them.
    """
    from dotenv import set_key

    from .profiles import build_filament, build_machine
    cfg = config_file()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.touch(exist_ok=True)
    for key, value in (("PRINTER_MODEL", printer_model), ("NOZZLE", nozzle), ("FILAMENT", filament), ("BED", bed),
                       ("SLICER_PATH", slicer_path), ("AMS_SLOT", None if ams_slot is None else str(ams_slot))):
        if value is not None:
            set_key(str(cfg), key, value, quote_mode="never")
    for key in ("MESHY_API_KEY", "PRINTER_HOST", "PRINTER_SERIAL", "PRINTER_ACCESS_CODE"):
        if key not in cfg.read_text():
            with cfg.open("a") as f:
                f.write(f"{key}=\n")
    s = Settings.load()
    if not s.slicer_path.exists():
        raise click.ClickException(f"Bambu Studio not found at {s.slicer_path}; pass --slicer-path")
    from .profiles import ProfileError, fitting_filament
    try:
        fitted = fitting_filament(system_profile_dir(s.slicer_path), s.filament, s.printer_model)
    except ProfileError as exc:
        raise click.ClickException(str(exc)) from exc
    if fitted != s.filament:
        click.echo(f"filament: {s.filament!r} is Bambu's profile for another printer; "
                   f"using {fitted!r}, the one Bambu lists for the {s.printer_model}")
        set_key(str(cfg), "FILAMENT", fitted, quote_mode="never")
        s = Settings.load()
    for n in (0.2, 0.4):
        try:
            click.echo(f"built {build_machine(s, n).name}")
            click.echo(f"built {build_filament(s, n).name}")
        except ValueError as exc:
            click.echo(f"skipped {n} mm nozzle: {exc}")
    click.echo(f"settings: {cfg}")
    click.echo(f"model={s.printer_model} nozzle={s.nozzle:g} bed={s.bed} filament={s.filament!r} ams_slot={s.ams_slot}")


@main.command()
def doctor() -> None:
    """Check the slicer, profiles, Meshy key and (if configured) the printer, without showing secrets."""
    s = Settings.load()
    ok = True

    def line(good: bool, text: str) -> None:
        nonlocal ok
        ok &= good
        click.echo(f"[{'ok' if good else '!!'}] {text}")
    line(s.slicer_path.exists(), f"Bambu Studio at {s.slicer_path}" if s.slicer_path.exists() else
         f"Bambu Studio not found at {s.slicer_path}: install it from bambulab.com, or run setup --slicer-path")
    line(system_profile_dir(s.slicer_path).is_dir(), "Bambu system profiles found")
    built = sorted(p.name for p in profile_dir().rglob("*.json")) if profile_dir().exists() else []
    line(bool(built), f"{len(built)} generated profiles in {profile_dir()}" if built else
         "no profiles built yet: run `mini-forge setup` with your printer, nozzle, plate and filament")
    line(bool(s.meshy_api_key), "MESHY_API_KEY set" if s.meshy_api_key else
         f"MESHY_API_KEY missing: create an API key in your Meshy account (API settings) and paste it into {config_file()}")
    if s.meshy_api_key:
        try:
            import tempfile

            from .meshy import Ledger, Meshy
            click.echo(f"     Meshy balance: {Meshy(Ledger(Path(tempfile.mkdtemp()))).balance()} credits")
        except Exception as exc:  # noqa: BLE001
            line(False, f"Meshy API: {s.redact(str(exc))}")
    if s.printer_configured():
        from .printer import Printer
        try:
            click.echo(f"     printer: {Printer(s).status().summary()}")
        except Exception as exc:  # noqa: BLE001
            line(False, f"printer: {s.redact(str(exc))}")
    else:
        click.echo("[--] printer LAN control not configured (optional; slice files can be printed from Bambu Studio)")
    sys.exit(0 if ok else 1)


@main.command("filaments")
@click.argument("search", required=False, default="")
@click.option("--printer-model", help='Show profiles for this printer (default: the one from setup), e.g. "Bambu Lab A1".')
@click.option("--all", "show_all", is_flag=True, help="Also show profiles Bambu made for other printers.")
def filaments(search: str, printer_model: str | None, show_all: bool) -> None:
    """List Bambu Studio filament profiles for your printer matching SEARCH (use the exact name in setup)."""
    from .profiles import filament_fits
    s = Settings.load()
    printer = printer_model or s.printer_model
    system_dir = system_profile_dir(s.slicer_path)
    names = sorted({p.stem for p in (system_dir / "filament").rglob("*.json")
                    if "@base" not in p.stem and " nozzle" not in p.stem and search.lower() in p.stem.lower()})
    for n in names:
        if show_all or filament_fits(system_dir, n, printer):
            click.echo(n)
    if not show_all:
        click.echo(f"(profiles for the {printer}; --all shows every printer's)", err=True)


# ---- job ---------------------------------------------------------------------------------
@main.command()
@click.argument("job")
@click.option("--subject", default="", help="What the mini is, in a few words.")
@click.option("--photo", type=click.Path(exists=True, dir_okay=False), help="Your photo, sketch or artwork for the reference.")
def new(job, subject, photo) -> None:
    """Create a job folder."""
    d = job_dir(job, must_exist=False)
    if d.exists():
        raise click.ClickException(f"{d} already exists; pick another name")
    (d / "reference").mkdir(parents=True)
    if photo:
        src = Path(photo)
        (d / "reference" / f"source{src.suffix.lower()}").write_bytes(src.read_bytes())
    update_job(d, job=job, subject=subject, created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    click.echo(d)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@main.command()
@click.argument("job")
@click.option("--open", "open_folder", is_flag=True, help="Open the job's picture folder in Finder / File Explorer.")
@click.option("--add", "add", type=click.Path(exists=True, dir_okay=False),
              help="Copy this picture (e.g. one the user dragged into the chat) into the picture folder.")
@click.option("--take-download", is_flag=True,
              help="Only if the user turned on downloads pickup: move the Gemini picture just saved to Downloads into the job.")
@click.option("--wait", type=int, default=60, show_default=True, help="Seconds to wait for the download with --take-download.")
def pictures(job, open_folder, add, take_download, wait) -> None:
    """List the pictures in a job's reference folder; optionally open it or add one."""
    ref = job_dir(job) / "reference"
    ref.mkdir(exist_ok=True)
    if take_download:
        s = Settings.load()
        if not s.downloads_pickup:
            raise click.ClickException("downloads pickup is off (the default). Ask the user; only they can turn it on "
                                       "(mini-forge downloads-pickup on). Otherwise they drag the picture into the folder.")
        src = _take_gemini_download(s.downloads_dir, wait)
        dest = ref / src.name
        n = 2
        while dest.exists():
            dest = ref / f"{src.stem}-{n}{src.suffix}"
            n += 1
        import shutil
        shutil.move(str(src), dest)
        click.echo(f"moved {src.name} from Downloads to {dest}")
    if add:
        src = Path(add)
        if src.suffix.lower() not in IMAGE_SUFFIXES:
            raise click.ClickException(f"{src.name} is not a picture ({', '.join(sorted(IMAGE_SUFFIXES))})")
        dest = ref / src.name
        n = 2
        while dest.exists():
            dest = ref / f"{src.stem}-{n}{src.suffix}"
            n += 1
        dest.write_bytes(src.read_bytes())
        click.echo(f"added {dest.name}")
    if open_folder:
        if sys.platform == "win32":
            os.startfile(ref)
        else:
            import subprocess

            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(ref)], check=False)
        click.echo(f"opened {ref}")
    found = sorted((p for p in ref.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES),
                   key=lambda p: p.stat().st_mtime)
    for p in found:
        click.echo(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(p.stat().st_mtime))}  {p.name}")
    if not found:
        click.echo(f"no pictures yet in {ref}")


GEMINI_DOWNLOAD = "Gemini_Generated_Image_*"
PICKUP_WINDOW_S = 120


def _take_gemini_download(folder: Path, wait_s: int) -> Path:
    """The newest finished Gemini_Generated_Image_* picture saved in the last PICKUP_WINDOW_S seconds.
    Only that name pattern is matched; no other file in the folder is opened or reported."""
    end = time.time() + wait_s
    while True:
        now = time.time()
        fresh = [p for p in folder.glob(GEMINI_DOWNLOAD)
                 if p.suffix.lower() in IMAGE_SUFFIXES and now - p.stat().st_mtime <= PICKUP_WINDOW_S]
        if fresh:
            newest = max(fresh, key=lambda p: p.stat().st_mtime)
            size = newest.stat().st_size
            time.sleep(1)
            if size and newest.stat().st_size == size:  # finished writing
                return newest
        if time.time() > end:
            raise click.ClickException(f"no {GEMINI_DOWNLOAD} picture saved in Downloads in the last "
                                       f"{PICKUP_WINDOW_S // 60} minutes; download it again or drag it into the folder")
        time.sleep(2)


@main.command("downloads-pickup")
@click.argument("state", type=click.Choice(["on", "off", "status"]))
def downloads_pickup(state) -> None:
    """Optional, off by default: let `pictures --take-download` move Gemini's saved picture from
    Downloads into the job. Turn on only when the user asks for it; it is recorded in the config."""
    from dotenv import set_key
    cfg = config_file()
    if state != "status":
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.touch(exist_ok=True)
        set_key(str(cfg), "DOWNLOADS_PICKUP", state, quote_mode="never")
        set_key(str(cfg), "DOWNLOADS_PICKUP_CHANGED_UTC", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), quote_mode="never")
    s = Settings.load()
    if s.downloads_pickup:
        click.echo(f"downloads pickup is ON: `pictures --take-download` moves only a file named {GEMINI_DOWNLOAD} saved in "
                   f"the last {PICKUP_WINDOW_S // 60} minutes from {s.downloads_dir}. Nothing else there is opened, "
                   "listed or reported. Turn off: mini-forge downloads-pickup off")
    else:
        click.echo("downloads pickup is OFF (the default): mini-forge never looks in Downloads")


@main.command()
@click.argument("job")
@click.option("--prompt-file", type=click.Path(exists=True, dir_okay=False), required=True,
              help="Short prompt (600 characters at most), e.g. the Meshy prompt from reference-prompts.md.")
@click.option("--edit", type=click.Path(exists=True, dir_okay=False),
              help="Edit this earlier picture instead of starting from the job's photo (a follow-up fix).")
@click.option("--model", default="nano-banana-pro", show_default=True, help="Meshy image model.")
@click.option("--yes", is_flag=True, help="Spend the credits. Without it, only the estimate is shown.")
def picture(job, prompt_file, edit, model, yes) -> None:
    """Optional: make the reference picture with Meshy instead of pasting the prompt into ChatGPT/Gemini.

    Uses image-to-image when there is a source photo (or --edit), text-to-image otherwise.
    Each picture or edit is a paid call (about 9 credits with nano-banana-pro)."""
    from .meshy import IMAGE_TO_IMAGE_PRICE, TEXT_TO_IMAGE_PRICE, Ledger, Meshy, image_urls
    d = job_dir(job)
    prompt = Path(prompt_file).read_text(encoding="utf-8").strip()
    if len(prompt) > 600:
        raise click.ClickException(f"the prompt is {len(prompt)} characters; Meshy's limit is 600")
    sources = [Path(edit)] if edit else sorted((d / "reference").glob("source.*"))
    est = (IMAGE_TO_IMAGE_PRICE if sources else TEXT_TO_IMAGE_PRICE).get(model, 12)
    client = Meshy(Ledger(d))
    if not yes:
        kind = f"image-to-image from {sources[0].name}" if sources else "text-to-image"
        click.echo(f"{kind}: estimated {est} Meshy credits (balance {client.balance()}). Re-run with --yes to spend them.")
        return
    if sources:
        result = client.image_to_image(prompt, [client.image_to_data_uri(sources[0])], ai_model=model)
    else:
        result = client.text_to_image(prompt, ai_model=model)
    urls = image_urls(result)
    if not urls:
        raise click.ClickException(f"Meshy returned no picture (keys: {sorted(result)})")
    n = len(list((d / "reference").glob("attempt-*-meshy.png"))) + 1
    dest = client.download(urls[0], d / "reference" / f"attempt-{n}-meshy.png")
    (d / "reference" / f"attempt-{n}-prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    click.echo(f"saved {dest} | credits spent on this job: {client.ledger.total}")


@main.command()
@click.argument("job")
@click.option("--image", type=click.Path(exists=True, dir_okay=False), required=True, help="The accepted reference picture.")
@click.option("--resolution", type=click.Choice(["4k", "2k", "standard"]), default="4k", show_default=True)
@click.option("--print-height", type=float, help="Planned height in mm, for Meshy's thin-wall report.")
@click.option("--yes", is_flag=True, help="Spend the credits. Without it, only the estimate is shown.")
def convert(job, image, resolution, print_height, yes) -> None:
    """Meshy image-to-3D (untextured, no remesh) and the free printability analysis."""
    from .meshy import I23D, Ledger, Meshy, sha256, thin_walls
    d = job_dir(job)
    ledger = Ledger(d)
    res = None if resolution == "standard" else resolution
    saved = d / "generation.json"
    client = Meshy(ledger)
    if saved.exists():
        result = read_json(saved)
    else:
        earlier = ledger.tasks("image-to-3d")
        if earlier:  # recover instead of paying again
            task_id, row = next(reversed(earlier.items()))
            click.echo(f"recovering earlier task {task_id[:8]} instead of submitting a new one")
            result = client.poll(I23D, task_id)
            if row.get("credits") is None:
                result = client.settle("image-to-3d", task_id, result, row.get("balance_before"), row.get("estimate") or 0)
        else:
            est = Meshy.image_to_3d_estimate(res)
            if not yes:
                click.echo(f"estimated cost: {est} Meshy credits (balance {client.balance()}). Re-run with --yes to spend them.")
                return
            ref = d / "reference" / f"reference{Path(image).suffix.lower()}"
            if Path(image).resolve() != ref.resolve():
                ref.write_bytes(Path(image).read_bytes())
            result = client.image_to_3d(client.image_to_data_uri(ref), geometry_resolution=res)
        write_json(saved, result)
    glb = d / "original.glb"
    if not glb.exists():
        client.download(result["model_urls"]["glb"], glb)
    if not (d / "analyze.json").exists():
        analysis = client.analyze(result["_task_id"], "fdm", print_height)
        write_json(d / "analyze.json", analysis)
        click.echo(f"Meshy thin-wall report (advisory): {json.dumps(thin_walls(analysis))}")
    update_job(d, glb_sha256=sha256(glb), meshy_task=result["_task_id"], credits_spent=ledger.total)
    click.echo(f"saved {glb} | credits spent on this job: {ledger.total} | unresolved: {sorted(ledger.unresolved)}")


@main.command()
@click.argument("job")
def inspect(job) -> None:
    """Clean the GLB into a closed solid, render front/side/back, and suggest the base top."""
    from .mesh import load_glb, normalize, render_views, suggest_base_top
    d = job_dir(job)
    body, info = load_glb(d / "original.glb")
    n = normalize(body, 40.0)
    n.export(d / "normalized.stl")
    render_views(n, d / "views.png", f"{job}, normalised to 40 mm")
    base_top = suggest_base_top(n)
    info.update(normalized_extents_mm=[round(v, 2) for v in n.extents], suggested_base_top_mm=base_top)
    write_json(d / "inspect.json", info)
    click.echo(json.dumps(info))
    click.echo(f"review {d / 'views.png'}: read the sole/base-top and eye heights on the 40 mm grid")


@main.command()
@click.argument("job")
@click.option("--feet", type=float, required=True, help="Sole or base-top height on the 40 mm normalised mesh.")
@click.option("--eyes", type=float, required=True, help="Eye height on the 40 mm normalised mesh.")
@click.option("--target", type=float, default=32.0, show_default=True, help="Feet-to-eyes height in mm (32 = heroic human).")
@click.option("--base", type=float, default=25.0, show_default=True, help="Base diameter in mm.")
@click.option("--base-thickness", type=float, default=2.0, show_default=True)
def scale(job, feet, eyes, target, base, base_thickness) -> None:
    """Scale uniformly by eye height onto a plain round base, then run the screening check."""
    import trimesh

    from .mesh import check_mesh, contacts_on_base, render_views, scale_to_eye_height
    from .meshy import sha256
    d = job_dir(job)
    src = trimesh.load(d / "normalized.stl", force="mesh")
    result, factor = scale_to_eye_height(src, feet_z_mm=feet, eyes_z_mm=eyes, target_eye_height_mm=target,
                                         base_diameter_mm=base, base_thickness_mm=base_thickness)
    result.export(d / "model.stl")
    render_views(result, d / "model-views.png", f"{job} at print size")
    contacts = contacts_on_base(result, base, base_thickness)
    s = Settings.load()
    check = check_mesh(d / "model.stl", s.nozzle, height_range_mm=(target * 0.5, target * 2.5))
    report = {"landmarks_on_normalised_mm": {"feet": feet, "eyes": eyes}, "target_eye_height_mm": target,
              "scale_factor": factor, "height_mm": round(float(result.extents[2]), 2), "base_mm": [base, base_thickness],
              "contacts_on_base": contacts, "model_sha256": sha256(d / "model.stl"), "check": asdict(check),
              "detail_policy": "uniform scale only; no smoothing, remeshing or decimation"}
    write_json(d / "scale.json", report)
    off = [c for c in contacts if c["on_base_fraction"] < 0.95]
    click.echo(check.summary())
    click.echo(f"{len(contacts)} contact(s) on the base" + (f"; {len(off)} partly off the rim: {off}" if off else ""))


@main.command()
@click.argument("job")
@click.option("--from-z", type=float, help="Start above this height (default: just above the base).")
def islands(job, from_z) -> None:
    """List parts that start in mid-air on the scaled model."""
    from .islands import mesh_islands
    d = job_dir(job)
    base_top = read_json(d / "scale.json").get("base_mm", [25, 2])[1]
    found = mesh_islands(d / "model.stl", from_z if from_z is not None else base_top + 0.3)
    write_json(d / "islands.json", found)
    far = [r for r in found if (r["gap_to_rest_mm"] or 0) > 3 or r["area_mm2"] > 0.5]
    for r in sorted(found, key=lambda r: r["start_z"]):
        click.echo(f"  z {r['start_z']:6.2f}  area {r['area_mm2']:6.3f} mm2  at {r['xy']}  {r['gap_to_rest_mm']} mm from the rest  joins {r['joined_z']}")
    click.echo(f"{len(found)} islands; {len(far)} large or more than 3 mm out (fix these in the picture or mesh first)")
    rim = read_json(d / "scale.json").get("base_mm", [25, 2])[0] / 2
    over = [r for r in found if math.hypot(*r["xy"][:2]) < rim]
    if over:
        low = [r for r in over if r["start_z"] < base_top + 10]
        click.echo(f"{len(over)} start(s) over the base ({len(low)} within 10 mm of its top): trees from the plate cannot "
                   "reach under them, so they need supports standing on the base or the figure, which get boxed in and "
                   "are hard to remove. A low ring of them is usually a robe or cloak hem; fix it in the picture "
                   "(hem resting on the base, hands against the body) before allowing those supports.")
    from .free_columns import free_columns
    cols = [asdict(c) for c in free_columns(d / "model.stl", base_top_mm=base_top) if c.height_mm >= 0.5]
    write_json(d / "free-columns.json", cols)
    risky = [c for c in cols if c["risky"]]
    for c in risky:
        click.echo(f"  RISKY free column from z {c['start_z']:.2f} at {c['xy']}: {c['height_mm']} mm before it joins the body, "
                   f"thinnest {c['min_area_mm2']} mm2, joins through {c['join_area_mm2']} mm2")
    click.echo(f"{len(risky)} risky free column(s): a feature that starts below the part it hangs from and grows upward on its "
               "own support tip. Supports do not fix these; tuck the feature against the body in the picture and reconvert, "
               "or accept the risk with the user (slice --accept-free-columns)." if risky else "no risky free columns")


# ---- slice --------------------------------------------------------------------------------
def _parse_set(values: tuple[str, ...]) -> dict:
    out = {}
    for v in values:
        if "=" not in v:
            raise click.BadParameter(f"--set needs key=value, got {v!r}")
        k, val = v.split("=", 1)
        out[k.strip()] = val.strip()
    return out


@main.command("slice")
@click.argument("job")
@click.option("--overlay", default=None, help="Profile overlay (detail-0.2-stout, detail-0.2-slim, standard-0.4).")
@click.option("--copies", type=int, default=1, show_default=True)
@click.option("--set", "sets", multiple=True, help="Extra slicer setting for this job, key=value (repeatable).")
@click.option("--name", default=None, help="Output name (default: the job name).")
@click.option("--no-paint", is_flag=True, help="Do not paint support enforcers at the islands found by `islands`.")
@click.option("--accept-free-columns", is_flag=True, help="The user accepted the risky free columns `islands` reported.")
def slice_cmd(job, overlay, copies, sets, name, no_paint, accept_free_columns) -> None:
    """Slice (painting support enforcers at mid-air starts), then run the support audit and the
    island landing check on the G-code."""
    from .islands import landing_coverage, top_gap_from_gcode
    from .profiles import overlay_nozzle, overlays
    from .slicer import bed_temperature, slice_plate
    from .support_audit import BASE_ROOT_NOTE_SHARE, write_audit
    d = job_dir(job)
    s = Settings.load()
    overlay = overlay or ("detail-0.2-stout" if s.nozzle == 0.2 else "standard-0.4")
    ov = overlays().get(overlay)
    if ov and overlay_nozzle(ov) != s.nozzle:
        raise click.ClickException(f"{overlay} is for a {overlay_nozzle(ov):g} mm nozzle but NOZZLE is {s.nozzle:g}")
    changes = _parse_set(sets)
    if changes.get("support_critical_regions_only") in ("0", "false"):
        raise click.ClickException("support_critical_regions_only=0 is refused: it multiplies supports everywhere. "
                                   "Uncovered starts get painted enforcers instead (on by default).")
    if changes.get("support_style") == "tree_strong":
        raise click.ClickException("support_style=tree_strong is refused: it fuses trees into walls on the base tops.")
    from .support_paint import enforcer_points
    islands_file = d / "islands.json"
    if not islands_file.exists():
        raise click.ClickException(f"run `mini-forge islands {job}` first")
    points = [] if no_paint else enforcer_points(json.loads(islands_file.read_text(encoding="utf-8")))
    cols_file = d / "free-columns.json"
    cols = json.loads(cols_file.read_text(encoding="utf-8")) if cols_file.exists() else []
    risky_cols = [c for c in cols if c.get("risky")]
    name = name or job
    out = d / f"slice-{name}"
    base_top = read_json(d / "scale.json").get("base_mm", [25, 2])[1]
    checked: dict = {}

    def accept(res) -> tuple[bool, int]:
        a = checked["audit"] = write_audit(res.gcode, res.nozzle, out / "support-audit.json", base_top_mm=base_top)
        c = checked["cover"] = landing_coverage(res.gcode, top_gap_from_gcode(res.gcode), base_top + 0.3)
        click.echo(f"  turned {res.turn_deg:g} deg: support audit {'PASS' if a.passed else 'FAIL'}, {len(c['risky'])} risky island(s)")
        return a.passed and c["passed"], len(a.reasons) + len(c["risky"])

    r = slice_plate([d / "model.stl"], overlay, out, name, copies=copies, changes=changes, settings=s,
                    enforcers={d / "model.stl": points}, accept=accept)
    audit, cover = checked["audit"], checked["cover"]
    write_json(out / "island-coverage.json", cover)
    beds = bed_temperature(r.gcode.read_text(encoding="utf-8", errors="replace")[:200000])
    report = {"overlay": overlay, "changes": changes, "copies": copies, "package": r.package.name,
              "enforcer_points": points, "painted_faces": r.painted, "turn_deg": r.turn_deg, "turns_tried": r.attempts,
              "base_root_share": audit.base_root_share,
              "figure_roots": audit.figure_roots, "figure_root_z": audit.figure_root_z,
              "risky_free_columns": risky_cols, "free_columns_accepted": bool(accept_free_columns and risky_cols),
              "estimate_s": r.estimated_time_s, "filament_g": r.filament_g, "layer_mm": r.layer_height, "nozzle": r.nozzle,
              "bed_temperatures": beds, "support_audit_passed": audit.passed, "support_audit_reasons": audit.reasons,
              "island_check_passed": cover["passed"], "risky_islands": cover["risky"],
              "ready": audit.passed and cover["passed"] and (not risky_cols or accept_free_columns)}
    write_json(out / "slice-report.json", report)
    click.echo(r.summary())
    if r.turn_deg:
        click.echo(f"figures turned {r.turn_deg:g} degrees from the slicer's arrangement: "
                   + ("the first turn that passed the checks" if audit.passed and cover["passed"] else "no turn passed; this one had the fewest problems"))
    if points:
        click.echo(f"painted support enforcers at {len(points)} mid-air start(s): {sum(r.painted.values())} faces")
    if risky_cols:
        click.echo(f"risky free columns: {len(risky_cols)} " + ("(accepted by the user)" if accept_free_columns else
                   "(NOT accepted: fix the picture, or pass --accept-free-columns after the user agrees)"))
    click.echo(f"bed temperature commands: {beds} (check they match your plate)")
    click.echo(f"support audit: {'PASS' if audit.passed else 'FAIL'} ({audit.columns} columns, tallest {audit.tallest_mm} mm)"
               + "".join(f"\n  - {x}" for x in audit.reasons))
    if audit.base_root_share > BASE_ROOT_NOTE_SHARE:
        click.echo(f"note: {audit.base_root_share:.0%} of support roots start on the base top; they come off, but can mark it")
    if audit.figure_roots:
        click.echo(f"note: supports stand on the figure itself in about {audit.figure_roots} places "
                   f"(z {min(audit.figure_root_z):.1f} to {max(audit.figure_root_z):.1f} mm). Under a cloak, robe or arm "
                   "they get boxed in and are the hardest to remove; the checks above do not measure that. "
                   "Show the user where they are before calling it ready")
    click.echo(f"islands: {len(cover['islands'])} start in air; {len(cover['risky'])} risky (>3 mm out, <20% supported)")
    for row in cover["islands"]:
        click.echo(f"  z {row['z']:6.2f} at {row['xy']}: {row['from_model_mm']} mm out, {row['support_coverage']:.0%} supported")
    click.echo(f"{'READY' if report['ready'] else 'NOT READY'}: {r.package}")


# ---- printer (optional) --------------------------------------------------------------------
@main.command("print")
@click.argument("job")
@click.option("--name", default=None, help="Slice name (default: the job name).")
@click.option("--plate-clear", is_flag=True, help="The user confirmed the build plate is empty.")
@click.option("--yes", is_flag=True, help="The user approved starting this print.")
@click.option("--reprint", is_flag=True, help="The user wants this already-sent package printed again; the old receipt is archived.")
def print_cmd(job, name, plate_clear, yes, reprint) -> None:
    """Upload and start a sliced job on a Bambu printer over LAN, after all gates pass."""
    from .printer import Printer, preflight
    d = job_dir(job)
    out = d / f"slice-{name or job}"
    report = read_json(out / "slice-report.json")
    package = out / report.get("package", "missing")
    if not report.get("ready"):
        raise click.ClickException("the slice is not READY (support audit or island check failed); fix it or re-slice")
    if not (plate_clear and yes):
        raise click.ClickException("starting a print needs the user's approval and a clear plate: --plate-clear --yes")
    receipt = out / "print-receipt.json"
    if receipt.exists() and not reprint:
        raise click.ClickException(f"{receipt} exists: this package was already sent. Check the printer instead of resending; "
                                   "for a print the user asked to repeat, add --reprint")
    s = Settings.load()
    p = Printer(s)
    st = preflight(p, package)
    click.echo(f"preflight ok: {st.summary()}")
    if receipt.exists():
        archived = receipt.with_name(f"print-receipt-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(receipt.stat().st_mtime))}.json")
        receipt.rename(archived)
        click.echo(f"reprint: previous receipt kept as {archived.name}")
    size = p.upload(package)
    click.echo(f"uploaded {size} bytes")
    preflight(p, package)
    write_json(receipt, {"package": package.name, "bytes": size, "requested_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "ams_slot": s.ams_slot})
    reply = p.start(package.name)
    update_job(d, printed=package.name)
    click.echo(f"start acknowledged: {reply.get('result')}")


@main.command()
def status() -> None:
    """One status read from the printer."""
    from .printer import Printer
    click.echo(Printer().status().summary())


@main.command()
@click.argument("dest", type=click.Path(dir_okay=False))
def camera(dest) -> None:
    """Save one chamber camera frame (P1/A1 series)."""
    from .printer import Printer
    click.echo(Printer().camera_frame(Path(dest)))


@main.command()
@click.option("--until-layer", type=int, default=0, help="Stop at this layer (checkpoint); 0 = until the job ends.")
@click.option("--every", type=int, default=30, show_default=True, help="Seconds between checks (local; no extra printer traffic).")
@click.option("--full-every", type=int, default=300, show_default=True,
              help="Seconds between full status requests to the printer. Keep 300 or more on P1/A1 printers.")
@click.option("--max-minutes", type=int, default=600, show_default=True)
def watch(until_layer, every, full_every, max_minutes) -> None:
    """Read-only watcher over one printer connection: exits when the job ends, on an error/HMS,
    part fan 0 while printing, a checkpoint, or when the printer stops reporting."""
    import signal

    from .printer import Printer, status_from
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # close the connection cleanly when stopped
    last, t0 = None, time.time()
    for st_raw, silent_s in Printer().monitor(max_minutes * 60, check_s=every, full_s=full_every):
        if not st_raw.get("gcode_state"):
            if time.time() - t0 < 120:
                continue
            click.echo("EXIT no report from the printer (check it is on and in LAN mode)")
            return
        if silent_s is not None and silent_s > max(full_every * 2, 600):
            click.echo(f"EXIT the printer has not reported for {silent_s / 60:.0f} min")
            return
        st = status_from(st_raw)
        row = {k: getattr(st, k) for k in ("state", "percent", "layer", "total_layers", "part_fan", "print_error")}
        if row != last:
            click.echo(json.dumps({"t": time.strftime("%H:%M:%S"), **row, "hms": len(st.hms)}))
            last = row
        running = st.state == "RUNNING" and st.percent < 100  # PREPARE still shows the previous job's layer
        if st.state not in ("RUNNING", "PREPARE", "SLICING"):
            click.echo(f"EXIT job state {st.state}")
            return
        if st.print_error or st.hms:
            click.echo("EXIT error or HMS alert")
            return
        if running and st.layer >= 8 and st.part_fan == "0":
            click.echo("EXIT part fan reads 0 while printing (check the toolhead cover/fan)")
            return
        if until_layer and running and st.layer >= until_layer:
            click.echo(f"EXIT checkpoint layer {st.layer}")
            return
    click.echo("EXIT watch time limit")

if __name__ == "__main__":
    main()

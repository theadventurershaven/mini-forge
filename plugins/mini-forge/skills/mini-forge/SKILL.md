---
name: mini-forge
description: Turn a photo, card or description into a printable tabletop miniature - reference picture via ChatGPT/Gemini, Meshy image-to-3D, mesh checks and scaling, Bambu Studio slicing with tested support profiles, support and mid-air-feature review, optional Bambu LAN printing. Use when the user wants to make, generate or 3D print a miniature or figurine.
argument-hint: "[what to make, or a photo]"
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT} mini-forge *)
---

# mini-forge: photo or description in, printable miniature out

Run every command as `uv run --project ${CLAUDE_PLUGIN_ROOT} mini-forge <command>` (written
`mini-forge` below). Jobs live in `./minis/<job>/` under the current folder. Show the user the
renders and reports at each review point; keep messages short.

## Rules

- **Money:** a Meshy conversion costs credits (about 25 at 4k). Show the estimate from
  `mini-forge convert` (without `--yes`) and get the user's yes before re-running with `--yes`.
  Never buy credits. If a run was interrupted, `convert` recovers the existing task instead of
  paying again.
- **Printing:** only with the user's explicit yes in this conversation **and** their statement
  that the plate is clear (`--plate-clear --yes`). One yes = one print start. Never retry,
  resume or restart a print on your own.
- **Secrets:** the Meshy key and printer access code live in `~/.mini-forge/config.env`. Never
  print, echo or log them; ask the user to paste them into that file themselves.
- **Detail:** never smooth, remesh, decimate or globally thicken the model. A thin warning means
  "look at which parts carry load", not "thicken". Meshy's thin-wall report is advisory only:
  its 1.0 mm minimum flags relief that a 0.2 mm nozzle prints fine.
- **Gates are not flags to turn off.** If the support audit or island check fails, change the
  model or the supports, never the check.

## 0. Setup (once)

1. Check `mini-forge doctor`. If it has not been set up, ask the user for their printer model,
   installed nozzle (0.2 for detail, 0.4 for speed), plate type and filament, then run
   `mini-forge setup --printer-model "Bambu Lab P1S" --nozzle 0.4 --bed textured --filament "..." --ams-slot 1`.
   `mini-forge filaments <word>` lists exact filament profile names.
2. Ask the user to put `MESHY_API_KEY=` (and, only for LAN printing, `PRINTER_HOST`,
   `PRINTER_SERIAL`, `PRINTER_ACCESS_CODE`) into the config file `setup` printed. LAN printing
   also needs LAN Only Mode and Developer Mode on the printer's network settings screen.
3. Re-run `mini-forge doctor`.

## 1. Job and reference picture

1. `mini-forge new <job> --subject "..." [--photo PATH]`.
2. Fill the first prompt from [reference-prompts.md](reference-prompts.md) and give it to the
   user to paste into ChatGPT or Gemini with their image. Ask them to return the picture.
3. Review the picture at full size (checklist in reference-prompts.md). For each hand, claw,
   cloth corner or weapon tip that would start in mid-air, give the user the matching follow-up
   edit. Accept the picture when everything touches something.

## 2. Meshy conversion

`mini-forge convert <job> --image PATH --print-height 38` shows the cost; after the user's yes,
add `--yes`. It saves `original.glb`, the free analysis and the ledger in `logs/`.

## 3. Prepare the mesh

1. `mini-forge inspect <job>`; read `views.png` (front/side/back on a 40 mm grid) and check the
   pose, limbs, equipment and back. It suggests the base top (where a sculpted base ends).
2. Read two heights on the 40 mm grid: the **sole or base top** and the **eyes**. Then
   `mini-forge scale <job> --feet F --eyes E [--target 32] [--base 25]`. Use 32 mm feet-to-eyes for
   a heroic human, about 25 for a dwarf, smaller for small creatures; for animals choose a
   size that reads right next to human minis and say what you chose.
3. Check `model-views.png`, the contacts on the base (all inside the rim) and the screening check.
4. `mini-forge islands <job>`: anything large or more than 3 mm from the rest of its layer is a
   feature that will likely fail. Fix it in the reference picture and reconvert (asking about
   the cost), or ask the user.

## 4. Slice and review

`mini-forge slice <job> [--overlay NAME] [--set key=value]`. Overlays (in `mini_forge/overlays/`,
each with notes on how well it has been tested):
- `detail-0.2-stout` (0.2 mm nozzle, default): stout trees from the plate; best tested.
- `detail-0.2-slim`: finer trees, only when supports stay short (the audit enforces it).
- `standard-0.4` (0.4 mm nozzle, default): faster prints for creatures and rank-and-file.

It prints the estimate, the bed temperatures (must match the plate), the **support audit**
(tall slender trees fall over mid-print) and the **island check** (support coverage under each
feature that starts in air). Report anything 3+ mm out with under 20% support as a blocker:
try `--set support_on_build_plate_only=0` (supports may then touch the base or model and leave
marks; tell the user and let them choose), or fix the geometry. `READY` means both passed.
Show the user the preview, time, grams and any small unsupported islands (they may droop
slightly).

## 5. Print

Without LAN printing: give the user the `.gcode.3mf` path to open and print from Bambu Studio,
with the nozzle and plate it needs.

With LAN printing, after the user's yes and plate-clear statement:
`mini-forge print <job> --plate-clear --yes`. It refuses unless the printer is idle with no
error, the nozzle matches the package, and the AMS slot has filament.

Then watch: `mini-forge watch --until-layer 40` (run it in the background), a camera frame with
`mini-forge camera minis/<job>/first-layers.jpg`, then again near halfway and at the end. A part
that comes loose raises no printer error, so the camera checks matter. On a clear failure,
tell the user; pause only if they ask (`status`, then the printer screen). Keep one printer
connection at a time.

## 6. Afterwards

Ask the user how the supports came off and how the risky features printed, and note it in the
job folder. That is how the overlays' evidence grows.

---
name: mini-forge
description: Turn a one-line description, sketch or photo into a printable tabletop miniature - reference picture via Gemini/ChatGPT (free) or Meshy, Meshy image-to-3D, mesh checks and scaling, Bambu Studio slicing with tested support profiles, support and mid-air-feature review, optional Bambu LAN printing. Use when the user wants to make, generate or 3D print a miniature or figurine.
argument-hint: "[what to make, or a photo]"
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT} mini-forge *)
---

# mini-forge: description or picture in, printable miniature out

Run every command as `uv run --project ${CLAUDE_PLUGIN_ROOT} mini-forge <command>` (written
`mini-forge` below). Jobs live in `./minis/<job>/` under the current folder. Show the user the
renders and reports at each review point; keep messages short.

## Rules

- **Whose design:** only the user's own characters, things they have rights to, or designs used
  with the owner's permission. If the request is to copy a commercial character or a bought
  miniature, say so plainly and suggest an original take instead. Never put an artist's name or
  a franchise in a prompt.
- **Money:** a Meshy conversion costs credits (about 25 at 4k); a Meshy picture about 9. Show the
  estimate (each paid command prints it without `--yes`) and get the user's yes before re-running with `--yes`.
  Never buy credits. If a run was interrupted, `convert` recovers the existing task instead of
  paying again.
- **Printing:** only with the user's explicit yes in this conversation **and** their statement
  that the plate is clear (`--plate-clear --yes`). One yes = one print start. Never retry,
  resume or restart a print on your own. To print the same package again, the user must ask for
  that print; add `--reprint` (the old receipt is archived).
- **Secrets:** the Meshy key and printer access code live in `~/.mini-forge/config.env`. Never
  print, echo or log them; ask the user to paste them into that file themselves.
- **Detail:** never smooth, remesh, decimate or globally thicken the model. A thin warning means
  "look at which parts carry load", not "thicken". Meshy's thin-wall report is advisory only:
  its 1.0 mm minimum flags relief that a 0.2 mm nozzle prints fine.
- **Gates are not flags to turn off.** If the support audit or island check fails, change the
  model or the supports, never the check.
- **Supports:** never turn off "critical regions only" and never use `tree_strong`; both have
  produced masses of unremovable support, and `slice` refuses them. An uncovered start gets a
  painted enforcer (automatic) or a geometry fix.
- **Supports must come off by hand.** The default profiles grow trees from the build plate only.
  `--set support_on_build_plate_only=0` lets them stand on the base top **and on the figure
  itself**: under a cloak, robe, skirt or arm they get boxed in, fuse to the cloth and are nearly
  impossible to remove (a cloaked rat-man came out this way). Never add it on your own or just in
  case. Use it only when a slice has already failed without it, and ask first in those words:
  "supports would also stand on the figure, under the [cloak], and may be very hard to remove".

- **First run:** the first `mini-forge` command on a computer downloads its Python packages (a
  minute or two). Before running any `mini-forge` command for the first time, say so in one line
  and wait for the user's OK.

## 0. Setup (once)

0. Check `uv --version`. If uv is missing, tell the user mini-forge needs it to run its Python
   tools and offer to install it with the official command; run it only after their yes:
   macOS/Linux `curl -LsSf https://astral.sh/uv/install.sh | sh`, Windows
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. If `uv`
   is still not found afterwards, call it by full path (`~/.local/bin/uv`, Windows
   `%USERPROFILE%\.local\bin\uv.exe`) for the rest of this session.
1. Check `mini-forge doctor`. If Bambu Studio is missing, give the user the download link
   (https://bambulab.com/en/download/studio) and wait for them to install it. If it has not been set up, ask the user for their printer model,
   installed nozzle (0.2 for detail, 0.4 for speed), plate type and filament, then run
   `mini-forge setup --printer-model "Bambu Lab P1S" --nozzle 0.4 --bed textured --filament "..." --ams-slot 1`.
   `mini-forge filaments <word>` lists the exact names of Bambu's profiles for their printer
   (brands ship one per printer family; the P1S uses the `@BBL X1C` ones, not `@BBL P1P`).
   `setup` switches to the right printer's variant itself and says so.
2. Ask the user to put `MESHY_API_KEY=` (and, only for LAN printing, `PRINTER_HOST`,
   `PRINTER_SERIAL`, `PRINTER_ACCESS_CODE`) into the config file `setup` printed. LAN printing
   also needs LAN Only Mode and Developer Mode on the printer's network settings screen.
3. Re-run `mini-forge doctor`.

## 1. Job and reference picture

1. `mini-forge new <job> --subject "..." [--photo PATH]`. With only a description, ask for a
   little more if it is thin: build, clothing, what it holds and how, pose.
2. Make the reference picture, using [reference-prompts.md](reference-prompts.md) ("from a
   description" or "from an image"):
   Offer the routes below in one short line each and let the user choose (default: by hand).
   Never look in the user's Downloads or other folders; pictures reach you only through the
   job's picture folder, a file the user drags into the chat, or the opt-in Downloads pickup below.
   - **Free, by hand (default):** fill the full prompt and give it to the user to paste into
     Gemini ("Pro" model) or ChatGPT, with their image if any. Run `mini-forge pictures <job> --open`
     so the job's picture folder opens, and ask them to drag the finished picture into it
     (straight from the browser or from wherever they saved it), or into this chat; for a file
     dragged into the chat run `mini-forge pictures <job> --add <path>`. Then
     `mini-forge pictures <job>` lists what arrived.
   - **Free, Claude drives the browser (optional):** always offer it. It needs the Claude in
     Chrome extension connected to this session (https://code.claude.com/docs/en/chrome); if the
     browser tools aren't available, say that and fall back to by hand. Say first that you will work in a new
     tab of their own browser, in their signed-in Gemini account, and touch nothing else. Open
     gemini.google.com/app in a new tab, start a new chat, choose the "Pro" model, attach their
     image if any (with the browser upload tool, or ask them to attach it in that tab), and send
     the prompt (Enter sends, so join its paragraphs with spaces). Pictures take about a minute;
     retry once on an error. Review the picture in the tab yourself and send the follow-up edits
     there (step 3). When it is accepted, check `mini-forge downloads-pickup status`:
     - **On:** click the picture's "Download full size image" button in the tab (the last one is
       the newest), then run `mini-forge pictures <job> --take-download`.
     - **Off (the default):** run `pictures <job> --open` and ask the user to drag the picture from
       the Gemini tab into the folder. The first time in a session, you may offer the optional
       Downloads pickup in these words: "I can save the picture for you: I'd click Gemini's download
       button and move only that one file (named Gemini_Generated_Image_...) from your Downloads
       into the job. Nothing else in Downloads is opened or listed. Want me to turn that on?" Run
       `mini-forge downloads-pickup on` only after a clear yes, never on your own, and never offer
       it again after a no. `downloads-pickup off` turns it off.
   - **Automatic (paid):** write the short prompt to `minis/<job>/reference/prompt.txt`, run
     `mini-forge picture <job> --prompt-file ...` for the estimate, then add `--yes` after their yes.
3. Review the picture at full size (checklist in reference-prompts.md). For each hand, claw,
   cloth corner, tail or weapon tip that would start in mid-air or hang below what it belongs to,
   use the matching follow-up edit: give it to the user to paste (by hand), send it yourself
   (browser route), or `picture --edit` (paid). Accept the picture when everything touches something.

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
   Look for a weapon, blade or staff that touches the base only by a corner or tip and rises
   from there before it reaches the hand: no check catches it, and it gets knocked loose mid-print.
   Fix it in the picture (raised, or flat against the body along its length), not by lifting it
   off the base.
4. `mini-forge islands <job>`: lists where features start in mid-air (these get painted
   supports at slicing) and **risky free columns**: a feature that starts below the part it
   hangs from and grows upward on its own support tip before joining the body. Those broke off
   on real prints even when fully supported. Fix them in the reference picture and reconvert
   (asking about the cost), or show them to the user and let them accept the risk.
   It also lists **starts over the base**: plate trees cannot reach under them, so they would
   need supports on the base or figure. A low ring of them is a robe or cloak hem. Recommend the
   picture fix first (the matching follow-up edit, then reconvert, asking about the cost) and offer
   on-base supports only as the second choice, saying they may be very hard to remove.

## 4. Slice and review

`mini-forge slice <job> [--overlay NAME] [--set key=value]`. Overlays (in `mini_forge/overlays/`,
each with notes on how well it has been tested):
- `detail-0.2-stout` (0.2 mm nozzle, default): stout trees from the plate; best tested.
- `detail-0.2-slim`: finer trees, only when supports stay short (the audit enforces it).
- `standard-0.4` (0.4 mm nozzle, default): faster prints for creatures and rank-and-file.
- `creature-0.4-stout` (0.4 mm): stout two-wall trees that may root on the base top, for high,
  far-reaching overhangs (tentacles, raised claws). Ask the user first; thick trees around small
  faces and hands are harder to remove.

Before slicing it paints support enforcers at the mid-air starts `islands` found (`--no-paint`
to skip). Afterwards it prints the estimate, the bed temperatures (must match the plate), the
**support audit** (tall slender trees fall over mid-print; refused styles) and the
**island check** (support coverage under each feature that starts in air). Where the slicer
plants trees depends on how the figure is turned, so when either check fails `slice` turns the
arranged figures in place (90, 180, 270, then the 45s) and re-slices, keeping the first turn that
passes; tell the user the turn it used. If no turn passes, anything 3+ mm out with under 20%
support is a blocker: fix the geometry (the reference picture, so the feature touches the body), or
ask the user as in the Supports rule. When most support roots start on the base top, the output
says so; mention it (they come off but can mark the base). Risky free columns block until the user
accepts them (`--accept-free-columns`). `READY` means all of it passed; the checks do not measure how hard supports are
to remove. If the output says supports stand on the figure, say where (under the cloak, between
the legs) before the user prints. Show the user the preview, time, grams and any small
unsupported islands (they may droop slightly).

## 5. Print

Without LAN printing: give the user the `.gcode.3mf` path to open and print from Bambu Studio,
with the nozzle and plate it needs.

With LAN printing, after the user's yes and plate-clear statement:
`mini-forge print <job> --plate-clear --yes`. It refuses unless the printer is idle with no
error, the nozzle matches the package, and the AMS slot has filament.

Then watch: `mini-forge watch --until-layer 40` (run it in the background; it keeps one printer
connection open and asks for a full report only every 5 minutes, since frequent reconnects have
frozen a P1S mid-print). Do not run `status` while a watch is running. Take a camera frame with
`mini-forge camera minis/<job>/first-layers.jpg`, then again near halfway and at the end. A part
that comes loose raises no printer error, so the camera checks matter. On a clear failure,
tell the user; pause only if they ask (`status`, then the printer screen). Keep one printer
connection at a time.

## 6. Afterwards

Ask the user how the supports came off and how the risky features printed, and note it in the
job folder. That is how the overlays' evidence grows.

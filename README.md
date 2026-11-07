# mini-forge

A Claude Code plugin that turns a one-line description, a sketch or a photo into a printable
tabletop miniature, and checks it the way an experienced FDM mini printer would before you
waste a night of printing.

```
"a hunched plague rat-man with a rusted cleaver"
   ──► reference picture (Gemini / ChatGPT, free; or Meshy, paid)
   ──► Meshy image-to-3D ──► clean + scale by eye height onto a 25 mm base
   ──► mid-air feature check ──► Bambu Studio slice with tested support profiles
   ──► support audit ──► .gcode.3mf for Bambu Studio, or (optional) a LAN print on a Bambu printer
```

**This runs in [Claude Code](https://claude.com/claude-code)** (the terminal / desktop app), not
on the claude.ai website: it needs to run Bambu Studio's slicer and, optionally, reach your
printer on your home network.

## What you need

| | |
|---|---|
| Claude Code | Any paid Claude plan that includes Claude Code. |
| [uv](https://docs.astral.sh/uv/) | One-line install; runs the plugin's Python tools. |
| [Bambu Studio](https://bambulab.com/en/download/studio) | Installed normally; its command-line slicer is used. |
| A Bambu Lab printer | Tested on a P1S with 0.4 and 0.2 mm nozzles. Other Bambu models should work but are untested. Other brands: the mesh steps work, slicing does not yet. |
| A [Meshy](https://www.meshy.ai) plan with API access | Meshy lists API access on Pro and above (check their pricing page). About **25 credits per mini**; about 9 more per picture if you let Meshy make the reference picture. |
| Gemini or ChatGPT (optional) | Free route for the reference picture: the plugin writes the prompt, you paste it. |

## Install

In Claude Code:

```
/plugin marketplace add theadventurershaven/mini-forge
/plugin install mini-forge@mini-forge-marketplace
```

Then just ask: *"make a mini of a hunched plague rat-man with a rusted cleaver"*, or attach a
sketch or photo, or run `/mini-forge`. The first run walks you through setup (printer model,
nozzle, plate, filament) and tells you where to paste your Meshy API key
(`~/.mini-forge/config.env`; Claude never reads it back into the conversation).

Updates arrive when you run `/plugin marketplace update`.

## What happens at each step

| Step | Command | What it checks |
|---|---|---|
| Reference picture | you in Gemini/ChatGPT, or `mini-forge picture` | Every hand, claw, tail and weapon touches something; feet on the base; nothing hangs down |
| Conversion | `mini-forge convert` | Shows the credit cost first; recovers interrupted tasks instead of paying twice |
| Inspect | `mini-forge inspect` | Closed solid, front/side/back renders, where the sculpted base ends |
| Scale | `mini-forge scale` | Uniform scale by feet-to-eye height (32 mm heroic human) onto a plain 25 mm base |
| Islands | `mini-forge islands` | Parts that start in mid-air, and parts that hang below what they belong to (these break even when supported) |
| Slice | `mini-forge slice` | Paints supports under mid-air starts, then audits the supports (too tall, too leaning, too many on the base) and checks coverage under every mid-air feature |
| Print | `mini-forge print` | Only with your yes and a clear plate; printer idle, right nozzle, filament loaded |

Every paid step shows its cost and waits for your yes. Nothing prints without your yes.

## Lessons built in (from real prints)

- **Fix mid-air features in the picture.** A hanging arm and a drooping tail broke off twice
  each while fully supported; tucked and raised, they printed. One follow-up edit to the picture
  is cheaper than any support setting.
- **Use Meshy's GLB, not its STL.** The STL export is simplified and full of broken faces.
- **Scale by eye height, not total height.** Raised weapons, hats and horns make total height lie.
- **Paint a support where it is missing; never turn on supports everywhere.** Turning off
  "critical regions only" multiplied supports every time it was tried. `slice` refuses it, and
  refuses the "strong" tree style, which fused supports into walls that would not come off.
- **Check support under each feature, not just the settings.** A print failed with settings
  that passed every global check because one leg had 21% support under it.
- **Tall supports must be stout.** A slim 29 mm tree fell over mid-print and took a shield with it.
- **Never smooth, remesh or thicken the whole model.** It costs the detail you came for.

## Profiles

mini-forge ships only its own setting changes (`plugins/mini-forge/mini_forge/overlays/`), each
with notes on what has actually been printed:

- `standard-0.4`: 0.4 mm nozzle, 0.12 mm layers, slim trees from the build plate. Default.
- `creature-0.4-stout`: 0.4 mm, stout trees that may also stand on the base top, for tentacles
  and raised claws. Asks first, since supports on the base can mark it.
- `detail-0.2-stout` / `detail-0.2-slim`: 0.2 mm nozzle, 0.06 mm layers, for heroes.

Full profiles and printer start G-code are built on your computer from your installed Bambu
Studio, so they always match your version.

## Use it on your own designs

Use mini-forge for your own characters, for things you have the rights to, or with the
creator's permission. Please don't use it to copy, share or sell other people's miniatures or
characters. Meshy's and Google's/OpenAI's terms also make you responsible for having the rights
to what you upload.

The pictures and models come from generative AI (Gemini/ChatGPT or Meshy for pictures, Meshy
for 3D).

## Status and limits

Early, and tested on one printer: a Bambu Lab P1S with SUNLU PLA+. The support profiles and
checks come from real prints on it; the plugin itself has been run from mesh to sliced file on
real models. Known limits:

- Slicing needs Bambu Studio and a Bambu printer profile.
- Where the slicer plants trees depends on how the figure is turned on the plate: one creature's
  claw went from 75% supported to 0% between two angles. `slice` turns the figures and re-slices
  until the checks pass, and says which turn it used; if none passes, do not ignore the flagged
  start.
- Many-legged creatures need a per-leg review; one scorpion lost its legs.

Reports from other printers and filaments are welcome as GitHub issues.

## Licence

MIT. Not affiliated with or endorsed by Bambu Lab, Meshy, Google, OpenAI or Anthropic.

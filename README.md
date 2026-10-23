# mini-forge

A Claude Code plugin that turns a photo, a game card or a description into a printable
tabletop miniature, and checks it the way an experienced FDM mini printer would before you
waste a night of printing.

```
your photo ──► ChatGPT / Gemini reference picture ──► Meshy image-to-3D ──► clean + scale onto a base
           ──► Bambu Studio slice (tested support profiles) ──► support + mid-air feature review
           ──► .gcode.3mf for Bambu Studio, or (optional) a LAN print on a Bambu printer
```

## What you need

- [Claude Code](https://claude.com/claude-code) and [uv](https://docs.astral.sh/uv/).
- [Bambu Studio](https://bambulab.com/en/download/studio) installed (its command-line slicer is used).
- A Bambu Lab printer (tested on a P1S; other Bambu models should work but are untested).
  Other printers: the mesh steps work, but slicing currently needs Bambu Studio's profiles.
- A [Meshy](https://www.meshy.ai) account with API access and credits: about 25 credits per mini.
- ChatGPT or Gemini to make the reference picture (you paste a prompt the plugin writes).

## Install

```
/plugin install mini-forge --marketplace theadventurershaven/mini-forge
```

(or `/plugin marketplace add theadventurershaven/mini-forge` then `/plugin install mini-forge@mini-forge-marketplace`).

Then ask Claude: *"make a mini of this"* with a photo, or run `/mini-forge`. The first run walks
you through setup: printer model, nozzle, plate, filament, and where to paste your Meshy key
(`~/.mini-forge/config.env`; never shared with the conversation).

## What it does at each step

| Step | Command | What it checks |
|---|---|---|
| Reference picture | (you, in ChatGPT/Gemini) | Every hand, claw and weapon touches something; feet on the base |
| Conversion | `mini-forge convert` | Shows the credit cost first; recovers interrupted tasks instead of paying twice |
| Inspect | `mini-forge inspect` | Closed solid, front/side/back renders, where the sculpted base ends |
| Scale | `mini-forge scale` | Uniform scale by feet-to-eye height (32 mm heroic human) onto a 25 mm base |
| Islands | `mini-forge islands` | Parts that would start printing in mid-air |
| Slice | `mini-forge slice` | Support audit (tall thin trees fall over) and support coverage under every mid-air feature |
| Print | `mini-forge print` | Only with your yes and a clear plate; printer idle, right nozzle, filament loaded |

## Lessons built in

- **Use Meshy's GLB, not its STL.** The STL export is decimated and full of broken faces.
- **Scale by eye height, not bounding box.** Weapons, hats and bases make bounding boxes lie.
- **Fix mid-air features in the picture.** One follow-up edit ("press the claws against the
  robe") is cheaper than reinforcing a mesh or losing a hand on the printer.
- **Check support under each feature, not just the settings.** A print failed with settings
  that passed every global check because one leg had 21% support under it.
- **Tall supports must be stout.** A slim 29 mm tree fell over mid-print and took a shield with it.
- **Never smooth or thicken the whole model.** Reinforce only what carries load.

## Profiles

mini-forge ships only its own setting changes (`plugins/mini-forge/mini_forge/overlays/`), each
with notes on what has actually been printed. Full profiles and printer start G-code are built
on your computer from your installed Bambu Studio, so they always match your version.

## Status

Early. The support profiles and checks come from real prints on a Bambu Lab P1S (0.2 and 0.4 mm
nozzles); the plugin itself has been tested from mesh to sliced file. Reports from other printers
and filaments are welcome.

## Licence

MIT. Not affiliated with Bambu Lab, Meshy, OpenAI or Google.

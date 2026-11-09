# mini-forge

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/theadventurershaven)

A Claude Code plugin that takes a tabletop miniature from concept to print with as little hand
work as possible. Describe a character, or give it a sketch or photo, and it makes the reference
picture, has Meshy turn it into a 3D model, scales it onto a base, sets up supports and slices
it for your Bambu Lab printer, checking each step the way an experienced mini printer would.

```
"a hunched plague rat-man with a rusted cleaver"
   ──► reference picture (Gemini / ChatGPT, free; or Meshy, paid)
   ──► Meshy image-to-3D ──► clean + scale by eye height onto a 25 mm base
   ──► mid-air feature check ──► Bambu Studio slice with tested support profiles
   ──► support audit ──► .gcode.3mf for Bambu Studio, or (optional) a LAN print on a Bambu printer
```

**For your own designs.** Use it on characters you created, things you have the rights to, or
with the creator's permission; not to copy other people's miniatures, characters or game art
([details](#use-it-on-your-own-designs)).

## Get started

1. **Get the [Claude desktop app](https://claude.com/download)** (Mac or Windows), sign in and
   open its **Code** tab. That is Claude Code, which comes with any paid Claude plan that
   includes it. mini-forge needs Claude Code, not regular Claude chat or Cowork, because it runs
   Bambu Studio's slicer on your computer. (Claude Code in a terminal works the same way.)
2. **Add mini-forge.** In the Code tab's message box, send this:
   ```
   /plugin marketplace add theadventurershaven/mini-forge
   ```
   then this:
   ```
   /plugin install mini-forge@mini-forge-marketplace
   ```
3. **Ask for a mini:** *"make a mini of a hunched plague rat-man with a rusted cleaver"*, or
   attach a sketch or photo. The first time, mini-forge checks your computer and walks you
   through anything missing:
   - **uv**, a small tool that runs mini-forge's Python code. Claude offers to install it for you.
   - **[Bambu Studio](https://bambulab.com/en/download/studio)**, Bambu's free slicer, if you
     don't already have it.
   - **Your printer setup:** model, nozzle, plate and filament.
   - **A Meshy API key**, from your [Meshy](https://www.meshy.ai) account. You paste it into a
     settings file yourself; Claude never reads it back.

**Updates:** ask Claude to *"update the mini-forge plugin"*, then start a new session. (Claude
runs `claude plugin marketplace update mini-forge-marketplace` and
`claude plugin update mini-forge@mini-forge-marketplace`; you can run those in a terminal too.)

## What it costs

- **Claude:** a paid plan that includes Claude Code.
- **Meshy:** API access needs a Pro plan or above (check their pricing page). About **25 credits
  per mini**; about 9 more if you let Meshy make the reference picture.
- **Reference picture:** free with Gemini or ChatGPT: mini-forge writes the prompt, you paste it
  and drag the picture into the folder it opens. Optional: with the
  [Claude in Chrome](https://claude.com/chrome) extension, Claude can run Gemini for you in your
  browser and review and fix the picture itself. Or let Meshy make it (paid).
- Every paid step shows its cost and waits for your yes.

## Printers

Tested on a Bambu Lab P1S with 0.4 and 0.2 mm nozzles. Other Bambu models
should work but are untested. Other brands: the 3D model steps work, slicing does not yet.

## What happens at each step

| Step | Command | What it checks |
|---|---|---|
| Reference picture | you in Gemini/ChatGPT, Claude in your browser (optional), or `mini-forge picture` | Every hand, claw, tail and weapon touches something; feet on the base; nothing hangs down |
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
- **Supports grow from the build plate.** Allowed to stand on the figure, they got boxed in under
  a cloak and fused to it. mini-forge asks before allowing that and says where they would land.
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

## Support

mini-forge is free. If it's useful to you, you can leave a tip at
[ko-fi.com/theadventurershaven](https://ko-fi.com/theadventurershaven); it pays for filament and
Meshy credits for testing new features.

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/theadventurershaven) Videos on making minis are on
[The Adventurer's Haven](https://www.youtube.com/@TheAdventurersHaven).

## Licence

MIT. Not affiliated with or endorsed by Bambu Lab, Meshy, Google, OpenAI or Anthropic.

# From a sentence to a printed miniature

This guide follows the video. Part 1 is the manual route with free and paid tools you already
know; part 2 is the same job done by mini-forge in Claude Code. Use it on your own characters,
on things you have the rights to, or with the creator's permission.

## Part 1: by hand

### 1. Concept picture (Gemini or ChatGPT)

Describe the character in your own words: build, face, clothing, what it holds and how, pose.
Don't name an artist or a franchise. In Gemini choose the "Pro" model; start a fresh chat for
each character.

### 2. Make it printable (same chat)

A printer builds from the bottom up and cannot start a line in mid-air. Paste the "from a
description" or "from an image" prompt from
[reference-prompts.md](../plugins/mini-forge/skills/mini-forge/reference-prompts.md). It asks for
a gray sculpt on a 25 mm base with every hand, weapon and tail touching the body.

Then look at the picture the way the printer will. For anything that hangs in the air or
dangles below what it belongs to (a hand by the side, a drooping tail, a weapon tip held out),
send the follow-up edit:

> Keep everything exactly the same, but move [the left hand] inward so it lies flat against
> [the thigh]. The bottom edge of [the hand] must touch [the thigh], with no gap between it and
> the body anywhere along its lower half.

This one habit saves more prints than any slicer setting.

### 3. Meshy: picture to 3D

In the Meshy web app: **Model → Image to 3D → High Detail → Meshy 7.1**, upload the picture.

- Resolution **Ultra 4K** (same price as 2K).
- **Texture off** (you are printing gray plastic), **Pose** unset (A/T-pose would re-pose the
  figure), **Split off**, Image Enhancement left on.
- Generate (about a minute), spin the model: limb count, weapons joined, base flat, nothing
  floating. If something is wrong, fixing the picture and generating again is usually cheaper
  than repairing the mesh.
- **Download GLB.** Skip Remesh, Thicken and Repair: they cost detail. Run the free Analyze
  Printability if you like; repair only if it reports a real problem.

### 4. Bambu Studio: size and base

The GLB arrives tiny (about 2 mm) and lying on its back. If asked whether the file is in
meters, answer **No**.

1. **Stand it up:** Lay on Face (F), click the underside of the base. Or Rotate (R), 90° around X.
2. **Rough size:** Scale (S), uniform scaling locked, type the height: about 39 mm total for a
   human, 31 for a dwarf.
3. **Check feet to eyes:** the target is 32 mm for a human (25 dwarf). Measure (U) from the top
   of the base to an eye, or slice and read the eye height on the layer slider, minus the base.
4. **Correct:** new height = current height × 32 ÷ measured. Re-measure once.
5. **Base (for game use):** scale first, then Cut (C) just above the generated base, add a
   25 × 25 × 2 mm cylinder (right-click → Add part → Cylinder) and sink the feet about 0.25 mm
   into it.

### 5. Slicer settings

Start from **0.12mm Fine** (0.4 mm nozzle) and switch the settings view to **Advanced**; most of
these are hidden otherwise. Bambu's own defaults are made for brackets and boxes: supports one
layer below the model and 0.35 mm beside it, so on a mini they fuse to the surface and wrap
around hands and faces.

| Setting (Support tab) | Bambu default | Use |
|---|---|---|
| Type / Style | Tree (auto) / Default | Tree (auto) / **Slim** |
| Threshold angle | 20° | **50°** (only real overhangs get support) |
| On build plate only | off | **on** |
| Support critical regions only | off | **on** |
| Top Z distance | 0.12 mm (one layer) | **0.24 mm** (two layers) |
| Bottom Z distance | 0.12 mm | **0.24 mm** |
| Support/object XY distance | 0.35 mm | **0.8 mm** (keeps trees off hands and faces) |
| Support/object first layer gap | | **0.5 mm** |
| Tree branch diameter | 2 mm | **1.2 mm** |
| Tree support wall loops | auto | **1** |
| Raft first layer expansion | auto | **0** (separate support feet, not a ring around the base) |
| Brim (Others tab) | auto | **None** |

For 0.2 mm nozzle heroes: 0.06 mm layers, top Z distance 0.16 mm, the rest the same.

Avoid the "Strong" tree style and turning off "critical regions only": both pile on supports
that are hard to remove. Tall supports (over about 20 mm) on a slim tree can topple; use 2 mm
branches with 2 wall loops for those.

### 6. The layer preview check

Slice and drag the layer slider up slowly. Look for any spot where the figure starts a new bit
in the air with no support under it (claw tips, chin, hem corners). Paint a support enforcer
there (Support painting tool) and slice again, or go back to step 2.

### 7. Print and watch

Clean plate, watch the first layer, and look in at about a quarter and halfway. A part that
comes loose raises no error on the printer; it shows as strands spreading outward.

## Part 2: the same job in Claude Code

Install (see the [README](../README.md)), then ask: *"make a mini of a hunched plague rat-man
with a rusted cleaver"*. Claude:

1. writes the picture prompt (you paste it into Gemini), or makes the picture with Meshy if you
   prefer, and reviews it for mid-air features;
2. shows the Meshy cost and converts after your yes;
3. cleans the mesh, measures the figure and scales it by eye height onto a 25 mm base;
4. lists mid-air starts and features that hang below what they belong to;
5. slices with tested support profiles, paints supports under mid-air starts, and audits the
   supports (height, lean, how many stand on the base);
6. with LAN printing set up, sends the print after your yes and your word that the plate is
   clear, and checks the camera during the print.

What it cannot do: judge how the supports come off. Tell it afterwards; that is how the profiles
improve.

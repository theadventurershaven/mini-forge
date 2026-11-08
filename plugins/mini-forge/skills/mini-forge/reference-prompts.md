# Reference-picture prompts

The reference picture decides most of the result: Meshy builds what it sees, and the printer
prints from the bottom up. Two ways to make it:

- **Free, by hand:** the user pastes a prompt below into Gemini (choose the "Pro" model) or
  ChatGPT, with their image attached if they have one, and returns the picture.
- **Automatic, paid:** `mini-forge picture` with a short prompt (600-character limit), about
  9 Meshy credits per picture or edit.

Use a fresh chat per character. A short, plain prompt plus one follow-up edit works better than
a long chain of edits.

**Only the user's own characters, things they have rights to, or designs used with the owner's
permission.** Never put an artist's name or a franchise in the prompt.

## From a description (no image)

Put the user's description in their own words where it says [DESCRIPTION]: build, face, clothing,
equipment and how it is carried, pose.

```text
Design an original fantasy character: [DESCRIPTION].

Show it as an unpainted neutral gray tabletop miniature sculpt on a plain white background.
Three-quarter front view, whole figure and base in frame, sharp focus throughout, soft even studio
lighting, minimal shadow. Square image.

It will be 3D printed in plastic from the bottom up, so every weapon, hand, shield, tail, cloth corner
and accessory must touch the body or the base through a natural contact point. Nothing hangs out in
open air, and nothing dangles below the part it is attached to. No floating parts, no thin straps or
cords hanging free, no cape, no thin spikes. Weapons, hilts and rims sturdy enough to print.

Pose: natural, stable stance, head turned slightly toward the viewer, all load-bearing feet fully on
the base.

Scale: heroic 32 mm tabletop scale, standing on a plain smooth circular base 25 mm across and 2 mm
thick, all feet inside the rim, no ground texture. Slightly enlarged head, hands and weapons as in
modern tabletop sculpts, no cartoon exaggeration.

All detail is sculpted relief, not paint, including a face with sculpted eyes, brow, nose and mouth,
and a detailed back.

One model only. No text, no border, no colour, no extra figures or objects.
```

## From an image (the user's own photo, sketch or artwork, or one they have permission to use)

```text
Use the attached image as the character design reference only. Ignore any frame, text, icons,
logos, background and other figures.

Turn the main character into an unpainted neutral gray tabletop miniature sculpt on a plain white
background. Three-quarter front view, whole figure and base in frame, sharp focus throughout, soft
even studio lighting, minimal shadow. Square image.

Keep the character's design: build, face, hair, clothing, armour and equipment as in the reference,
each with its sculpted texture. Clean, solid hems and cloth edges, no tattered or ragged edges.

It will be 3D printed in plastic from the bottom up, so every weapon, hand, shield, tail, cloth corner
and accessory must touch the body or the base through a natural contact point. Nothing hangs out in
open air, and nothing dangles below the part it is attached to. No floating parts, no thin straps or
cords hanging free, no cape, no thin spikes. Weapons, hilts and rims sturdy enough to print.

Pose: natural, stable stance, head turned slightly toward the viewer, the same number of limbs as the
reference, all load-bearing feet fully on the base.

Scale: heroic 32 mm tabletop scale, standing on a plain smooth circular base 25 mm across and 2 mm
thick, all feet inside the rim, no ground texture. Slightly enlarged head, hands and weapons as in
modern tabletop sculpts, no cartoon exaggeration.

All detail is sculpted relief, not paint, including a face with sculpted eyes, brow, nose and mouth.

One model only. No text, no border, no colour, no extra figures or objects.
```

Adjust: a large creature gets a 40 or 50 mm base; an image with several figures gets "Render
only the [subject]" after the first paragraph.

## Short prompts for `mini-forge picture` (600 characters at most)

Description (text-to-image; leaves about 120 characters for the description):

```text
An unpainted neutral gray tabletop miniature sculpt of [DESCRIPTION], on a plain white background.
Three-quarter front view, whole figure and base in frame, sharp focus, soft even lighting, square.
Heroic 32 mm scale on a plain round 25 mm base, feet fully on it. Every hand, weapon, tail and cloth
edge touches the body or the base; nothing thin hangs in open air; no cape, no loose straps. Detail
as sculpted relief, not paint, with a sculpted face. One model only, no text, no colour.
```

Image (image-to-image, uses the job's `reference/source.*`):

```text
Use the attached image as the character design only; ignore any frame, text or icons. Render one
unpainted neutral gray tabletop miniature sculpt of the main character on a plain white background,
three-quarter front view, whole figure in focus, soft even lighting. Keep its build, clothing and
equipment. Plain round 25 mm base, feet fully on it. Every hand, weapon, tail and cloth edge touches
the body or the base; nothing thin hangs in open air. Detail as sculpted relief, not paint. No text,
no colour, no extra figures.
```

## Follow-up edit, one per feature that would start in mid-air

Printed bottom-up, the lowest point of every hanging hand, claw, cloth corner, shield rim,
scabbard tip or tail starts in open air, and a feature that hangs below the part it belongs to
grows upward as a free column before it joins the body (these break even when supported). Look
for them in the picture and fix them here; this is far cheaper than fixing the mesh or losing the
feature on the printer. By hand: same chat. Automatic: `mini-forge picture <job> --edit <picture>`.

```text
Keep everything exactly the same, but move [FEATURE] inward so it lies flat against [BODY PART].
The bottom edge of [FEATURE] must touch [BODY PART], with no gap between it and the body anywhere
along its lower half.
```

Examples that worked:
- "...move both clawed hands inward so the palms and fingers lie flat against the front of the
  robe at hip height, claws curled and gripping the cloth..." (open claws in the air are tiny
  islands the slicer may not support; a figure lost a hand this way)
- "...the shield's lower rim rests against the hip and thigh..."
- A hanging arm: "...bend the arm so the hand rests on the thigh..." (a hanging forearm broke off
  twice while fully supported).
- A drooping tail: "...raise the tail so it curves up from the body..." (a drooping tail broke
  twice; raised, it printed intact).
- A strung bow with a free string does not print; ask for it unstrung or held against the body.
- Wrong limb count: "Keep everything exactly the same, but add [N] more legs so there are exactly
  [COUNT], [N/2] on each side, matching the existing legs."

## What to check before accepting a picture

- Limb count and equipment match the subject.
- Every hand, claw and weapon touches something beside or below it; nothing hangs downward.
- Feet (or a robe, mist or rock) stand fully on the base.
- The back is shown or described; otherwise Meshy invents a plain back.
- Judge the full-size picture, not a thumbnail.

# Reference-picture prompts (ChatGPT or Gemini)

The user pastes these into ChatGPT or Gemini with their photo, card or sketch attached, and
returns the picture. Fill the brackets. Image models follow a short, plain prompt better than a
long list of rules, and a fresh chat is better than a long chain of edits.

## First picture

```text
Use the attached image as the character design reference only. Ignore any card frame, icons or text.

Render ONLY [SUBJECT] as an unpainted neutral gray tabletop miniature sculpt on a plain white
background. Three-quarter front view, whole figure and base in frame, sharp focus, soft even
lighting. Square image.

[LOOK: build, face, hair, clothing and armour with their sculpted texture]. [EQUIPMENT and how it is
carried realistically, e.g. "sword held in the right hand with the blade tip resting on the base",
"shield on the left forearm, held against the hip"]. [POSE: natural stance, feet planted, head turned
slightly to the viewer]. [For creatures: exactly N legs, all feet on the base.]

[SIZE CLASS, e.g. human-sized] on a plain smooth circular 25 mm base, 2 mm thick, all feet inside
the rim. Heroic tabletop proportions: slightly enlarged head, hands and weapons.

Design for one-piece FDM printing: nothing thin hanging in open air, no floating parts, no loose
straps or cloth strips, hands and claws touching the body or the equipment. All detail as sculpted
relief, with a detailed back as well.

One model only. No text, no border, no colour.
```

## Follow-up edit (same chat), one per feature that would start in mid-air

Printed bottom-up, the lowest point of every hanging hand, claw, cloth corner, shield rim,
scabbard tip or tail starts in open air. Look for them in the picture and fix them here; this is
far cheaper than fixing the mesh or losing the feature on the printer.

```text
Keep everything exactly the same, but move [FEATURE] inward so it lies flat against [BODY PART].
[FEATURE] must touch [BODY PART] along its lower edge, with no gap between it and the body.
```

Examples that worked:
- "...move both clawed hands inward so the palms and fingers lie flat against the front of the
  robe at hip height, claws curled and gripping the cloth..." (open claws in the air are tiny
  islands the slicer may not support; a werewolf lost a hand this way)
- "...the shield's lower rim rests against the hip and thigh..."
- For two weapons: one in hand planted on the base, the other carried with its tip on the base.
  A strung bow with a free string does not print; ask for it unstrung or held against the body.

## What to check before accepting a picture

- Limb count and equipment match the subject.
- Every hand, claw and weapon touches something below or beside it.
- Feet (or a robe, mist or rock) stand fully on the base.
- The back is shown or described; otherwise Meshy invents a plain back.
- Judge the full-size download, not a thumbnail.

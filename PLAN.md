# mini-forge: status and next steps

## Done
- Plugin layout: marketplace at the repo root, plugin in `plugins/mini-forge` (skill + `mini-forge` CLI).
- Profiles: only our overlays ship; machine/filament profiles and start G-code are built locally from Bambu Studio.
- CLI: setup, doctor, filaments, new, picture (Meshy text/image-to-image, optional), convert (cost shown,
  `--yes`, task recovery), inspect, scale, islands (+ free columns), slice (+ painted enforcers, support audit,
  island landing check), print (gated), status, camera, watch.
- 0.2.0 (2026-11-06): description-only start and universal prompts; free-column check; enforcer painting at
  mid-air starts; audit refuses tree_strong, critical-only off and >40% base-rooted supports (the last dropped 2026-11-07); `creature-0.4-stout`
  overlay; README for strangers; `docs/GUIDE.md`.
- 0.3.x-0.4.0 (2026-11-08 to 11): first real jobs through the plugin on a fresh Mac install, printed. Supports kept off the
  figure unless asked (0.48 mm gap where they land); hems and downward weapons fixed at the picture stage; `--reprint`;
  watch over one connection with an event log; camera frames opt-in; opt-in Downloads pickup; `standard-0.4-stout`;
  stale-session notice after an update.
- Tests (synthetic, no private data) and `claude plugin validate` pass.
- Ko-fi tip link (ko-fi.com/theadventurershaven) in the README and `.github/FUNDING.yml` (2026-11-07).
- Dry run on a real Meshy mesh (hooded ghost): same support columns, tallest tree and island result as the
  original pipeline's printed slice. 0.2.0 run on a printed creature: same free columns and painted faces as the
  original pipeline.

## Next
- Other Bambu models: confirm machine/process names and a real print on A1 / A1 mini / X1 / P2S / H2D.
- Non-Bambu printers: slicing through OrcaSlicer or PrusaSlicer; today the mesh steps work and the user slices by hand.
- A reliable check for thin base-rooted features (a weapon on a base corner); a root-area rule gave false alarms.

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
- Tests (synthetic, no private data) and `claude plugin validate` pass.
- Ko-fi tip link (ko-fi.com/theadventurershaven) in the README and `.github/FUNDING.yml` (2026-11-07).
- Dry run on a real Meshy mesh (hooded ghost): same support columns, tallest tree and island result as the
  original pipeline's printed slice. 0.2.0 run on a printed creature: same free columns and painted faces as the
  original pipeline.

## Next
- Fresh install tested 2026-11-06 (clean Claude config and home folder, clone of the repo): install, setup, doctor,
  islands and slice all work. A very long install path breaks on Windows' 260-character limit (a shapely DLL);
  the normal ~/.claude path is fine.
- Single-figure gates calibrated (2026-11-07). Coverage depends on the figure's turn on the plate (the Infected's
  claw: 75% at its printed angle, 0% at the angle auto-arrange picks alone), so `slice` now turns the arranged figures
  (copies aligned first) and re-slices until the audit and island check pass, keeping the best turn otherwise.
  Base-root share is reported, not refused (the rodent printed well at 72%; tree_strong stays refused). Free-column
  floor 2 -> 3 mm (claw tips of 2.3-2.5 mm printed; every break was 5.4 mm or taller). Result on printed figures:
  Infected and rodent READY on creature-0.4-stout (rodent also x3), Hungry READY on both 0.4 overlays, Warhound still
  asks about its 5.7 mm tail. Both creatures stay NOT READY on standard-0.4: their claw starts hang over the base,
  which plate-only trees cannot reach, and that is what the creature overlay is for.
- First real job through the plugin with an invented character (paid conversion + LAN print), which is also
  the video footage.
- Other Bambu models: confirm machine/process names for A1 / A1 mini / X1 / P2S.

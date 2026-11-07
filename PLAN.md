# mini-forge: status and next steps

## Done
- Plugin layout: marketplace at the repo root, plugin in `plugins/mini-forge` (skill + `mini-forge` CLI).
- Profiles: only our overlays ship; machine/filament profiles and start G-code are built locally from Bambu Studio.
- CLI: setup, doctor, filaments, new, picture (Meshy text/image-to-image, optional), convert (cost shown,
  `--yes`, task recovery), inspect, scale, islands (+ free columns), slice (+ painted enforcers, support audit,
  island landing check), print (gated), status, camera, watch.
- 0.2.0 (2026-11-06): description-only start and universal prompts; free-column check; enforcer painting at
  mid-air starts; audit refuses tree_strong, critical-only off and >40% base-rooted supports; `creature-0.4-stout`
  overlay; README for strangers; `docs/GUIDE.md`.
- Tests (synthetic, no private data) and `claude plugin validate` pass.
- Dry run on a real Meshy mesh (hooded ghost): same support columns, tallest tree and island result as the
  original pipeline's printed slice. 0.2.0 run on a printed creature: same free columns and painted faces as the
  original pipeline.

## Next
- Fresh install tested 2026-11-06 (clean Claude config and home folder, clone of the repo): install, setup, doctor,
  islands and slice all work. A very long install path breaks on Windows' 260-character limit (a shapely DLL);
  the normal ~/.claude path is fine.
- **Gate calibration for single figures (blocker for strangers).** Both creatures from the 2026-10-31 plate printed
  well, yet alone on the default overlay each is NOT READY (an uncovered claw/paw start next to the base), and on
  creature-0.4-stout the small rodent fails the 40% base-root rule (69%; the rule was set on multi-figure plates).
  Recheck the landing check near the base top and the base-root share for small single figures before release.
- First real job through the plugin with an invented character (paid conversion + LAN print), which is also
  the video footage.
- Tip link (Ko-fi) in the README and `.github/FUNDING.yml` once the account exists.
- The landing check varies with plate position (a claw start flagged on one slice was covered on the printed
  one); consider a larger enforcer radius or a second arrangement before calling a start uncovered.
- Other Bambu models: confirm machine/process names for A1 / A1 mini / X1 / P2S.

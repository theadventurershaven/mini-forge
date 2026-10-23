# mini-forge: status and next steps

## Done
- Plugin layout: marketplace at the repo root, plugin in `plugins/mini-forge` (skill + `mini-forge` CLI).
- Profiles: only our overlays ship; machine/filament profiles and start G-code are built locally from Bambu Studio.
- CLI: setup, doctor, filaments, new, convert (cost shown, `--yes`, task recovery), inspect, scale, islands,
  slice (+ support audit + island landing check), print (gated), status, camera, watch.
- Tests (synthetic, no private data) and `claude plugin validate` pass.
- Dry run on a real Meshy mesh (hooded ghost): same support columns, tallest tree and island result as the
  original pipeline's printed slice.

## Next
- Fresh-machine install test through `/plugin install` (uv creates the venv inside the plugin cache).
- First real job through the plugin, including a paid conversion and a LAN print.
- Guide / video script (`docs/GUIDE.md`): setup, one mini end to end, the lessons, limits.
- Other Bambu models: confirm machine/process names for A1 / A1 mini / X1 / P2S.

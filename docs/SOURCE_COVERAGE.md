# Source coverage and local archive

All 64 original notes remain unchanged in `temp/legacy/documentation/`; 62 migration hashes were rechecked against the prior manifest, and MASTER/FREEZE were preserved separately. This table is provenance/ownership, not 64 competing instructions. Full source hashes are in `source_coverage.json`.

The full old workspace, knowledge/findings and outputs remain in `temp/legacy/recomp/`. Old root output/audio/misc files are in neighboring legacy folders. Private tests are in `temp/legacy/vendor_test_source/`; historical vendor docs/helper are in `temp/legacy/vendor_reference/`. No original history is inherited.

Important evidence caveats: native_havokcap3.* was overwritten by cap4, so resourcesystem 938 survives in its atomic note only. Older interpfix stdout/CSV were overwritten; snapshots survive. Repeated m33 underscore/hyphen handoffs and mislabeled HANDOFF_save_data are historical summaries, not independent save proofs. A successful 11214-byte AUTOSAVE.DAT read does not establish round-trip integrity.

| Original note (private) | Canonical owner |
|---|---|
| atomic-2026-10-08-coh-overflow.md | [RUNTIME](research/RUNTIME.md) |
| atomic-2026-10-08-interp-contracts.md | [RUNTIME](research/RUNTIME.md) |
| atomic-2026-10-08-mfc-overflow.md | [RUNTIME](research/RUNTIME.md) |
| atomic-2026-10-08-policy-snapshot.md | [SPURS](research/SPURS.md) |
| atomic-2026-10-08-ppu-wait.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-08-wait-target.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-09-compiler-provenance.md | [TRANSLATION](research/TRANSLATION.md) |
| atomic-2026-10-09-interrupt-boundaries.md | [RUNTIME](research/RUNTIME.md) |
| atomic-2026-10-09-notification-serialization.md | [RUNTIME](research/RUNTIME.md) |
| atomic-2026-10-09-online-analysis-tools.md | [TRANSLATION](research/TRANSLATION.md) |
| atomic-2026-10-09-owner-read-gate.md | [SPURS](research/SPURS.md) |
| atomic-2026-10-09-pm-cpu-span.md | [SPURS](research/SPURS.md) |
| atomic-2026-10-09-pm-ownership-stores.md | [SPURS](research/SPURS.md) |
| atomic-2026-10-09-pm-page-mask.md | [SPURS](research/SPURS.md) |
| atomic-2026-10-09-pm-reserve-predicate.md | [SPURS](research/SPURS.md) |
| atomic-2026-10-10-debug-pack01-quarantine.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-debug-package-toc.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-fp-failures.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| atomic-2026-10-10-havok-capture.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-havok-race-load.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-havok-raw-fatal.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-havok-reference-hardware.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-havok-retail-parity.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-native-wedge-launcher-hygiene.md | [OPERATIONS](OPERATIONS.md) |
| atomic-2026-10-10-play-stall-snapshot.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-rpcs3-compiler-cache.md | [TRANSLATION](research/TRANSLATION.md) |
| atomic-2026-10-10-rpcs3-matched-reference.md | [HAVOK_REFERENCE](research/HAVOK_REFERENCE.md) |
| atomic-2026-10-10-upstream-recon.md | [VENDOR](VENDOR.md) |
| atomic-2026-10-10-upstream-reuse.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| FREEZE_STATUS.md | [PARKED_MSTREAM](research/PARKED_MSTREAM.md) |
| HANDOFF_audio.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| HANDOFF_BootAdvance.md | [OPERATIONS](OPERATIONS.md) |
| HANDOFF_EVENT_WAKE.md | [OPERATIONS](OPERATIONS.md) |
| HANDOFF_liftboot.md | [BUILDING](BUILDING.md) |
| HANDOFF_menu_nav.md | [OPERATIONS](OPERATIONS.md) |
| HANDOFF_pad_input.md | [OPERATIONS](OPERATIONS.md) |
| HANDOFF_ppu_consumer.md | [SPURS](research/SPURS.md) |
| HANDOFF_prompt_2026-10-10_evening.md | [BUILDING](BUILDING.md) |
| HANDOFF_RecompBootstrap.md | [BUILDING](BUILDING.md) |
| HANDOFF_rsx_readiness.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| HANDOFF_save_data.md | [BUILDING](BUILDING.md) |
| HANDOFF_SPURS_COMPOSITE.md | [SPURS](research/SPURS.md) |
| HANDOFF_yourlane.md | [BUILDING](BUILDING.md) |
| m1_park_fence.md | [PARKED_MSTREAM](research/PARKED_MSTREAM.md) |
| m33-ppu-consumer.md | [SPURS](research/SPURS.md) |
| m33-rsx-readiness.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| m33_asset_pipeline.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| m33_ppu_consumer.md | [SPURS](research/SPURS.md) |
| m33_rsx_readiness.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| m37-ppu-kick-answers.md | [SPURS](research/SPURS.md) |
| m39-spin-exit-decode.md | [SPURS](research/SPURS.md) |
| m39b-ppu-park-decode.md | [SPURS](research/SPURS.md) |
| m40-caller-loop-verdict.md | [SPURS](research/SPURS.md) |
| m46_boot_progress.md | [BUILDING](BUILDING.md) |
| m4_audio.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| m4_textures.md | [GRAPHICS_AUDIO](research/GRAPHICS_AUDIO.md) |
| m4_title_tracer.md | [OPERATIONS](OPERATIONS.md) |
| MASTER_HANDOFF.md | [PARKED_MSTREAM](research/PARKED_MSTREAM.md) |
| NAMED_BUILD_FEASIBILITY.md | [TRANSLATION](research/TRANSLATION.md) |
| NATIVE_PORT_BOUNDARY.md | [BUILDING](BUILDING.md) |
| next-20-steps-2026-10-10.md | [NEXT_STEPS](NEXT_STEPS.md) |
| probeoff-2026-10-08.md | [OPERATIONS](OPERATIONS.md) |
| sol-handoff-2026-10-07.md | [RUNTIME](research/RUNTIME.md) |
| wws-stall-dossier-2026-10-07.md | [SPURS](research/SPURS.md) |

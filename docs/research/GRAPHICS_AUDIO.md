# Graphics, video and audio seams

## Rendering evidence

Upstream André Brum correction `030931aa1cedac80e19089793307a1b4701460c5`: RSX transform-constant window 32 dwords (eight vec4), not 64. Neighbor methods previously corrupted unrelated constants. Red 8 checks/4 fail → green 8/0. Font-only menus existed before; no attributable visual/race claim.

Three actual 1888-byte/90-instruction fragment programs needed 38079 HLSL bytes. Caller 32768 failed all; 65536/131072 passed unchanged decoder/input; FXC ps_5_0/main/O3 all 0. Scratch now 262144, matching VP. No ISA change/suppressed error. [Vendor](../VENDOR.md) owns draft PR 230, synthetic upstream proof and credit.

Other preserved renderer seams:
- Negative-w full position negation preserves NDC; RSX sign-agnostic |z|≤|w| versus D3D 0≤z≤w required RSX-visible per-vertex boundary mapping, 272 numeric checks and real menu VP compile.
- Reused tri/strip/fan draw records needed is_clear reset; stale clear classification hid genuine video strip draw.
- Guest recycles fragment ucode addresses per pass. Snapshot at bind, derive PSO/hash/inline constants from that snapshot; later live read selects wrong program. Twelve-frame bloom/luminance propagation proves pipeline activity, **not accepted real video**.

Menu 69-op capture: clear/copy no-video placeholder 320×180, composite 1536×1280, alpha GUI overlays/text, bloom → 2×1, display blit, UI atlas. Bound texture with no TEX did not identify video: alpha GUIc_PS is a color overlay. Real Video_PS is 7 instructions/TEX-first, structural hash 7c6a7b111d42d11dff8b27819550f1fe2cd5744f6d5066566fcf5591e71e0b4d, matched reference 7083A85F804748DB.fp. No original shader bytes are distributed here.

Named path: VideoPlayer::Render 2644D0 → FwMemcpy C7C724 upload 384000 bytes → QuadRenderable videoTexture → TRIANGLE_STRIP/DrawArrays C8D230. Caller MotorStormRender::viewRenderPreGUI 275548, gate 275668..275694. These are debug target identifiers, not guaranteed retail mappings. Diagnose actual resource/frame selection/read/decode/upload/render boundary before touching overlay shaders.

## Audio staging

Game audio uses embedded Multistream/SPURS workloads, not imported cellAdec/cellAtrac. cellAudio→WASAPI wiring and real-time ring drain do not prove correct decoded audio. Firmware flashATRAC/flashMP3 are private inputs; staging fingerprints must use actual PT_LOAD bytes. Image-relative registration alone does not correct absolute/PC-relative addresses at a different staging base.

Per-observed-base link lifts restore fixed-low-LS relative externs, register/deduplicate by (fingerprint, lift_base), require resident span and caller link on every context. flashATRAC self-modifies text for a function-pointer table; hit_once skips rehash only after valid initial claim, rearmed on restage. Ninety-function parity sweep and in-game silence 79.7–81.9% matching interpreter baseline establish limited parity, not correct sound.

Captured compressor/reverb lifts reconstructed at guessed 2F3A0 instead of actual 2EF80/2FD00 caused an audio-lane failure; interpolation fallback was diagnostic working mode, not final native acceptance. A stopped-log inference for StreamCodecMP3 was corrupted by global print caps; blocked wait and empty-queue park are different. Old retail avStream exclusions stay scoped to their own version/window. Native tests remain muted: verify samples/channels/continuity/underruns before mute, leave audible quality unclaimed.

Presentation, video/model/art restoration and excessive PLAY delay remain evidence-led tasks in [next steps](../NEXT_STEPS.md); prior numeric/source successes cannot close them.

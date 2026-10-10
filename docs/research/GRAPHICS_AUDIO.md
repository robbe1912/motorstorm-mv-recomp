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

## Native video playback seams (issues 20 and 21)

Named debug target. The title plays MPEG-2 elementary streams through its own VideoStream threads over cellVdec HLE directly. cellSail, cellDmux, cellPamf, cellVpost and cellVideoUpload imports recorded zero log hits in observed runs; cellVpost Exec is a documented no-op stub in the toolkit, but this title does not reach it.

Lifted flow: MotorStormRender::viewRenderPreGUI 0x275548 walks the global player list and calls VideoPlayer::Render 0x2644D0 per player. VideoStream::my_input_thread 0x2667BC reads the file through a process-global VideoFile reader (VideoFile::readThreadProc), scans MPEG-2 start codes into ping-pong access-unit buffers, and submits cellVdecDecodeAu. VideoStream::my_post_thread 0x266320 paces cellVdecGetPicItem and cellVdecGetPicture (RGBA32_ILV) into a frame ring. Two module flag bytes gate Render: TOC-0x348C (set on input-thread exit, stream end or error) and TOC-0x3488 (error only). The TOC-0x348C path tears down the VideoFile state inside Render.

Intro video (issue 20, intro1.m2v, 1280x720 at 30000/1001): the instrumented baseline run shows the stream advanced (49 logged reads, at least 1.6 MiB of 179 MiB) and both VideoStream threads exited cleanly on skip, but the screen stayed black for the whole intro. The seam is decode-or-later. No proof yet that pictures leave the decoder (PICOUT callback delivery, GetPicture output) or that Render uploads real frames instead of the 320x180 no-video placeholder. Condition-variable waits are not covered by the wait probe, so a pacing or picture-wait deadlock is not excluded by absent log lines.

Menu background video (issue 21, gui_d.m2v): the second player opens the file but performs zero reads. Its input thread blocks forever on the done-semaphore while the singleton reader left over from the intro player stays parked on the request-semaphore. The reader thread is never joined and the semaphores are never destroyed; the lazy infrastructure-creation path in my_input_thread only triggers when the semaphore id is invalid, so stale global state from the previous player deadlocks the next player before its first read. Any fix must restore firmware-consistent cross-player state, not bypass the wait.

Next evidence step: a traced run with VDEC_TRACE, FS_READ_ALL and SEMTID plus RSX capture. Proof targets are PICOUT callback delivery, GetPicture destination content and per-frame upload provenance; draw counters or presents per second do not close these issues.

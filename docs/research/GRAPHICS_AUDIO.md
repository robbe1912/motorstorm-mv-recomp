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

Named debug target. The title plays MPEG-2 elementary streams through its own VideoStream threads over cellVdec HLE directly. Observed logs contained no cellSail, cellDmux, cellPamf, cellVpost or cellVideoUpload entries. This bounds those logs; it does not establish that the title never calls those imports.

Lifted flow: MotorStormRender::viewRenderPreGUI 0x275548 walks the global player list and calls VideoPlayer::Render 0x2644D0 per player. VideoStream::my_input_thread 0x2667BC reads the file through a process-global VideoFile reader (VideoFile::readThreadProc), scans MPEG-2 start codes into ping-pong access-unit buffers, and submits cellVdecDecodeAu. VideoStream::my_post_thread 0x266320 paces cellVdecGetPicItem and cellVdecGetPicture (RGBA32_ILV) into a frame ring. Two module flag bytes gate Render: TOC-0x348C (set on input-thread exit, stream end or error) and TOC-0x3488 (error only). The TOC-0x348C path tears down the VideoFile state inside Render.

Intro video (issue 20, intro1.m2v, 1280x720 at 30000/1001): the instrumented baseline run shows the stream advanced (49 logged reads, at least 1.6 MiB of 179 MiB) and both VideoStream threads exited cleanly on skip, but the screen stayed black for the whole intro. File reads do not establish access-unit submission. The first missing boundary may be submission, decode, callback, picture retrieval or rendering. No proof yet that pictures leave the decoder (PICOUT callback delivery, GetPicture output) or that Render uploads real frames instead of the 320x180 no-video placeholder. Condition-variable waits are not covered by the wait probe, so a pacing or picture-wait deadlock is not excluded by absent log lines.

Menu background video (issue 21, gui_d.m2v): the baseline records the second player opening the file but has no attributed reads afterward. The FS logger retains capped per-fd counters across close/reopen, so absence of lines cannot prove zero reads. A stale process-global reader/request/done-semaphore lifecycle is a hypothesis from the lifted source, not a demonstrated live deadlock. Confirm actual thread PCs, semaphore ownership and paired wait/return chronology before changing lifecycle semantics. Any fix must restore firmware-consistent cross-player state, not bypass the wait.

The later 20261011T003811.531817Z attempt (EXE `627f27bd`, 420.516 s, bounded termination) did not record VDEC_TRACE, FS_READ_ALL, SEMTID or SEM_WAITDBG in its launch environment and cannot confirm the proposed semaphore cause.

Next evidence step: `--trace-video` with VDEC_TRACE, FS_READ_ALL, SEMTID and SEM_WAITDBG plus owned RSX capture. Proof targets are PICOUT callback delivery, GetPicture destination content and per-frame upload provenance; draw counters or presents per second do not close these issues.

## Combined-run positive evidence (2026-10-11)

The [combined review run](../OPERATIONS.md#combined-review-validation-2026-10-11)
adds positive evidence to the hypotheses above. Descriptor-lifetime-aware
load tracing attributes 41,943,040 completed read bytes to `gui_d.m2v`.
The decoder trace logs 63 successful GetPicture conversions across two
sequences (the print is after conversion, immediately before CELL_OK).
It also logs 31 PICOUT notification attempts; that print precedes callback
dispatch, so it does not prove callback return. Decoder trace counters are
capped/sparse; these are logged events, not uncapped operation totals or
per-video attribution. Successful pictures do not prove their pixels were
uploaded or rendered. The observed menu background is still black. A zero
menu-read conclusion is contradicted for this run; an earlier or later
lifecycle defect remains possible. [Issue #46](https://github.com/robbe1912/motorstorm-mv-recomp/issues/46)
owns the bounded sequence/picture/upload/draw provenance experiment.

The texture observer wrote 32 raw/metadata pairs totaling 8,659,456 bytes
and explicitly exhausted its attempt budget. Later selection uploads are
unobserved; [issue #45](https://github.com/robbe1912/motorstorm-mv-recomp/issues/45)
owns arming for that window, including the upload-cache-miss coverage limit.
The bike observer recorded rsfind 64 (quota reached), dynsel 2, vpfn 2,
vvinv 1, ral 1 and vtload 1 after arming. These entry snapshots do not prove
geometry/material completion. Screenshots still show malformed race
selection and missing bike art/model. Issues #20 through #24 remain open.

## Launch-US ticket asset correlation (2026-10-11, issue 22)

The launch-US `cache_ps3.txt` indexes 446 RPKs: 333 vehicles, 104 characters
and 9 worlds. Menu resources are separately indexed under `guiscenes` as
RIB/EVO records; the loose `gui` directory contains videos. Native runs use
the original packed disc. Selective offline extraction identifies original
resources for comparison; it does not supply replacements to the runtime.
There is no evidence that loose menu RPK extraction is required for the
verified ticket texture below.

### Active scene and correction of the initial bundle assumption

The actual requested scene is `festival_scene.rib`, root
`000FD77BC5804123`, with artwork in `festival_meshes.rib` (235 resources).
The scene has 82 dependency references into that meshes bundle and none into
`festival_ticket_meshes.rib`. The similarly named `festival_ticket_scene.rib`
(root `000F60A177731E8A`) and its 393-resource meshes bundle are separate
resources. Their first-tier IDs `0005E28A0ABE2C26`, `00056C421655E9B0` and
`00050528923763DA` were the initial observer targets; they do not identify
this visible screen's active ticket artwork.

Read-only scans found all 38 pixel IDs and all 357 distinct nonpixel IDs from
those separate festival-ticket bundles, qualified by exact ID, type, indexed
size and dependency count. Most resource pointers were zero; shared resources
had nonzero pointers. These are valid observations of that separate bundle,
but they do not establish failed publication for the active scene. Likewise,
its textures' absence from later committed RSX memory or 39 selected source
spans does not explain the visible defect. A guessed contiguous 393-row span
failed its ID comparison and was rejected.

The version 3 parser validates EVOSBIG, version 30000, the 11111111 header,
resource/type/dependency totals, names and sizes, and the exact 99999999/EOF
boundary. All 59 extracted scene/bundle RIBs and the active festival meshes
RIB passed. The [Nenkai template](https://github.com/Nenkai/010GameTemplates/blob/fadbd2d123011dc8edbea12097aa2bc378dd3b72/Evolution%20Studios/RPK_ResourcePack.bt)
targets later versions and serves only as a type-name reference. Original
bytes and parser outputs remain in ignored `temp/issue22-assets`.

### Native observations

Three muted runs used matching launch-US disc data and debug ELF SHA256
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
The user navigated each to SELECT A RACE. No agent input, focus changes or
desktop captures were used; a run-local marker armed existing internal RSX
frame capture.

| Run | Native EXE SHA256 | Saved frame |
|---|---|---:|
| 20261011T212653.400190Z | bd6e08305f68ac162338427b3c2c30d5786cd7f756ee8212ebe82c69eabdbf0b | 13924 |
| 20261011T214142.477860Z | e73b19a10a0339e454c37078300f2e478e68de4312683972e3bc555fdaf4d44a | 1520 |
| 20261011T215220.284090Z | a21bba4ce80f74749259daa4ddf72113a7febf3ef6edfb110cc6e92db5a7ed4e | 8757 |

The saved 1280x720 SELECT A RACE backbuffers reproduce text, broad diagonal
bands and no recognizable tickets. Each manifest records 349 operations.
The observed 1536x1280 target at 00D00000 is almost entirely black. Operations,
submitted frames and window readiness do not prove successful rendering or
minimum 60 FPS.

The third run's bounded request observers recorded 366 events: 178
RequestInternal entries (812280), 178 request-constructor entries (833288)
and 10 LoadInternal entries (81CC74). No unreadable ID or 4096-event quota
was reported. Actual festival root FD77BC5804123 was requested twice;
carselect root F9D61093BF3BD was requested once, with caller PC 499578.
The separate festival-ticket root F60A177731E8A was unrequested. Entry events
prove requests, not completion. Filtering covered the initial bundle IDs and
root scene/collection/RIB types; active pixel IDs were identified later, so
absence from this request trace cannot judge their loading.

### Verified active texture reaches native RSX memory

| Active resource | ID | EVO size | Payload format and dimensions |
|---|---|---:|---|
| T1_in_at_the_deep_end_DXT1.dds | 0005A486D144C3CC | 1048619 | PixelFormat 10 / DXT3, 1024x1024 |
| T1_in_at_the_deep_end_n_v2.dds | 0005E8D66BAFCF8C | 524331 | PixelFormat 9 / DXT1, 1024x1024 |

The diffuse filename's DXT1 label is not its serialized format. Its EVO
header specifies PixelFormat 10, and its 1048576-byte payload begins at
file offset 43. That entire payload equals native guest source C4AEAC80 in
independent later reads from both the first and third runs, SHA256
`945daa01b6e5abed7f459fd4c5cfaea00805469baf491d25b2242c7d25227660`.
The first run's C4BEAC80 source also equals the complete 524288-byte normal
payload, SHA256
`35093e1dda632ba530206c538ab8b68d70a96987f8221948f7cc011d33bae297`.

Third-run frame 8757 op022/op023 bind C4AEAC80 as 1024x1024 RSX format 87
(DXT3), matching that diffuse EVO header. They draw 762 vertices into
00D00000 with fragment program 04C6AC81 and vertex-program cache slot 17.
This supplies a concrete active-ticket texture/source/draw correlation.
Later source reads are non-atomic and bound state is not proof of sampling,
GPU view contents, decoded pixels or successful rasterization. It rules out
an archive extraction/upload-byte failure for this identified source; it does
not exonerate every asset or the remaining rendering stages.

### Next distinguishing observation and probe limits

Issue [22](https://github.com/robbe1912/motorstorm-mv-recomp/issues/22) remains
open. Rank the next hypotheses for the verified Deep End draw:

1. Vertex/index fetch or transformation produces invalid geometry. Capture
   raw indices, vertex descriptors and inputs for op022/op023 and correlate
   them with the mesh resource and exact bound vertex program.
2. Fragment-program inputs/constants or texture sampling differ from the
   intended draw. Capture bind-time shader bytes, constants and sampled units
   for 04C6AC81, then verify the view's decode/remap against the EVO header.
3. Correct draw output is lost through target/depth/cull/composition state.
   Follow that draw's output through 00D00000 to the final backbuffer.

FP_PICK=03A71FC1 captured constants and six positions for other draws;
one extreme position is a lead, not proof about the verified Deep End draw.
Early compiled shader files are not bind-time identity because program
addresses can be recycled. Both constructor observers produced no RIB
snapshots; executed entry/return coverage remains unproved. Construction-time
Find nulls and capped upload observers' silence are not load-failure verdicts.

First-run closure used the 600s guard. The second and third runs used owned
stop markers; guard return code 1 is not a gameplay verdict. The first two
wrappers restored ordinary generated selection and rebuilt successfully.
A third wrapper scope NameError stopped before process creation; the corrected
launcher ran the SHA-validated private diagnostic EXE independently of the
restored ordinary build. All 62 ordinary generated source hashes remain
unchanged. Probes, generated copies, extracted payloads, dumps and captures
stay ignored. No rendering fix or acceptance claim resulted from this unit.

Earlier C325D600 bytes labeled a ticket strip match Sony/presents intro text;
archived frame 005729 shows SELECT A BIKE. Neither proves race ticket art.
Main-menu background video is a separate unresolved observation; these ticket
captures do not verify it. Menu correctness, normal PLAY race entry and
measured minimum 60 FPS remain unproved.
## Agent-run menu reproduction and indexed-draw seam (issue 22)

The October 12 correction replaces repeated human navigation with normal,
screen-gated PAD_FILE input; it does not force a scene or treat arrival as
graphics success. In the muted pilot, four acknowledged CROSS presses selected
English, skipped an observed blank intro, chose PLAY and dismissed the festival
help overlay. Only game-internal saved backbuffers were read. A private profile
records the original ELF identity, observed screen ROIs and a target requiring
both the SELECT A RACE heading and ticket points text.

The automatic rerun `20261012T150006.048370Z` used EXE SHA256
`7f41a45cd53ea03bc8f93b8755d28966d562b6390a8b7452bc1a8716018698d9`
and the same debug-US ELF as the preceding ticket correlation. It reached that
target in internal frame 11 with four acknowledged inputs, no user navigation
and no desktop capture/control. The owned launcher closed at 56.672 seconds
after the target observation and a five-second draw-observation window. Closure
is intentional, not game completion. The menu still had malformed broad bands.
The ordinary backend/source selection had already been restored and rebuilt;
the run used an isolated copy of the diagnostic executable.

A bounded read-only observer was authored first on our ps3recomp fork and
temporarily integrated into a copied diagnostic binary. It captured the
verified DeepEnd draw at frame 1323/op 22: triangle strip, first index 1336,
256 input indices, 762 emitted vertices, RT `00D00000`, viewport 720x1280,
FP `04C6AC81`, VS cache hash `C23D78F6`. Its textures still included the
previously verified DeepEnd diffuse/normal sources `C4AEAC80`/`C4BEAC80`.
Private artifacts retain raw big-endian indices, interpreted indices,
converted vertex slots, constant banks, bound FP bytes and compiled VS DXBC.
Raw attribute-span requests exceeding the one-MiB guard were explicitly
refused; those absent spans are not complete raw-vertex proof.

There are 25 `0xFFFF` entries in those 256 indices. The ordinary command log
records unknown method `0x1DB0 = 0x0000FFFF` followed by unknown method
`0x1DAC = 0x00000001`: the configured primitive-restart index and its enable.
The legacy D3D12 command state does not handle these methods, and its indexed
strip expansion treats every index as a vertex reference. This identifies a
concrete restart-dispatch/assembly seam, distinct from the restart-aware
generic live-draw/dispatch paths. It does not yet prove a repaired menu: the
next change needs a game-free regression, hardware-faithful restart state and
strip assembly, followed by the same agent-run native loop.
### Restart correction: native boundary passes, graphics still fail

Fork commit `7db6730` implements the missing restart methods and incremental
strip/fan assembly, including width rules and winding. The actual upload
function's game-free regression is red on the old code (15 references and
three sentinel fetches) and green on the candidate (six references, no
sentinel fetch), with additional packet-continuation/disabled/fan/width cases.
These authored fixtures are not captured game indices.

Muted automatic run `20261012T152117.580104Z`, EXE SHA256
`a838c95b0eee273adc2081a40c47085c2994d3dfb4ba20274994073475cfc207`,
reused the same debug-US ELF and four-step normal-input profile, without draw
observer knobs or user navigation. Internal frame 11 still shows malformed
bands and no recognizable tickets. At the verified DeepEnd op 22, the emitted
count changes from 762 to **537**, exactly the strip-cut reference count
computed from the preceding capture's 25 sentinels. The formerly unknown
restart-method messages are absent because the methods now update real state,
not because errors were suppressed. This proves a repaired dispatch/assembly
boundary, not normal menu graphics. The owned launcher closed intentionally
after 56.797 seconds. Video, race entry and FPS acceptance remain unverified;
the remaining geometry/shader/target-composition seam needs distinct evidence.

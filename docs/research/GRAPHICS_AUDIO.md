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

## Current vehicle-preview observation (2026-10-13, issue 24)

The user reports oversized malformed blue triangles and heavy z-fighting in
the vehicle preview, with the platform base appearing normal. This is a
vehicle-specific discriminator, not proof of faulty materials or pointers.
Internal frame 71 of muted run `20261013T171346.818831Z` independently shows
SELECT A BIKE / MOHAWK INDIANA and oversized blue geometry. It cannot establish
temporal z-fighting from a single image. The run uses named-US debug ELF
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`
and the corresponding launch-US disc; its EXE identity and diagnostic limits
are recorded in [SPURS evidence](SPURS.md). The platform observation remains
user-reported. Original bike acceptance in issue 24 remains unmet.

Next distinguish raw index/attribute fetch from vertex-program transforms,
then material/depth state, retaining both vehicle and platform draws at the
same ordinary selection checkpoint. Prior ticket source equality, exposure
coherence and AA layout gains do not exonerate this vehicle's geometry path.

### Indexed input comparison at the observed bike screen

Muted named-US run `20261013T175851.392347Z`, EXE SHA256
`0533a502da57f4f6dcf0bccb3e795a54d4fb4b72da3f92152099d7ef17306fde`,
reached the selected MOHAWK view through acknowledged normal menu inputs.
The private draw observer armed after that screen was observed; no race
confirmation was sent. Fourteen indexed callbacks targeting `0x00D00000`
retained raw guest indices/attribute spans, actual host vertices, active VP
state and constants, bound FP snapshot, and compiled VS. The run ended by
its explicit stop marker after 58.547 s, return 1; this was a diagnostic stop.

An independent offline reconstruction follows the retained BE indices,
configured restart sentinel and strip winding. Every reconstructed count
matches its captured host vertex count. All 53,904 compared components of
float32/half positions, UB colors and half UVs have zero mismatches. CMP
attributes were
excluded from this initial comparison, and this does not validate every
vertex-fetch format, shader transform, material, depth state or draw.
Several float3/stride32 draws using attribute0 offset `0x05998000` already
contain coordinates around plus/minus 10000 before vertex shading. A separate
half/stride26 draw has unit-sized positions. Neither is yet bound to the
selected bike or platform resource; the user's platform observation remains
a useful discriminator, rather than an established draw identity.

Read-only copies from the configured launch-US archive have hashes differing
from the earlier bike-resource inventory: `vehicles/bike.rpk`,69855 bytes,
SHA256 `16edaa61982ad78b79c0b21a0d395edc025b20ed9346660e03dda9280d6c4375`;
`vehicles/bike01.rpk`,3499060 bytes,
SHA256 `c9fe832bc34c084a818ddd060de50a35f504ea3e41456449208a8a7dc10e443c`.
Do not equate these targets or infer corruption from an unmatched byte sample.
The next seam is resource identity and any guest conversion before upload.

A second resource-binding run `20261013T180447.409407Z`, with the same EXE,
consumed English selection but timed out waiting for the next observed menu
step. It did not arm bike or draw observation; no vehicle conclusion follows.
An attempted observed-movie skip was refused because the internal frame was
stale. The run reached its 181.125 s guard, return 1. No input retry or scene
shortcut was used. Temporary backend hooks were restored byte-for-byte in
both native and fork trees; the supported optimized baseline rebuilt as EXE
SHA256 `992697a15fd9523898ff84c64152f9329912e7f3942f05ac67e132972cea54b9`.
Original vehicle appearance and normal-PLAY racing remain unaccepted.

### Resource-request observer correction (issue 24)

The original named-US `ResourceSystem::Find` routine at `00820B8C` preserves
r5 as its identifier pointer, compares the eight-byte value through that pointer
with resource-tree keys, and writes the result handle through r4. The previous
entry observer mislabeled the r4 output buffer as an identifier. Its 96-byte
snapshots cannot establish request identity or lookup completion. Incoming r0
values alone are not a substitute for argument proof.

The authored observer now reads exactly eight bytes through r5. The existing
synthetic observer check supplies distinct r4/r5 buffers: the old header fails
this assertion, the corrected header passes, and the guest-memory/context,
probe-off silence, arm gating and quota checks still pass. Original/generated
inputs remain unchanged; this corrects diagnostics, not rendering.

Supported optimized build `20261013T182131.195519Z` produced EXE SHA256
`e51e97d310cdbb17cfb8714ca3ff9a359d8f64f9b2f2414471b1b85bf9d26cc0`.
Muted owned run `20261013T182637.264949Z` used the same named-US ELF and launch-US
disc as the preceding draw capture. Screen-gated inputs followed normal PLAY
to the class screen, armed entry observation before class confirmation, then
observed MOHAWK at internal frame 59. No race-confirmation input was sent.
Entry requests name `bike01` and `bike01_LV02`; those names are now observed
at this checkpoint, but they do not bind the earlier GPU draws to a resource.

All 64 retained `rsfind` records contain readable eight-byte identifiers. Among
these are two vertex-buffer requests, `0003800BF78C6600` and
`00033C08B34987C5`, and index-buffer request `000471421626BC98`. The explicit
64-event stage quota was reached before the later vehicle-load entries; absence
of other requests after that cap has no diagnostic meaning. Requests are entry
observations, not successful results or draw-consumption proof. After 35 more
seconds of observation, frame 70 still has the blue malformed preview. The
run ended on its explicit stop marker at 86.735 seconds, return 1; vehicle
rendering and normal-PLAY racing remain unaccepted.

A separate baseline run `20261013T181712.409242Z` observed the same package
names, but used the old r4 observer and stopped at the first selected-name
screen (54.625 seconds, return 1). That screen showed a loading emblem; target
recognition alone did not establish model-load completion. A later read-only
VRAM snapshot attempt against the corrected run found its PID already terminal
and captured no memory. No replacement run was launched on that failure.

The launch-US `vehicles/bike01_LV02.rpk` copy is 3299524 bytes, SHA256
`48639f882b6e0e5cdd8341bcaf7da81156f63e88c1b58918af4a59b55021e000`.
Its primary StreamFormat version `0x10000` specifies HALF3 positions, not
float32 positions, followed by another HALF3 field at TEXCOORD usage 7.
The primary buffer has stride 32 and 30143 vertices. Source positions decoded
according to that format are unit-sized; treating its first 12 bytes as float3
was not a valid source interpretation. The retained GPU draw uses float3 with
stride 32, so source identity and any guest conversion must be established
before comparing those position representations. No complete retained index
or position span directly matched this package; that does not prove corruption.

### Resident geometry and environment binding (issue 24)

The muted named-US baseline run `20261013T183511.323216Z` used EXE
`e51e97d310cdbb17cfb8714ca3ff9a359d8f64f9b2f2414471b1b85bf9d26cc0`.
The controller followed the observed class/model route, armed the entry
observer before class confirmation, then retained 35 seconds after the
MOHAWK name target. It sent no race-confirmation input. The owned process
was verified before and after a read-only memory snapshot, then stopped
explicitly: 88.766 seconds, guard termination, return 1. No menu or race
acceptance follows from that run.

Guest-base discovery checked original ELF bytes and process identity.
Sequential reads took approximately 0.8 seconds, not an atomic snapshot.
Of the inspected 96 MiB VRAM and 512 MiB MAIN regions, 66 and 137 one-MiB
blocks respectively were readable. Unreadable blocks have explicit metadata
and placeholder bytes; comparisons must exclude them. The interpreted
resource objects, metadata table and dependency/name pool have recorded
readable coverage.

The complete primary bike vertex payload (964,576 bytes) matches readable
VRAM at `C5C0EC00`, and its complete index payload (93,926 bytes) matches
`C3171200`. The configured launch-US `bike01` and `bike01_LV02` copies share
these payloads: equality establishes resident source bytes, not which package
provided them, load completion, conversion or GPU consumption. The vertex
resource `00030E22B17D9C31` has a MAIN object/descriptor linking that VRAM
address to stride 32 and 30,143 vertices.

All 14 retained attribute-zero spans from the earlier indexed-draw run also
match this newer VRAM snapshot at their deterministic addresses. The large
float-position buffer at `C5998000` is distinct from the resident bike
payload. Its MAIN object and descriptor identify resource
`000317308816E69D`, stride 32, 3,862 vertices and size `0x1E2C0`.
Resource-info metadata links it through eight named mesh dependencies of
the loaded `3Dsky_vehicleselect` environment: trailers, inner/outer landscape,
balloon, blimp, ground, midday sky and clouds. This is a resource/metadata
binding, not execution chronology or proof that every retained draw belongs
to one particular mesh. It removes the basis for treating large coordinates
alone as corrupted selected-bike data.

Focused Ghidra work independently corroborates resource-info identifier,
name, dependency-count and 16-byte dependency-entry contracts. Exact decoded
instruction bytes were checked against the configured original ELF;
incomplete function coverage remains explicit in [translation evidence](TRANSLATION.md).
The next diagnosis must distinguish environment projection/clipping from
the separate bike load/conversion/upload/draw path. Neither has a proven
correction. Existing negative-w/depth mapping and upstream differences need
their own contract and native evidence before modification.

### Preserve homogeneous clip-W (issue 24)

The retained environment draw uses constants 260–263 for its world transform
and 64–67 for final projection; constants 256–259 are not its final projection.
CPU evaluation of captured positions/constants puts every vertex of draw 10
behind the camera. The curated vertex decompiler nevertheless emitted a
negation of the entire clip vector when W was negative, making that geometry
eligible for rasterization. The inspected fork and current upstream emit direct
scale/offset output instead; reference agreement alone was not the proof.

A bounded hardware D3D11 replay compiled the actual captured HLSL and used its
474 uploaded vertices and constant block. With depth clipping disabled, no
culling and an authored coverage-only fragment shader, the former output
covered 391 pixels where zero was required. The positive-W control draw covered
425 pixels. An ignored curated-source trial in the own ps3recomp fork removed
only the W-sign negation, regenerated HLSL through the actual decompiler, and
verified equality except for that line. The behind-camera replay then covered
zero pixels; the control remained at 425. This isolates clipping coverage,
not game materials, depth interactions or complete D3D12 behavior.

The selective native port removes that single emission while preserving other
curated depth/viewport behavior. `python scripts/check_rsx_clip.py` compiles an
authored NV40 MOV fixture through production `rsx_vp_decompile` and performs
pixel readback. The old source renders the behind-camera triangle (8,192 pixels)
and fails; the corrected source rejects it and retains the visible control
(8,192 pixels). Explicit hardware and WARP runs pass. CI uses WARP deliberately;
it is not native-game or hardware-performance acceptance. No original shader,
vertex, constant or asset payload is in the published regression.

Supported optimized build `20261013T190744.410183Z` produced EXE SHA256
`e1e041a43880f7cfe71a58ee0dfb4ccc866ca524cf8ce8a7276fee52fa711e34`.
Muted named-US run `20261013T192701.416457Z` used the ordinary observed route,
including the Evolution-caption skip, ticket, Anything and bike-class inputs.
The selected MOHAWK heading was observed in frame 130; after 35 more seconds,
the desert environment was visible without the prior enormous blue triangles.
The logo appears intact in the retained ticket and selection captures, matching
the user's qualified observation. Ground stippling and the bike-loading emblem
remain. No race-confirmation input was sent. Explicit stop at 130.828 seconds,
guard termination and return 1 do not establish bike completion or racing.

Replay defects were corrected separately under issue 85. The first candidate
run `20261013T191355.170966Z` retained the ticket view but timed out on an old
reference and stale lexicographic frame selection; duration guard stopped it
at 301.532 seconds. Run `20261013T192050.549517Z` stopped its controller on a
partial BMP and subsequently exhausted workspace disk space; its final JSON
write failed. Missing native process and terminal launcher/controller handles
establish termination, not a complete final record or acceptance. Redundant
render-target BMPs from these two runs were removed while retaining backbuffers,
manifests and logs. The successful repeat capped capture at 180 frames and
updated only the observed private ticket-art reference. Issue 24, original-menu
acceptance and normal-PLAY racing remain open; retail mstream remains parked.

The subsequent muted run `20261013T193559.785161Z` used the same EXE and
acknowledged all eight ordinary-route inputs, including one MOHAWK confirmation
from fresh frame 63 (text match 1.0). Sixty more seconds were retained before
explicit stop at 112.765 seconds, guard termination and return 1. Last completed
frame 77 remained SELECT A BIKE with the environment and no bike model; the
loading emblem was absent in that still. No race successor or driving was
observed. This does not identify a new wait/producer or prove which load stage
failed; the scoped PVS evidence remains separate.

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

### Packed normals/tangents: fetch regression passes, menu remains malformed

The earlier verified DeepEnd draw has format-6 size-one attributes at a2
(normal) and a9 (tangent). The legacy shared fetch lacked this packed-format
case and instead read the four bytes as float32. Captured converted tangent
slots contain non-finite values. Reinterpreting their original packed words
as signed 11/11/10-bit components yields finite near-unit vectors for the
valid references: normal lengths 0.99791--0.99986, tangent lengths
0.99881--0.99995. These are private CPU correlations, not GPU pixel proof.

The authored production-component regression fails on the preserved old source
(return 1: a packed synthetic vector becomes -2.7502439,6,7,8), then passes
with the added format case (1,-0.500488758,-0.50097847,1). Disabled attributes,
ordinary float input, stride, location and frequency controls also pass.
No game word or captured program is used in the regression fixture.

Muted automatic run `20261012T154128.842569Z`, EXE SHA256
`7dff3e4a718d5928e8b1c18fa566f13fbcf738a1aeff72b4e6e9cd1e34c47a25`,
uses the original debug-US ELF, ordinary preserved generated tree and four
normal screen-gated inputs. Internal frame 11 still shows the malformed
bands, black background and no recognizable tickets; RT `00D00000` is black.
The corrected input contract does not satisfy menu acceptance. Continue with
viewport/front-face/depth and exact fragment/sampler/composition evidence.

### GPU pixel execution and immediate ticket-target reads (issue 22)

Two bounded, disabled-by-default observer prototypes were authored first in the
own fork and executed only from private diagnostic binaries. Eight fenced
D3D12 pipeline-statistics queries in `20261012T160741.687652Z` showed the actual
guest PSO executes: operations 22–25 produced zero pixel-shader invocations,
while operations 34–37 produced 47,222 / 9,075 / 63,018 / 17,994. All eight
submitted their expected vertices and clipper primitives. Early back-face
rejection therefore cannot explain the whole missing ticket.

Immediate target copies in `20261012T162352.446244Z`, diagnostic executable
SHA256 `beafb2f125d39429720dfcf70ce0aeb75efb7fcb16831cd27ebfca0aa54b145d`,
captured the target after operations 34 and 37. Both complete 1536x1280 RGBA8
readbacks had zero nonzero RGB pixels but sixteen distinct alpha values, with
changing alpha coverage. Black RGB is already present at those boundaries;
a later overwrite alone cannot explain it. These observations do not expose
floating-point shader values or independently validate every sampled view.
A preceding stage-copy attempt launched the old query-only binary due a private
path-substitution mistake; its launch hash exposed the mismatch and it has no
stage-image verdict. The corrected launcher validates the expected executable
hash before process creation.

Standard CPU BC2/BC1 decoding of the previously verified original active
Deep End diffuse and normal payloads produces recognizable ticket art and its
normal atlas. This is source interpretation, not GPU sampling or menu acceptance.
No loose RPK extraction has been established as necessary for that resource.

The exact bound ticket program has one MAD at byte offset 624 with source 2's
absolute flag set. The legacy decompiler discarded this flag. Own-fork commit
`0d03c8b` fixes only that operand decode. The authored production-decompiler
regression fails the preserved baseline and passes the candidate, including
negation-after-absolute and plain-operand controls. The initial checker passed
a float array to the typed constant-block API and produced an unreliable local
pass; CI exposed it. The corrected fixture uses `rsx_fp_constant_block`, verifies
its count and authored constant word, and reproduces baseline failure and
candidate success (`20261012T172118.149873Z` / `20261012T172120.581554Z`).

Ordinary-source native candidate `20261012T165232.509027Z`, executable SHA256
`45e4de11c7259569abe2c73b31b6b7483ec9661b56f28688715581eeedae5ed5`, used
the same debug-US ELF and four screen-gated normal inputs, with no observer,
user navigation, desktop control, or substituted assets. Internal frame 11
still shows SELECT A RACE, broad bands, black background, and no recognizable
tickets. Menu correctness remains failed. The next seam is actual sampled RGB
and floating-point shader state; the native goal stays active.

### Floating-point ticket probe — October 12, 2026

Private, default-off auxiliary FLOAT4 observation retains original color0 and
uses the real bound guest program and normal automated input route. Query
boundaries 4/7 correspond to operations 34/37. The selected draws have blending
disabled and full RGBA writes; their auxiliary values are not alpha blended.
Successful target arrival remains separate from graphics acceptance.

- Raw export run `20261012T175202.691355Z`: finite exact-zero RGB with changing
  alpha. This excludes final UNORM conversion as the only loss.
- Actual normal texture sample run `20261012T175629.617339Z`: nonzero finite
  sampled RGB at both boundaries. Source texture equality alone was not used
  as sampling proof.
- Constant 17 run `20261012T175755.858329Z`: X is 1, other channels 0, at all
  47222/17994 covered pixels. Its binding is correct at these boundaries.
- Texcoord 6 run `20261012T180116.676800Z`: Z is exactly zero everywhere; X/Y
  vary and W is positive. Fog run `20261012T180246.438842Z` confirms all fog
  channels broadcast the positive clip-W value at these boundaries.
- Arithmetic observation run `20261012T180413.156873Z`: before the final
  multiplier the shader still has nonzero finite RGB. The following exposure
  multiplier obtains its scalar from texcoord 6 Z and reduces RGB to zero.

The private v2 observer executable is
`8913a96d0b74b1d73d8cb3404065a4ce87c0f010cf079a2edc97462c03c91ab0`;
launchers check that hash before process creation. Captured vertex program
analysis traces texcoord 6 Z to constant 73 X. Its captured raw bits are
`00000001`, a tiny float that rounds to zero in a half register. This narrows
the next investigation to constant production/upload, including the guest
producer; it does not justify replacing the value or blaming one decoder yet.
Original command/shader bytes stay private. The diagnostic backend source was
restored after the build; the ordinary executable still needs rebuilding.
Original menu correctness and playable normal PLAY remain failed/unverified.

The bounded constant FIFO observer run `20261012T181026.979811Z`
(executable `ed1a6b9edf77fcdccecddf484b7aa2985afe16f5faec2c0e298973c0973b62b9`)
recorded 536 writes to constant 73 after target arming. All 134 vec4 uploads
contain X bits `00000001`, Y zero, Z `10138E20`, W zero, directly in an
incrementing LOAD-plus-vec4 packet. The GPU snapshot agrees with the FIFO;
this observation does not support changing the constant register decoder.

Writer-watch run `20261012T181338.657723Z`, using the same executable and
normal route, identifies the reliable guest link register as a call inside
`PostEffectsInstance::FrameStart`. The sampled host function identity is
misleading because of identical-code folding; it is not evidence that a mutex
function uploads constants. At the watched FIFO address the exposure upload
starts with ordinary positive float values and decays to bits `00000001`.
The guest routine reads a half-float pixel, smooths it into its exposure value,
then uploads constant 73. The next probe is that input pixel and its producer;
no exposure substitution or forced constant was applied.


### Native GPU-to-guest exposure coherence mismatch (2026-10-12)

- Read-observer run `20261012T181941.830966Z`, EXE SHA-256
  `4e4eb619fc80dc0772569aa0eeb2d45877fa6014c6ed0b5777a2ea04664e4e3d`,
  followed the normal muted menu replay and closed at the target. The getter
  returns a buffer at `C2A30480`; FrameStart reads its center half-float at
  `C2A34580` (64x64 RGBA16F, 512-byte rows, pixel 32,32). Guest reads return zero.
- Combined raw-GPU/read-observer run `20261012T182704.250088Z`, EXE SHA-256
  `6c258c6beae4ad9ee14b7e2d2507b30f84872edf6d7e935d59f211870b6d5048`,
  independently repeated the normal route. Fenced GPU readbacks for render target
  `02A30480` contain center red half `3C00` (exactly 1.0), whereas all 146 observed
  guest half reads at the corresponding EA contain `0000`. Later GPU center RGBA
  is `(1, 9.953125, 9.953125, 0.9951171875)`, with raw halves
  `(3C00,48FA,48FA,3BF6)`; DXGI 10, pitch 512. This is raw data, not BMP tonemapping.
- The established producer chain is GPU exposure surface -> guest half read ->
  FrameStart smoothing -> FIFO constant 73 -> tc6.z -> ticket RGB multiplier.
  Missing GPU-to-guest visibility explains the measured zero input and exposure
  decay. Implement and test a general surface-coherence seam, including endian,
  pitch, format, identity and render-thread synchronization; do not substitute an
  exposure constant. First prove GPU/guest equality, then repeat ordinary native
  menu/normal PLAY acceptance. The precise synchronization strategy remains open.
- Upstream open PR #224 implements transfer coherence for the register-file
  engine's RGBA8 surfaces. It does not cover this legacy D3D12 FP16 CPU-load seam.
  Preserve its provenance if reusing any implementation.
- Observers remain private and default off; tracked runtime files were restored.
  Menu graphics and playable-race acceptance remain unresolved.


## Typed GPU surface visibility candidate and placement follow-up (2026-10-12)

- Fork-first implementation queues typed PPU/HLE reads of device-owned pages to
  the renderer. A separate allocator/list/fence copies actual offscreen pixels
  before the unchanged read. Draw-time DMA identity, pitch and format are retained;
  FP16/FP32 bit patterns and guest endianness are preserved. Dirty generations
  avoid redundant copies. Unsupported layouts, failed events/fences and pending
  renderer-thread reads raise tagged errors rather than returning invented data.
- Actual fast-accessor regression: old header fails `fast guest half read sees
  device 1.0`; candidate passes. Actual fork HLE header repeats red/green. Authored
  fixtures cover 8/16/32/64-bit access, negative/infinity/NaN bits, row padding,
  differing pitches and invalid lengths. Run `python scripts/check_rsx_cpu_surface.py`;
  fixture is `scripts/fixtures/rsx_cpu_surface_memory.c`. These are primitive tests,
  not native visual acceptance or a performance measurement.
- Combined native proof run `20261012T190951.505938Z`, private EXE SHA-256
  `a90225402d7b083917224aedbb4b0d54d184be12c162bcdffbad2b88d5487dd1`:
  fenced GPU center half and latest PPU half at `C2A34580` both equal `3C00` (1.0),
  with 146 observed reads. The identical private comparator previously returned
  failure for GPU `3C00` versus guest `0000`; it now passes. Private observation
  blocks were removed from tracked source after the diagnostic EXE was copied.
- Ordinary candidate SHA-256
  `450c2a0d2ae8a567d53782b07bd7caddd7d28aeac9b95a615d36f7fb6391e715`,
  run `20261012T192751.538171Z`, reaches the replay target; original ticket art and
  moving intro content are visible. User independently reports real video and
  assets confined to the lower third. Video content also appears in internal
  frames, including frame 45. This is progress, not correct layout or playable
  race acceptance. Band geometry and placement remain visibly wrong.
- The old blank-intro replay checkpoint is invalid now. Private replay instead
  compares a genuinely observed Sony intro region; this can wait for a matching
  animated frame. Remaining inputs and target use established text checkpoints.
- Placement hypotheses: reversed dimensions in the guest producer; incorrect
  viewport/composite mapping; incorrect vertex position arithmetic. Private
  readonly FIFO run `20261012T193554.660724Z` shows initial clip/viewport
  `1280x720`, then full-scene `720x1280`, with matching scales/offsets. The portrait
  values exist before the renderer decoder. Trace the producer and final composite
  before introducing a dimension swap. No geometry substitution has been applied.
- Current scope is typed CPU reads of registered legacy D3D12 offscreen color
  surfaces. Bulk-pointer/SPU writes and complete bidirectional ownership are not
  established by these tests. Normal PLAY race, layout, sound, saves and minimum
  60 FPS remain unverified. Retail mstream stays parked.

Placement producer checkpoint (2026-10-12): the private read probe
`20261012T195415.330090Z` observes the GC buffer metadata before command emission:
its dimension fields already contain 720 and 1280. Writer probe
`20261012T195635.820779Z` identifies `GcRenderBuffer::Create` as the initializer;
value-filtered probe `20261012T200234.486324Z` preserves the relevant caller chain
through `evo::renderer::PixelBuffer::Init(IStream*, unsigned)`. The SDK command
writer copies these dimensions into the FIFO. Initial display setup remains
1280x720. Next inspect how the PixelBuffer resource obtains/computes its dimensions
and compare its source descriptor; renderer decoding alone has not been shown
responsible. Private generated excerpts and register/stack dumps remain ignored.

User-authorized current capture from the writer probe shows SELECT A BIKE with
readable UI/logo, missing bike art and a narrow central object. This adds native
observation of the remaining defect, not geometry or race acceptance. The owned
writer/read probes were closed explicitly before each next launch. The current
value probe uses normal input and lets the now-visible intro play naturally;
exact animated-image equality was an unreliable skip checkpoint.

## AA sample layout and current native acceptance (2026-10-12)

The original ELF's constructors/callers, captured metadata and FIFO agree on
720x1280 full-scene targets after 1280x720 display setup. No lifting-induced
dimension transpose was demonstrated. The first proven placement seam is the
legacy backend's sample-memory extent: format `0x3148` uses AA mode 3, a 2x1
sample grid. Clip 720x1280 therefore needs 1440x1280 sample storage. Inferring
visible width from its padded 6144-byte pitch incorrectly yields 1536 columns.

The fork-first shared helper maps mode 0 to 1x1, mode 3 to 2x1 and modes 4/5 to
2x2, rejecting unknown layouts, null outputs and overflow. Offscreen viewport
and scissor follow the same grid. Row padding does not add visible columns;
an 8x8 non-AA surface with 64-byte pitch remains 8x8. Registered display targets
keep their existing path. No guest dimension swap or fabricated content is used.
This models sample-memory dimensions; bit-exact hardware MSAA coverage and
sample patterns are not established.

`python scripts/check_rsx_surface_layout.py` compiles the actual production
`current_rt_off`, RSX state and helper against authored states. The preserved
old backend fails with 1536x1280 versus required 1440x1280; both curated candidate
and own-fork candidate pass. Fresh red/green evidence is under private
`temp/checks/rsx-surface-layout-20261012T225405.638776Z`,
`...225405.639783Z` and `...225408.269922Z`. The fixture does not prove native
visual correctness or measured performance.

Private native trial run `20261012T203436.372458Z`, EXE SHA-256
`f52ddfc50c7f89dea59b8a84a8afb8846de7b489a7ebc7c4fddb45755766f8ca`,
shows real video filling 1280x720 at frame 19 and an authentic main menu with
proper logo/background and PLAY/ONLINE/EXTRAS/SETUP placement at frame 65.
The ordinary supported run `20261012T205459.922815Z`, EXE SHA-256
`3822b2341dbbf26e670189cb392a00b680a56434aa8c58f5860c784967177fc2`,
records the intended screen-gated replay profile and original ELF/disc pair in
`launch.json`. Normal CROSS input is acknowledged for language, PLAY, festival
help and SELECT A RACE. Frame 61 has readable original ticket art at lower right,
but broad malformed yellow/black/gray geometry across the screen.

The replay records `target_observed=true` and
`graphics_correctness_verified=false`. Race-ticket sizing/ordering/selection
acceptance in issue #22 is therefore unmet despite restored art/color; the
issue must remain open. Bike geometry/art, normal PLAY race acceptance, driving,
opponents, audio, saves and minimum 60 FPS remain unverified. Retail mstream
stays parked; the resolved top-right flashing defect is not reopened.

A private wrapper previously replaced `sys.argv`, causing it to ignore supplied
replay profiles. Those earlier wrapper results do not prove the requested full
intro route. Use supported `scripts/run.py` and inspect its recorded profile.
The current profile lets the intro play normally, with the main menu around
four minutes; exact animated-image equality remains an unsuitable unattended skip gate.

## Packed render-target sampling and residual stipple (2026-10-14, issue 94)

The user reports pixelated/blurry motion and a translucent foreground hill;
these are unresolved visual defects. Muted baseline run
`20261014T130115.408755Z`, EXE
`0c9997e061264243efeb62e99e769653987bdd9c4f959f875b5046e9ad32c156`,
reaches MOHAWK through acknowledged normal menu inputs, including one manually
observed internal intro-frame skip. It stops explicitly at 138.687 seconds.
No PPU watch or bike observer is enabled. Full RSX captures retain color
targets and draw/texture manifests; BMPs drop alpha and cannot prove raw HDR
or packed values. The final scene target shows a solid hill, whereas display
output shows hill ghosting and pronounced terrain stipple.

Frame 65's geometry renders RGBA8 to `00D00000` plus MRT1 `01F90000`.
Display op328 samples MRT1 as format `BF`, 1440x1280, remap `29E4`;
the enum/layout independently identifies guest Y16_X16_FLOAT, two half floats
per four-byte texel. The backend instead binds the matched target's RGBA8
resource format and identity remap. That is a typed-sampling contract mismatch.
Ranked alternatives are AA-coordinate scaling, stale history inputs, then
depth state; a still does not identify a temporal filter by itself.

Fork-first candidate decodes the packed guest ARGB bytes to half floats before
filtering, applies the requested remap, and keys PSOs on alias state. It matches
the backend's current one-mip static point/clamp unit0 and linear/wrap other
units. Other formats and guest sampler policies are outside this correction.
`python scripts/check_rsx_texture_alias.py` executes that production adapter
on an authored RGBA8 texture: unpatched sampling fails seven float-readback
cases; adapted WARP and hardware pass positive/negative pairs, clamp/wrap,
pre-filter decoding, named textures, remap and LOD/bias cases. No game data.
Own-fork full Windows runtime library and the supported native build pass.

Candidate run `20261014T131633.495135Z`, EXE
`e75da09611d4e54dce68f728c542fb131ebd2a81c0675f7d732b14e823713af0`,
uses the same named-US target, capture settings and ordinary menu route.
Its main menu appeared before the attempted intro observation, so no skip was
sent; the existing observed PLAY controller continued. A bounded owned-process
pause always resumed. Final frame37 shows a solid hill with visible rocks and
flag, but fine terrain stippling and absent bike remain. Explicit-stop terminal:
98.656 seconds, return1, visible owned window verified. This is partial native
visual improvement, not issue94 closure, race entry, complete motion correctness
or a frame-time measurement. Issues #24/#13 remain open; retail stays parked.
Dense temporal comparison and locating the first pass with residual stipple
remain necessary. Original captures, shaders and target bytes stay private.

### Vertex-color terrain blending and sampler mismatch (2026-10-14, issue 94)

The user specifically requested checking vertex painting, including future race
landscapes. Retained native run `temp/runs/20261014T132520.253865Z` (EXE
`e75da09611d4e54dce68f728c542fb131ebd2a81c0675f7d732b14e823713af0`)
reached MOHAWK by acknowledged ordinary input and stopped explicitly after
110.593 s. Its owned material snapshot validates process/EXE/guest base and
records ten sequential bounded texture reads with hashes. CPU BC1 decoding shows
detailed original diffuse and normal maps; the earlier startup texture observer
exhausted its 32-capture quota, so absence there does not establish missing art.

Copied private shader evidence into that run before future FP_PICK overwrites:
`terrain-vp.hlsl`, `terrain-pick.hlsl`, `terrain-pick.bin`. The binary is a live
program read, not independently admitted as the SET-time snapshot. The captured
HLSL for FP `05B6DC81`/VS26 (frame46, ten selected draws) establishes:

- Vertex input attribute3 goes directly to output1/COLOR0 (VP lines34-35,185).
- FP line200 reads COLOR0 R/B/A into half-register1 x/z/w. Line211 uses B in
  `h6.xyz = B * constant6.xyz + constant5.xyz`, then saturates derived terms.
- Texture1 is sampled at line294. Lines305,324,335 form a material blend with
  R: `h2 = R * (sample1.xyw * constant10.xxy - prior + constant11.xxy) + prior`.
  This is vertex-color-controlled material/detail blending, not merely a final
  RGB tint. It does not identify the artist's painting tool or establish that
  all terrain materials or race tracks share this shader. Alpha is loaded;
  its eventual role has not been established.

Preserve attribute3 normalization, channel order, interpolation and the
half/full-register alias semantics when investigating flat terrain. A complete
hill mesh/vertex-color span and an isolated pixel replay remain needed; the
shader is shared by multiple draws, so first vertices alone do not prove full
foreground coverage. Race landscape COLOR0 and material blending need their own
native draw/asset binding before acceptance.

A separate read-only metadata candidate retained sampler address/filter/control0
and mip counts at draw time (no sampler rendering change). Run
`temp/runs/20261014T133222.152229Z`, EXE
`bd23b6b14eba9ad409d36f3db582be4543ae2bc579d432ddadb14c1e163d0644`,
frame60 shows FP05B6DC81 t0 BC1 1024-square, address60010121, filter02043F80,
control080078010, 11 mips; related 256-square maps have9 mips. FP04DE6701 uses
address60010101/filter02043F34 and 11-12 mips. These request repeat S/T and linear
min/mag; the current D3D12 root signature hardcodes unit0 point/clamp for fonts.
The display XY16F alias instead requests address60030303/filter01012000,
point/clamp, matching its existing adapter policy. Native upload resources still
have one mip, so the evidence rejects selecting a low uploaded mip as the direct
explanation, but missing mip filtering remains a distinct potential source of
motion shimmer. No sampler fix or native hill/graphics acceptance from this run.
The owned visible muted run stopped explicitly after128.719 s, return1; one
observed intro CROSS4 was acknowledged13:33:55.836287Z, frame48 SHA
a6443130e5b588ec45b473c7d0fa018955aa3486aacfaf2345c7f043b5c23847.

Authored sampler GPU reducer uses the production descriptor decoder: old fixed
states fail five of seven cases, candidate WARP passes all seven. Controls retain
point/clamp font behavior; coverage includes repeat, linear interpolation, mixed
S/T, a high texture unit, border and mirror. Decoder checks anisotropy, signed
LOD bias, LOD bounds and explicit unsupported-address rejection. Evidence:
`temp/checks/rsx-sampler-20261014T133640.242508Z`. Backend binding integration
and native verification are still required; this does not establish hill causality.

## Preview depth-surface identity trial (2026-10-14, issue 94)

The curated D3D12 backend creates one D24S8 depth resource. It binds that
resource for every guest surface. It also clears depth and stencil when the
color target or MRT set changes. `surface_zeta_offset` does not select the
attachment. This loses depth when a later color pass reuses the guest zeta.
It also lets an unrelated surface clear the scene depth.

The candidate uses an address-keyed D24S8 cache. It records the zeta offset
for draws and ordered clears. A color or MRT change no longer clears depth.
The frame waits for earlier GPU work before it prepares or grows resources.
Batch merging requires the same zeta offset. Allocation failure is fatal.
This trial does not add depth-as-texture sampling or validate other zeta
formats, memory locations, or content preservation after resource growth.

Game-free D3D12 readbacks pass all six original cases on WARP and hardware.
They cover color-target changes, separate depth addresses, a smaller clip,
a return to the scene, stencil preservation, and an explicit selected-surface
clear. The authored legacy single-buffer control fails four cases. It is a
control, not a native replay of the old renderer. The candidate source
compiles separately in the own fork. These results do not establish a
visible MotorStorm correction.

The first isolated build has EXE SHA256
`cc1faf37a571b201a0baa60774f472177c38bc931cfb7d128e915228aa3bd6c0`.
Run `20261014T191239.969343Z` in the convolution-capture worktree follows
normal screen-gated input to MOHAWK. The launcher stops after the text
checkpoint. The final completed frame15 is black behind the menu text. Its
manifest has 104 records and two scene-overlay draws, but no preview terrain
geometry. Thus this run stops too early to compare flag occlusion or the
foreground hill. The private replacement checkpoint requires an observed
distant ridge as well as the MOHAWK text. It rejects the label-only black
frame offline. The restored main executable remains separate. PR98 remains
unaccepted.

Run `20261014T191720.231032Z` with the same candidate reaches the selection
scene, but the user observes correct flag draw order with a missing sky and
retained pixels behind it. Its manifest records every far-plane clear as
z=0.99998480 s=255. That equals the packed value 0xFFFFFF00 decoded with
reversed fields: the curated `rsx_commands.c` read z24 from the low 24 bits
and stencil from the top byte. See the next subsection.

### Packed z24 clear decode regression and fix (2026-10-14, issue 94)

RPCS3 decodes NV4097_SET_ZSTENCIL_CLEAR_VALUE for D24S8 as z24 in bits 31:8
and stencil in bits 7:0. The own fork scaffold has carried that order since
its first commit, so the curated vendor copy is the outlier. The reversed
order cleared depth to 0.9999848 with stencil 255 at the far plane. The sky
quad then failed the depth test, and the color target kept the previous
frame pixels because the game clears depth, not color, for that pass.

The game-free contract now lives on fork branch `codex/depth-clear-contract`
(commit 18061de). Six added packed-clear cases drive the production
rsx_process_method decode into the address-keyed cache. The reversed order
fails all six on WARP and hardware and leaves the prior-frame color
untouched. The z24-high order passes twelve of twelve cases while the legacy
control fails four. Evidence: `temp/issue94-depth/20261014T194936`
(red) and `20261014T194940` (green) in the fork.

The curated decoder now reads z24 from bits 31:8 and stencil from the low
byte. Candidate EXE SHA256
`ed33612e4fb8040858919fb3132fff63b1dae528f8f3aaf4bbb159dbc32dae76`.
Owned muted replay `20261014T200115.394376Z` reaches the selection scene.
The sky band y20-140 returns to blue-dominant `(65.4, 72.9, 82.5)` against
the baseline signature `(53.6, 64.4, 82.1)`; the broken candidate showed the
warm retained smear `(95.2, 88.7, 77.8)`. The user confirms the skybox.

Remaining observed defects on the same scene stay open on issue 94:
a blurry backdrop, a grey platform and no persistent preview vehicle. The user
confirms that white camper vans are correct original props; they are not evidence
of missing textures. UP/DOWN livery changes reportedly show the vehicle for one
frame with the wrong material, then it disappears; a dense native witness and
draw/material/state trace are still required. Limits: the decode covers
D24S8 only; Z16 clear packing, other zeta formats and post-growth content
remain untested; no depth-as-texture sampling.

### Recovery audit (2026-10-15, issue 94)

Fresh authored fixture compilation at own-fork `18061de` passes 12/12 readbacks
on WARP and hardware; the legacy control fails 4/12. Private source hashes,
build log and readbacks: main `temp/audit-20261015/depth-20261014T233451Z`.
This exercises the real cache helper and command decoder. The fixture simulates
backend binding/recording, so it does not prove the entire production backend.

The local ownership retries, SELF_FB experiment and environment passthrough
were reverted in `aed81af`, `e412834`, `1c86529` and `9bcb8a3`. Earlier PR text
claiming that ownership retries deterministically fixed replay is withdrawn:
run `20261014T213856.719775Z` reported lost ownership while rendering continued.
The cause remains unresolved. The separate PAD_FILE sharing retry remains a
candidate; it has no authored actual-send sharing/ownership-loss regression yet.

The inherited `to-preview-5s.json` skip reference was an autosave warning, not
a cinematic. Its timed claim and CROSS2 gate are rejected. The corrected private
route uses one acknowledged CROSS8 after LANGUAGE on the inspected Sony caption,
ROI `[740,490,400,15]`, contrast threshold 0.95. Muted owned run
`20261014T233356.731003Z`, EXE SHA256
`d9b1af564150eb048ede3cfaa39ae809035433917ddc0c5adb8618cb1e96c33b`,
acknowledges the skip at 23:34:26.811852 UTC (score 0.957759), then reaches PLAY
in frame11, visually inspected. The launcher closes at 38.484 seconds.
The wider Sony ROI missed at 0.9499 in the preceding explicitly stopped run;
the threshold was retained and the caption crop corrected. This proves one
corrected early-caption skip, without establishing race or scene correctness.
The prior Evolution-caption skip also reached PLAY. Repeated-hold causality for
the separate Havok 8320-byte allocation failure remains unproved.

Repeat run `20261014T233507.334993Z` missed a different Sony fade (score 0.864),
so the single-reference gate is not accepted as reliable. Issue104 adds explicit
observed `reference_variants` under the same optional action, without lowering
the threshold. With that tooling, consecutive runs `20261014T233820.319968Z`
and `20261014T233859.335448Z` each acknowledge exactly one caption CROSS8
(scores 0.992368 and 1.0), reach visually inspected PLAY frame11 and close at
about 38.5 seconds. Private `temp/audit-20261015/intro-only.json` and the normal
preview route use the corrected gate. These are intro receipts, not race proof.

### Public rendering references

[Drakengard 3 Recompiled](https://github.com/soyjxck/dod3-recomp) reports
native Windows D3D12 and macOS Metal gameplay. It uses the ps3recomp
runtime family. This is project-reported native evidence, not a local
gameplay verification.

[Merged upstream PR236](https://github.com/sp00nznet/ps3recomp/pull/236)
tracks color/depth writes by address and reads depth back through guest
texture formats. Its depth readback hook has a Vulkan implementation. It is
not a drop-in fix for the curated legacy D3D12 backend.

[Open upstream PR280](https://github.com/sp00nznet/ps3recomp/pull/280)
fixes live-draw depth snapshots, same-address color/depth preference, and
sampling the bound zeta with depth writes off. Its reported test uses Proton
and a test-only shader change. It does not prove native MotorStorm behavior.
No wholesale backend replacement or upstream branch trial is accepted here.

## One-frame livery vehicle captured at native input (issues 24 / 110)

Run `20261015T001556.521391Z`, native EXE SHA256
`6442b20f4bbbafef96c8d916ad37a6e6ea50e5ebdd55d0151987db3f81fe9b8f`,
followed normal LANGUAGE / observed-caption skip / PLAY / ticket / bike-class
inputs. The original ELF identity stayed unchanged. After visually inspecting
the selection scene, one screen-gated UP hold of four polls was acknowledged
at `00:17:26.759008Z`. Native PAD_FILE consumption triggered the renderer
capture directly, without a guest address condition or forced transition.

All 64 complete backbuffers/manifests have consecutive frame counts
2522..2585, capture indices 22..85, burst reason and presenting flag. The
ignored run contains `capture-event-proof.json` with input, launch/final
identities and hashes. It is pinned with `.keep`; original captures remain
private. The bounded launcher ended at 141.063 seconds, with guard termination
and return 1. This is not a race or performance acceptance run.

The user's transient vehicle witness is now directly reproduced:

| Capture | Guest-render frame counter | Recorded operations | Observation |
| --- | --- | --- | --- |
| 32 | 2532 | 376 | Loading emblem; no bike |
| 33 | 2533 | 667 | Recognizable bike, malformed stippled/flat materials |
| 34 | 2534 | 381 | Bike and loading emblem absent |

The visible frame has 657 DRAW records and 10 CLEAR records, versus 372/4
before and 377/4 after. It includes 125 draws using run-local VS32 into
RT `0x02B90000`, and 141 using VS33 into RT `0x00D00000`. Neither shader group
appears in the captured operations of frames 32, 34 or 35. These are observed
groups, not recovered semantic shader names. A private differential records
the remaining FP/material signatures.

Next probes distinguish three explanations: cached/replayed RSX commands
stop reaching draw recording; guest scene/visibility logic stops generating
the bike batches; or a submission/present boundary places the batches outside
the captured list. Compare the guest command producer, decoded draw callbacks
and recorded batch boundaries around the same livery event. A GPU-only
material/depth rejection cannot by itself explain the missing shader groups
in the next captured list. The malformed material in the visible frame also
remains unresolved. This does not establish correctly rendered assets.

The earlier rebuilt run `20261015T000411.867467Z` missed the intro gate:
its inspected Sony-caption frame 12 scored 0.80938 against the best previous
reference. The movie continued playing; it was not a demonstrated native
video stall. That genuine caption was added as another observed private
reference with the same 0.95 threshold and once-only optional action. Run
`20261015T000830.431354Z` then skipped once and reached inspected PLAY at
40.484 seconds. Subsequent normal-route runs also skipped once. These are
specific receipts, not universal reliability proof for all caption phases.


## Container allocation ABI and native shape preservation (2026-10-15)

[Issue 119](https://github.com/robbe1912/motorstorm-mv-recomp/issues/119)
now has a production-path reproduction and a generic allocator correction.
The curated syscall 350 handler decoded r3/r4 as container ID/size; the LV2
ABI is size/container ID/flags/output in r3..r6. The
[RPCS3 declaration](https://github.com/RPCS3/rpcs3/blob/2003f2404fc3db469c1b95478051be1109421522/rpcs3/Emu/Cell/lv2/sys_memory.h)
and implementation independently establish that order. The unchanged C unit,
called through its registered syscall, took a 6 MiB request with CID 1 and
tracked only 1 MiB; its following ordinary allocation overlapped the requested
extent. The corrected production unit reserves all 6 MiB. The authored fixture
also checks page flags, IDs, physical/container/VA/slot budgets, free accounting,
busy-container destruction and failed-commit rollback.

The generic implementation is saved on the own-fork
[container-allocation branch](https://github.com/robbe1912/ps3recomp/tree/codex/memory-container-allocation),
implementation commit `9c72279`, CI wiring `44c5ed0`. Its native port is in the
active worktree's curated `runtime/syscalls/sys_memory.c/.h`. It shares the
ordinary allocator's physical budget and alias-aware VA selection; no game
routine, memcpy, pointer or resource-lifetime bypass was added.

The supported optimized build produced EXE SHA-256
`44f7b3997e888dd4765a8d8b9bbb4c529895fd569f6368494c12348baf692826`,
PDB `984642640a55d38951e9f5c0f495cb5427c14397cb186950d934a86fce3a28e7`,
using the unchanged named-US ELF. Native run `20261015T163536.232616Z` used
8 observed/acknowledged ordinary CROSS inputs, muted/windowed ownership and
an explicit owned stop. A PDB/loaded-CodeView-bound read-only metadata snapshot
records CID 1's allocation at `4D700000`, size `600000`, bump `4DD00000`.
The original resource ID `000AE0A6:74683664`, size `530CB0`, fits that extent.
The later ID `000A4B1E:E18E2AF8` now reads into `4E0BFF80..4E0D8F60`, outside
the original buffer, rather than the former overlapping `4DBBFF80` buffer.
Sequential snapshots alone remain insufficient for a complete free history.

The deferred source/shape watch completed 85.031 seconds, 9 hits and 6 bounded
dumps, with no failure or cleanup errors. After initialization, the watched
shape head remains `10070CC800000001` in all recorded subsequent writes; the
old zeroing/name-copy overwrite did not recur in this watched interval.
The resource observer recorded 195 constructors, compared with 131 at the old
fault. No unresolved-indirect or garbage-vcall message appeared; all 16
incomplete fragment-program warnings remain visible. The actual-data verifier
passes, while an explicit old-1-MiB expectation fails at that assertion.
Private raw data/checkers/dumps stay under the run and `temp/issue119-source`.

The separate 300-second control run `20261015T162223.899508Z` likewise passed
the former corruption point, but the captured view became black. Four owned
read-only stack snapshots in the later run distinguish ongoing loading from a
proven permanent wait: the late main-thread sample at 16:37:54 UTC waits through
`B15714/A012E8`, while the 16:37:59 sample executes `C5C424/87D278/6C379C` and
other guest functions. A physics deadlock is not established by these samples.
The next race-entry investigation must correlate progress/physics completion
and actual backbuffers before changing semantics. Native race/graphics
acceptance, controls/opponents/audio/saves, sustained 30 FPS and the final
editable C/Rust plus Windows/Linux game packages remain open. This diagnostic
run is not a frame-time benchmark; retail mstream remains parked.


The curated regression is `python scripts/check_memory_container.py`. It compiles
`src/memory_container_check.c` against the actual curated syscall implementation
without original game inputs. Its authored alias adapter tests conflict avoidance;
`check_memory_capacity.py` separately exercises the real alias registry. Both
pass locally. Compiling the same container fixture against the preserved old
production source fails at the 6 MiB allocation-size assertion. Source-audit CI
runs the regression on Linux and Windows. The selected port's syscall source
matches the native-tested hash above; this is not a clean full-game build from
this review branch or proof of Linux game execution.


Capture qualification correction: in run `20261015T163536.232616Z`, frame 25
is explicitly `presenting=0` (frame count 3001), so its black backbuffer cannot
establish visible black race graphics. The most recent presented capture is
frame 24 (`presenting=1`, frame count 2881), visually inspected as the original
track-loading map/instructions. The metadata/source-watch conclusions above
are unchanged; completed race presentation remains unverified. Future screen
and race evidence must distinguish presented captures from offscreen work.


### Restored-baseline convolution capture (2026-10-14, issue 97)

Sampler PR98 remains unaccepted. Its native boot rejects Gaussian convolution
before LANGUAGE. The restored usable executable stays unchanged:
`a3f153bccfca241407a4736739a52cf4fa8c966eb22633c656bd05ac01affb64`.
This investigation has no independent RSX oracle for Gaussian coefficients,
offsets, LOD or edge rules. Enum names and generic formulas do not supply it.

Muted no-input run `20261014T175706.440055Z` reaches LANGUAGE and stops explicitly
at 70.735 s. Its frame12 manifest records frame_count721, op011, FP01F8C8C1/VS4.
The draw writes RGBA8 target02AE1080 at 320x180 and binds unit0 to that same
OffRT through guest addressC2AE1080, guest formatA5, remapAAE4. Op010 clears the
target to zero. Op013 samples it into02B19480. This is a source-binding lead,
not proof of the intended guest feedback semantics or the root cause.
End-frame BMPs do not preserve the exact pre-draw source or alpha.

The picked HLSL samples unit0 and derives a saturated threshold term from its
blue channel. Captured constants start with -0.00699996948, 20 and 3.
The VP supplies normalized fullscreen UVs with Y inversion. Neither shader
contains Gaussian weights. The old FP_PICK binary dump reads later live guest
memory; it is not automatically the bound SET-time snapshot.

Restored-baseline run `20261014T180311.755705Z` follows acknowledged ordinary
LANGUAGE, one observed intro skip, PLAY, help, ticket and class inputs.
Frame31 reaches MOHAWK INDIANA; inspected final frame33 shows a solid but flat
hill, terrain stipple and no visible bike. The muted owned run closes after
target observation at 70.579 s. This proves the route remains usable, not normal
assets, race entry or graphics acceptance. Captures and shader payloads remain
private.

An isolated capture-only build uses the same baseline renderer, not PR98.
Its raw-copy helper first runs in the own ps3recomp checkout. An authored
7x5 GPU smoke preserves two ordered clears, all RGBA channels and unpadded rows.
The isolated native EXE is
`052cd64b112b36491d308ff0486b058f9dc274f6a6aafa67f93ecdc2e51ba498`.
Its source and output remain separate from the restored executable.

Run `20261014T181650.057259Z` retains source bytes immediately before the draw
and target bytes immediately after it, with resource states restored between
copies. Three selected draws at renderer frames116-118 bind the same host
resource as source and target. Raw RSX offset02AE1080 resolves to guest
addressC2AE1080. Every retained 320x180 RGBA8 pixel is zero before and after.
Each 230400-byte payload has SHA256
`2a589ae1f2fa2a6328223ff195a29c9244bec633dca49139f6f231e1d79c0eb2`.
These captures do not distinguish convolution coefficients, sampling offsets
or edge behavior. Zero input is not a filter oracle.

The verified bound FP snapshots contain 208 bytes and have SHA256
`24b373c14f951e08e7cf5ca178f2a09fe52b132d9de1f0f2cc44690a66c03e11`.
That hash matches the earlier picked binary for these selected draws.
The retained GPU constant banks confirm the three threshold constants above.
This admits these snapshots; it does not validate arbitrary later live reads.
The next sampler prerequisite remains an independent RSX impulse/checkerboard
readback with fractional coordinates, scale changes and boundary samples.

The same owned muted run follows ordinary PLAY to MOHAWK. One observed intro
skip and the model confirmation receive native input acknowledgments.
Confirmation at 18:18:30.094330Z uses completed frame47. Inspected frame51 shows
the race loading artwork; frame60 still shows loading, not gameplay.
The guest then calls sys_process_exit(0) at 150.813 s. The launcher does not
terminate it. The terminal log records an unresolved indirect call to D00A5AAC
with tid9/LR00AFDC10. The existing runtime then replaces a virtual call through
1006D448, this=4BE37300, with a no-op and r3=0. This run does not validate that
fallback or identify the bad-state producer. No Havok observer payload is
produced. Return0 is not race acceptance.
The original usable EXE retains its hash above; no owned native process remains.

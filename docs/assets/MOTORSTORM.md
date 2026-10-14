# MotorStorm asset extraction: worked example

Use the [general method](README.md) for reusable contracts. This page locates the
MotorStorm-specific formats, tools and established correlations; full native
experiment evidence is owned by [graphics/audio research](../research/GRAPHICS_AUDIO.md).
Asset recovery and normal native rendering remain separate acceptance claims.

## Target and containers

The current diagnostic target is the named-US debug executable with matching
launch-US BCUS98137 data; see [building](../BUILDING.md) for identities. Complete
Edition BCES00006 APP_VER03.10 is a different revision. Do not mix its metadata,
addresses or generated code with the launch-US target.

`cache_ps3.txt` indexes vehicle, character and world RPKs. Menu scene/mesh resources
are indexed under `guiscenes` as RIB/EVO records; loose `gui` data includes videos.
The runtime reads the original packed disc. Selective extraction is for identifying
and comparing the original bytes; no loose-menu extraction requirement has been
established for the verified ticket artwork.

The public archive audit/extraction interface is:

```powershell
python scripts/analysis/audit_ms1_asset_names.py --help
```

Supply `--ra-tool` for the reviewed external RA module, `--index` and one or more
`--elf` inputs. Selective extraction additionally needs `--dat`, `--cnk`,
`--extract` and an ignored `--out-dir`. The wrapper is not self-contained and
does not prove game-build compatibility from name hashes. Review duplicate hash
entries before accepting its first selection.

The validated version-3 RIB parser is currently private prototype tooling:
`temp/issue22-assets/parse_rib_v3.py`, with active-scene variants and inventories
in that same directory. It is not available from a fresh public clone. It checks
`EVOSBIG `, version `0x30000`, header marker `0x11111111`, resource records and
type/ID relationships, dependency totals, bounded names, end marker `0x99999999`
and exact EOF. Records retain ID, type, indexed size, flags, dependency IDs, name
and source name. Its asserted structure is not a validated parser for other
versions. The later-version [Nenkai template](https://github.com/Nenkai/010GameTemplates/blob/fadbd2d123011dc8edbea12097aa2bc378dd3b72/Evolution%20Studios/RPK_ResourcePack.bt)
was a type-name reference. Curating a reusable checked parser/exporter remains
future work; do not claim a complete asset extraction SDK.

## Established asset correlations

| Subject | Established correlation | Limit |
|---|---|---|
| Active race-ticket scene | `festival_scene.rib` root `000FD77BC5804123` depends on `festival_meshes.rib` artwork | Similarly named festival-ticket bundles are separate and did not identify this active screen. |
| Deep End diffuse | Resource `0005A486D144C3CC`, serialized PixelFormat10/BC2, 1024-square, payload offset43 and length1048576 | Its filename says DXT1; the header and bytes take precedence. Full payload equality with native RSX source is recorded in graphics research. |
| Deep End normal | Resource `0005E8D66BAFCF8C`, PixelFormat9/BC1, 1024-square | Residency does not establish correct material execution. |
| Primary selected-bike buffers | Complete 964576-byte vertex and 93926-byte index payloads matched readable native VRAM | Does not prove visible bike submission, selected LOD, completed material or animation. |
| Environment geometry | Resource `000317308816E69D`, stride32, 3862 vertices; metadata dependencies identify `3Dsky_vehicleselect` environment components | Large coordinates alone did not establish corrupted bike vertices or which individual mesh a draw used. |

The private texture/material evidence is under `temp/issue22-assets`, mesh and
resource correlation under `temp/issue24-draw`, and the current terrain sampler
investigation under `temp/issue-render-motion`. Run directories retain launch,
process/executable identity, acknowledged input, internal captures and final
status. Private directories are evidence locations, not dependencies needed to
build public tooling.

## Vertex-color material blending

Native run `20261014T132520.253865Z` retained FP `05B6DC81` and its vertex program
as private `terrain-pick.hlsl` and `terrain-vp.hlsl`, plus a separately qualified
live program-byte read. The vertex program forwards attribute3 to COLOR0. The
fragment program uses R to weight a material/detail blend involving texture1
and prior terms; B adjusts another material response. This is more than a final
color tint. Alpha is loaded but its eventual role is not yet established.

Frame46 binds detailed BC1 maps, including a 1024-square color map and 256-square
normal/detail maps. Sequential full-span guest reads and CPU previews confirm
these originals contain detail. The shader is shared across multiple draws;
the complete foreground hill mesh/color-span binding and isolated material replay
remain unverified. A race landscape must be checked independently for its shader,
color channels, normalization, UV generation and LOD selection. Do not replace
vertex colors with white/defaults or assume this material applies to every track.

## Sampling and host-view traps already observed

- Respect actual mip, cube, pitch and component layouts. The current D3D12 upload
  exposes one mip even when terrain guest descriptors specify9–12; mip-chain
  upload/filtering remains incomplete.
- Sampler capture in run `20261014T133222.152229Z` confirms terrain repeat S/T and
  linear min/mag requests. Existing unit0 point/clamp binding conflicts with that
  state. An authored decoder GPU reducer exercises this mismatch; backend integration
  and native proof are pending. This is not yet a verified hill fix.
- A geometry MRT written as RGBA8 is later requested as XY16F (`0x9F`/`0xBF`).
  Sampling its bytes as ordinary color caused a proven typed-view mismatch.
  Decode each half before interpolation/remap. The retained candidate improved
  hill solidity; flat terrain, motion defects and missing bike remain unresolved.
- Surface AA sample extents differ from logical image extents and pitch padding.
  Keep these quantities separate; do not infer dimensions from pitch alone.
- GPU exposure and guest-visible CPU reads must agree. Recognizable offline
  artwork did not guarantee nonblack runtime lighting/composition.

See the linked graphics research for exact hashes, draw states, regression scope
and limitations. Current issues [94](https://github.com/robbe1912/motorstorm-mv-recomp/issues/94),
[24](https://github.com/robbe1912/motorstorm-mv-recomp/issues/24) and
[13](https://github.com/robbe1912/motorstorm-mv-recomp/issues/13) remain open.

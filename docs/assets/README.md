# Asset extraction and reconstruction

This is the reusable method for recovering original textures, meshes and
materials from a game's containers and validating their use by a native runtime.
Keep game-specific layouts and observed bindings in a worked example:
[MotorStorm Monument Valley](MOTORSTORM.md). Rendering experiments and native
acceptance evidence remain in [graphics/audio research](../research/GRAPHICS_AUDIO.md).
Pending tooling and verification belong in [GitHub issues](https://github.com/robbe1912/motorstorm-mv-recomp/issues).

Extraction, residency, binding and correct rendering are separate claims. An
exported image or model proves neither that the runtime loaded it nor that the
game selected that material or LOD.

## Establish identity before decoding

Record the game/build/region, executable and archive hashes, parser revision,
archive entry, resource ID/type/name, offsets, lengths and dependency IDs. Give
each transformation its own output hash. Keep originals read-only and decoded
outputs under ignored `temp/`; never write replacements into the disc tree.
Follow the [repository boundary](../REPOSITORY.md) for source, captures and dumps.

A useful evidence chain is:

```text
archive entry -> resource descriptor/dependencies -> serialized payload
 -> loaded resource object -> guest MAIN/LOCAL span
 -> draw-time vertex/index/texture bindings -> converted GPU inputs
 -> material/shader outputs -> displayed frame
```

Admit each arrow separately using IDs, full-span byte comparisons or an observed
pointer/descriptor relationship. Names and partial byte matches are leads.
Record collisions, ambiguous package copies, unreadable regions and observer
quotas. Sequential reads are not an atomic snapshot of a live pipeline.

## Containers and dependency graphs

1. Identify the archive version, byte order, index records, compression blocks
   and chunk boundaries. Validate bounds before allocating or seeking.
2. Resolve name hashes as candidates; check duplicate hashes and entries before
   selecting a source. Validate decompressed lengths and checksums where present.
3. Parse resource records into a graph of stable IDs, types, sizes, names and
   dependency edges. Validate totals, record boundaries, terminators and EOF.
4. Trace the scene/resource the game actually requests. Similar scene names do
   not establish the active bundle. Observe request and completion separately.
5. Extract only the resources needed for the comparison; preserve container
   bytes alongside decoded metadata. A viewer export is a derived artifact.

The current [archive audit wrapper](../../scripts/analysis/audit_ms1_asset_names.py)
is game-specific and requires a separately supplied reviewed RA module. Its
read-only extraction rejects output path escapes, uses exclusive writes, checks
chunk decode lengths and prints output hashes. It selects the first matching
hash entry: inspect duplicates before treating the selection as definitive.
This is not a universal archive extractor. See the worked example for available
tools and private parser limitations.

## Textures

Recover format from the serialized header and draw state, not a filename suffix.
Record dimensions, mip count, faces/layers, pitch, tiling/swizzle, compression,
component order/remap, byte order and payload boundaries. Retain each mip/face's
offset and length; a contact sheet loses that structure.

Decode and verify in distinct stages:

- **Storage:** calculate padded/block extents and exact lengths. BC1/BC2/BC3 use
  4x4 blocks; endian conversion belongs to the specific format, not a blanket
  reversal of all console data. Linear pitch can differ from width times size.
- **Layout:** unswizzle where required. Cube faces may be separated by an entire
  mip pyramid. Do not advance faces by level-0 size alone.
- **Meaning:** distinguish diffuse/albedo, normal, masks, lookup tables and
  render targets using material/shader consumers. A purple image is a normal-map
  lead, not proof of its channel convention or coordinate space.
- **Sampling:** preserve component remap, S/T/R addressing, min/mag/mip filters,
  LOD bounds/bias, anisotropy and border behavior from the draw. Unit numbers do
  not imply font, terrain or any fixed sampler policy.
- **Views:** a target written as one format may later be sampled through another
  typed representation. Reconstruct the bits before filtering when required;
  ordinary color sampling of packed half floats is not a format conversion.

Compare full original payloads with readable guest spans, then compare actual
upload/conversion outputs and sampled results. A BMP capture can discard alpha,
clamp HDR or visualize absolute values: retain raw bytes and metadata when sign,
precision or packing matters. Record which conversion produced every preview.

Current shared contracts live in [texture layout](../../vendor/ps3recomp/libs/video/rsx_texture_layout.h),
[texture capture](../../vendor/ps3recomp/libs/video/rsx_texture_capture.h) and
[packed target sampling](../../vendor/ps3recomp/libs/video/rsx_texture_alias.h).
Their existing scope is not a guarantee of every guest format or sampler feature.

## Meshes, vertex streams and LODs

Recover index width/byte order, topology, restart markers, base vertex, draw
range, vertex count, stride and every attribute's offset/type/component count.
Record MAIN/LOCAL location and the address translation used. Keep resource IDs
and dependency links to the mesh, material and any LOD alternatives.

Decode position, normal/tangent basis, UV sets, color, weights and joint indices
independently. Apply quantization scale/bias only when established by the asset
descriptor or vertex program. Disabled arrays can use constant attributes;
substituting zero or white can silently change the material. Preserve signedness
and normalization, including packed and half-float components.

Validate indices against the addressed stream range, account for draw offsets,
and compare complete source payloads before blaming geometry translation. Large
positions can belong to sky/environment geometry. Equal bytes across two LOD
packages do not identify which package or LOD the game selected.

An OBJ preview can show basic geometry; it does not preserve the full material,
multiple UVs, vertex colors, skinning or engine LOD graph. Use an explicit
intermediate representation and retain original metadata before considering an
export such as glTF. No complete general mesh/material exporter is supplied here.

Use the production [vertex fetch](../../vendor/ps3recomp/libs/video/rsx_vertex_fetch.h)
and [vertex formats](../../vendor/ps3recomp/libs/video/rsx_vertex_formats.h) as
executable contracts when comparing a future decoder.

## Materials and vertex painting

A material is a binding graph and a program, not a list of texture filenames.
Associate mesh/submesh, shader identity, textures/units, samplers, constants,
vertex attributes, blend/alpha/depth/cull state and render-target exports at
the same draw. Guest shader addresses can be recycled; retain SET-time content
identity and distinguish it from a later live memory read.

Trace vertex color or mask channels through both programs. Establish whether
each controls tint, texture/detail or normal blending, roughness/specular terms,
alpha or another response. Do not assign conventional RGBA meanings by habit.
Follow texture coordinate generation too: a landscape can use world position
instead of an authored UV channel. Preserve interpolation and precision.

To validate vertex painting, bind the raw color stream and its type/normalization
to the actual shader input, then replay controlled channel values against the
real material path. Shader use proves channel influence; it does not prove the
artist's tool, the full mesh's painted values, or use by a different race shader.
The [MotorStorm example](MOTORSTORM.md#vertex-color-material-blending) records
the confirmed menu-terrain R/B channel use and outstanding checks.

## Reuse and a future Rust implementation

Keep container parsing, resource graph, texture layout/decoding, vertex fetch,
material semantics and host GPU upload as separate interfaces. Represent guest
EAs, archive offsets, resource IDs and host pointers with distinct types; never
serialize live host pointers as portable asset identifiers. Use explicit endian
reads, checked arithmetic/ranges and errors that retain source ID/offset.

A portable intermediate record should retain original payload hash/span,
format/layout metadata, decoded stream descriptors, mesh/submesh/LOD graph,
material-to-shader bindings, per-unit samplers and per-channel color roles with
an evidence status. Keep transforms and coordinate conventions explicit. Export
conversion choices must not overwrite the original representation.

Port one contract at a time and compare Rust output with the current C helpers
using authored fixtures: full bytes where exact, justified tolerances for numeric
results, malformed/truncated inputs, mips/cube faces, disabled attributes,
normalization and sampler/typed-view cases. Then repeat an owned native draw and
normal gameplay route. Isolated decoder equality is not native game acceptance.
Original assets and their derived payloads stay private; public fixtures are
authored data. The evidence ledger must survive an implementation-language change.

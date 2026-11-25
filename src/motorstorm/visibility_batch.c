#include "visibility_batch.h"
#include "spu_helpers.h"
#include <string.h>

// Debug US classification slice after the input DMA wait. The arithmetic
// order retains the original thresholds and ordered output lists. The caller
// owns DMA, interrupt handling, and entry to the original epilogue.

static uint32_t ls_word(const uint8_t* ls, unsigned address) {
    return (uint32_t)ls[address] << 24 | (uint32_t)ls[address + 1] << 16 |
           (uint32_t)ls[address + 2] << 8 | ls[address + 3];
}

static void store_ls_word(uint8_t* ls, unsigned address, uint32_t word) {
    for (unsigned i = 0; i < 4; ++i)
        ls[address + i] = (uint8_t)(word >> (24 - 8 * i));
}

static uint32_t scaled_radius(uint32_t radius, const uint32_t axis[3]) {
    const uint32_t xy = spu_sf_madd(axis[1], axis[1], spu_sf_mul(axis[0], axis[0]), 0);
    const uint32_t squared_length = spu_sf_madd(axis[2], axis[2], xy, 0);
    const u128 length_bits = spu_splat_u32(squared_length);
    const uint32_t reciprocal = spu_fi(length_bits, spu_frsqest(length_bits))._u32[0];
    const uint32_t estimate = spu_sf_mul(reciprocal, squared_length);
    const uint32_t correction = spu_sf_madd(reciprocal, estimate, 0x3f800001, 0x80000000);
    const uint32_t scale = spu_sf_madd(correction, spu_sf_mul(estimate, 0x3f000000), estimate, 0);
    return spu_sf_mul(radius, scale);
}

typedef uint32_t VisibilityScalar;
typedef u128 VisibilityVector;
typedef struct { VisibilityVector columns[4]; } VisibilityMatrix;
typedef struct {
    VisibilityVector center;
    VisibilityScalar world_radius;
    VisibilityScalar object_radius;
} VisibilitySphere;

enum {
    pvs_flush_index = 0x167c0, pvs_output_tag = 0x167d0, pvs_output_destination = 0x16854,
    pvs_primary_count = 0x16870, pvs_stats_pointer = 0x16880,
    pvs_secondary_pointer = 0x16890, pvs_auxiliary_pointer = 0x168a0,
    pvs_primary_pointer = 0x168b0, pvs_lod_mode = 0x168c0,
    pvs_screen_weight = 0x16900, pvs_size_enabled = 0x16910,
    pvs_frustum_enabled = 0x16920, pvs_occlusion_enabled = 0x16930,
    pvs_lod_plane = 0x16940, pvs_projection_scale = 0x16950,
    pvs_frustum_planes = 0x169a0, pvs_depth_plane = 0x169f0,
    pvs_secondary_limit = 0x16a00, pvs_size_limit = 0x16a10,
    pvs_depth_enabled = 0x16a20,
    pvs_records = 0x16b30, pvs_boxes = 0x16b40,
    pvs_spheres = 0x16b50, pvs_matrices = 0x16b60,
    pvs_special_count = 0x16bb0, pvs_special_list = 0x16bc0,
    pvs_secondary_count = 0x17bc0, pvs_auxiliary_count = 0x17bd0,
    pvs_secondary_depth = 0x17be0, pvs_auxiliary_depth = 0x19be0,
    pvs_occluders = 0x1bbe0, pvs_occluder_count = 0x266e0,
    pvs_occluder_indices = 0x266f0, pvs_object_base = 0x27000,
    pvs_unit = 0x3f800000, pvs_refinement = 0x3f800001
};

static VisibilityScalar vis_fma(VisibilityScalar a, VisibilityScalar b, VisibilityScalar c) {
    return spu_sf_madd(a, b, c, 0);
}

static VisibilityScalar vis_negate(VisibilityScalar x) {
    return x ^ UINT32_C(0x80000000);
}

static VisibilityScalar vis_sub(VisibilityScalar a, VisibilityScalar b) {
    return spu_sf_add(a, vis_negate(b));
}

static VisibilityScalar vis_residual(VisibilityScalar a, VisibilityScalar b, VisibilityScalar c) {
    return spu_sf_madd(a, b, c, UINT32_C(0x80000000));
}

static int vis_greater(VisibilityScalar a, VisibilityScalar b) {
    u128 x = spu_splat_u32(a), y = spu_splat_u32(b);
    return x._f32[0] > y._f32[0];
}

static VisibilityVector vis_vector(const uint8_t* data, unsigned offset) {
    VisibilityVector value;
    for (unsigned i = 0; i < 4; ++i) value._u32[i] = ls_word(data, offset + i * 4);
    return value;
}

static VisibilityMatrix vis_matrix(const uint8_t* data, unsigned offset) {
    VisibilityMatrix matrix;
    for (unsigned i = 0; i < 4; ++i) matrix.columns[i] = vis_vector(data, offset + 16 * i);
    return matrix;
}

static VisibilityScalar vis_dot(VisibilityVector a, VisibilityVector b) {
    const VisibilityScalar xy =
        vis_fma(a._u32[1], b._u32[1], spu_sf_mul(a._u32[0], b._u32[0]));
    return vis_fma(a._u32[2], b._u32[2], xy);
}

static VisibilityScalar vis_distance(VisibilityVector plane, VisibilityVector center) {
    return spu_sf_add(vis_dot(plane, center), plane._u32[3]);
}

static VisibilityVector vis_transform(const VisibilityMatrix* matrix, VisibilityVector point) {
    const VisibilityVector x = spu_splat_u32(point._u32[0]), y = spu_splat_u32(point._u32[1]);
    const VisibilityVector z = spu_splat_u32(point._u32[2]), w = spu_splat_u32(point._u32[3]);
    const VisibilityVector* c = matrix->columns;
    return spu_fa(spu_fma(c[2], z, spu_fm(c[0], x)), spu_fma(c[3], w, spu_fm(c[1], y)));
}

static VisibilityScalar vis_inverse(VisibilityScalar value) {
    const VisibilityVector operand = spu_splat_u32(value);
    return spu_fi(operand, spu_frest(operand))._u32[0];
}

static VisibilityScalar vis_length(VisibilityVector axis) {
    return scaled_radius(pvs_unit, axis._u32);
}

static VisibilitySphere vis_sphere(const VisibilityMatrix* matrix, VisibilityVector sphere,
                                   VisibilityScalar object_radius) {
    const VisibilityScalar scale = vis_length(matrix->columns[2]);
    const VisibilityScalar world_radius = spu_sf_mul(sphere._u32[3], scale);
    sphere._u32[3] = pvs_unit;
    return (VisibilitySphere){vis_transform(matrix, sphere), world_radius,
                              spu_sf_mul(object_radius, scale)};
}

static unsigned vis_lod(const uint8_t* ls, VisibilitySphere sphere, unsigned kind) {
    const unsigned mode = ls_word(ls, pvs_lod_mode);
    if (mode) return mode < 17 ? 1u << (mode + 15) : 0;
    const VisibilityScalar depth = vis_distance(vis_vector(ls, pvs_lod_plane), sphere.center);
    if (!vis_greater(depth, 0)) return 0x10000;
    const VisibilityScalar inverse = vis_inverse(depth);
    const VisibilityScalar estimated = spu_sf_mul(sphere.object_radius, inverse);
    const VisibilityScalar scaled = vis_fma(vis_residual(estimated, depth, sphere.object_radius),
                                              inverse, estimated);
    const VisibilityScalar size = spu_sf_mul(
        spu_sf_mul(scaled, ls_word(ls, pvs_projection_scale)), 0x44870000);
    if (vis_greater(size, ls_word(ls, 0x165f0 + 4 * kind))) return 0x10000;
    return vis_greater(size, ls_word(ls, 0x165c0 + 4 * kind)) ? 0x20000 : 0x40000;
}

/* Project the two endpoints of a sphere diameter into screen space. */
static VisibilityVector vis_project(const VisibilityMatrix* projection, VisibilityVector center,
                                    VisibilityVector axis, VisibilityScalar radius) {
    VisibilityVector endpoint = spu_fma(axis, spu_splat_u32(radius), center);
    endpoint._u32[3] = pvs_unit;
    endpoint = vis_transform(projection, endpoint);
    const VisibilityScalar w = endpoint._u32[3], inverse = vis_inverse(w);
    endpoint = spu_fm(endpoint, spu_splat_u32(inverse));
    endpoint = spu_fma(endpoint, spu_splat_u32(vis_residual(w, inverse, pvs_refinement)), endpoint);
    endpoint._u32[2] = 0;
    return endpoint;
}

static int vis_projected_size_reject(const uint8_t* ls, VisibilitySphere sphere,
                                     VisibilityScalar weight) {
    const VisibilityMatrix view = vis_matrix(ls, 0x16ab0);
    const VisibilityMatrix projection = vis_matrix(ls, 0x16a70);
    sphere.center._u32[3] = pvs_unit;
    const VisibilityVector center = vis_transform(&view, sphere.center);
    const VisibilityVector a = vis_project(&projection, center, vis_vector(ls, 0x164a0), sphere.world_radius);
    const VisibilityVector b = vis_project(&projection, center, vis_vector(ls, 0x16490), sphere.world_radius);
    const VisibilityVector diameter = spu_fs(a, b);
    const VisibilityScalar limit = spu_sf_mul(weight, ls_word(ls, pvs_screen_weight));
    return vis_greater(spu_sf_mul(limit, limit), vis_dot(diameter, diameter));
}

static int vis_size_reject(const uint8_t* ls, VisibilitySphere sphere, unsigned kind,
                           VisibilityScalar weight, uint32_t* depth, int* omit_secondary) {
    if (!ls[pvs_size_enabled]) return 0;
    if (!ls[pvs_depth_enabled]) return vis_projected_size_reject(ls, sphere, weight);

    *depth = vis_distance(vis_vector(ls, pvs_depth_plane), sphere.center);
    const VisibilityScalar inverse = vis_inverse(*depth);
    const VisibilityScalar estimate = spu_sf_mul(pvs_unit, inverse);
    const VisibilityScalar refined = vis_fma(vis_residual(estimate, *depth, pvs_unit), inverse, estimate);
    const VisibilityScalar size = spu_sf_mul(
        spu_sf_mul(spu_sf_mul(sphere.object_radius, refined), ls_word(ls, pvs_projection_scale)),
        0x44870000);
    const VisibilityScalar limit = ls_word(ls, 0x16500 + 4 * kind);
    if (vis_greater(*depth, 0)) {
        const VisibilityScalar relative_radius = spu_sf_mul(sphere.world_radius, refined);
        *omit_secondary = vis_greater(limit, size) ||
                          vis_greater(ls_word(ls, pvs_secondary_limit), relative_radius);
        return vis_greater(spu_sf_mul(weight, ls_word(ls, pvs_size_limit)), relative_radius);
    }
    const int reject = !vis_greater(*depth, vis_negate(sphere.world_radius));
    *omit_secondary = reject || vis_greater(limit, vis_negate(size));
    return reject;
}

static int vis_frustum_sphere_reject(const uint8_t* ls, VisibilitySphere sphere) {
    const VisibilityVector origin = vis_vector(ls, 0x16960), axis = vis_vector(ls, 0x16970);
    const VisibilityVector cone = vis_vector(ls, 0x16980);
    const VisibilityScalar radius = sphere.world_radius;
    const VisibilityScalar cap = spu_sf_mul(radius, ls_word(ls, 0x16990));
    const VisibilityVector expanded_origin = spu_fnms(axis, spu_splat_u32(cap), origin);
    VisibilityVector offset = spu_fs(sphere.center, expanded_origin);
    VisibilityScalar projection = vis_dot(axis, offset);
    const VisibilityScalar opening = spu_sf_mul(cone._u32[2], cone._u32[2]);
    if (!vis_greater(projection, 0) ||
        vis_greater(spu_sf_mul(opening, vis_dot(offset, offset)), spu_sf_mul(projection, projection)))
        return 1;

    offset = spu_fs(sphere.center, origin);
    projection = vis_negate(vis_dot(axis, offset));
    const VisibilityScalar back_opening = spu_sf_mul(cone._u32[3], cone._u32[3]);
    const VisibilityScalar distance_squared = vis_dot(offset, offset);
    if (vis_greater(projection, 0) &&
        !vis_greater(spu_sf_mul(back_opening, distance_squared), spu_sf_mul(projection, projection)) &&
        vis_greater(distance_squared, spu_sf_mul(radius, radius)))
        return 1;

    for (unsigned i = 0; i < 5; ++i) {
        const VisibilityScalar distance = vis_distance(vis_vector(ls, pvs_frustum_planes + 16 * i),
                                                       sphere.center);
        if (!vis_greater(0, vis_sub(distance, radius))) return 1;
    }
    return 0;
}

typedef struct {
    const VisibilityMatrix* matrix;
    const uint8_t* ls;
    unsigned address;
    int ready;
    VisibilityVector corners[8];
} VisibilityBoxCache;

static void vis_make_corners(VisibilityBoxCache* box) {
    if (box->ready) return;
    VisibilityMatrix local = vis_matrix(box->ls, box->address);
    local.columns[0]._u32[3] = pvs_unit;
    const VisibilityVector center = vis_transform(box->matrix, local.columns[0]);
    VisibilityVector extent[3];
    for (unsigned i = 0; i < 3; ++i) {
        VisibilityVector axis = local.columns[i + 1];
        axis = spu_fm(axis, spu_splat_u32(axis._u32[3]));
        axis._u32[3] = 0;
        const VisibilityVector direction = vis_transform(box->matrix, axis);
        const VisibilityScalar length = vis_length(direction), inverse = vis_inverse(length);
        const VisibilityScalar error = vis_residual(length, inverse, pvs_refinement);
        const VisibilityVector unit = spu_fm(direction, spu_splat_u32(inverse));
        extent[i] = spu_fm(spu_fma(unit, spu_splat_u32(error), unit), spu_splat_u32(length));
    }
    const VisibilityVector lower = spu_fs(center, extent[0]), upper = spu_fa(center, extent[0]);
    const VisibilityVector diagonal = spu_fa(extent[1], extent[2]);
    const VisibilityVector difference = spu_fs(extent[2], extent[1]);
    box->corners[0] = spu_fa(upper, diagonal);
    box->corners[1] = spu_fa(lower, diagonal);
    box->corners[2] = spu_fa(upper, difference);
    box->corners[3] = spu_fa(lower, difference);
    box->corners[4] = spu_fs(upper, difference);
    box->corners[5] = spu_fs(lower, difference);
    box->corners[6] = spu_fs(upper, diagonal);
    box->corners[7] = spu_fs(lower, diagonal);
    box->ready = 1;
}

static int vis_frustum_box_reject(VisibilityBoxCache* box) {
    vis_make_corners(box);
    for (unsigned i = 0; i < 5; ++i) {
        const VisibilityVector plane = vis_vector(box->ls, pvs_frustum_planes + 16 * i);
        unsigned outside = 0;
        for (unsigned j = 0; j < 8; ++j) outside += vis_greater(vis_distance(plane, box->corners[j]), 0);
        if (outside == 8) return 1;
    }
    return 0;
}

static int vis_occluded(const uint8_t* ls, VisibilitySphere sphere, VisibilityBoxCache* box) {
    const unsigned count = ls_word(ls, pvs_occluder_count);
    for (unsigned i = 0; i < count; ++i) {
        const unsigned index = ls_word(ls, pvs_occluder_indices + 4 * i);
        const unsigned planes = pvs_occluders + 304 * index;
        const unsigned plane_count = ls_word(ls, planes + 288);
        unsigned j = 0;
        for (; j < plane_count; ++j) {
            const VisibilityScalar distance = vis_distance(vis_vector(ls, planes + 16 * j), sphere.center);
            if (vis_greater(0, vis_sub(distance, sphere.world_radius))) break;
        }
        if (j == plane_count) return 1;
        vis_make_corners(box);
        for (j = 0; j < plane_count; ++j) {
            const VisibilityVector plane = vis_vector(ls, planes + 16 * j);
            unsigned corner = 0;
            while (corner < 8 && !vis_greater(0, vis_distance(plane, box->corners[corner]))) ++corner;
            if (corner < 8) break;
        }
        if (j == plane_count) return 1;
    }
    return 0;
}

typedef struct { unsigned address, size; } VisibilityRange;
static int vis_disjoint(VisibilityRange a, VisibilityRange b) {
    return !a.size || !b.size || a.address + a.size <= b.address || b.address + b.size <= a.address;
}

static int vis_validate(const uint8_t* ls, unsigned count, const VisibilityRange* ranges,
                        unsigned length) {
    for (unsigned i = 0; i < length; ++i) {
        VisibilityRange current = ranges[i];
        if (!current.size) continue;
        if ((current.address & 15) || current.address < 0x28930 ||
            current.address > 0x3b000 || current.size > 0x3b000 - current.address) return 0;
        for (unsigned j = 0; j < i; ++j)
            if (!vis_disjoint(current, ranges[j])) return 0;
    }
    const unsigned primary_count = ls_word(ls, pvs_primary_count);
    const unsigned secondary_count = ls_word(ls, pvs_secondary_count);
    const unsigned special_count = ls_word(ls, pvs_special_count);
    const unsigned occluder_count = ls_word(ls, pvs_occluder_count);
    if (primary_count >= 4096 ||
        secondary_count > 2048 || count > 2048 - secondary_count ||
        ls_word(ls, pvs_auxiliary_count) > 2048 ||
        special_count > 1024 || count > 1024 - special_count || occluder_count > 64) return 0;
    for (unsigned i = 0; i < count; ++i)
        if ((ls_word(ls, ranges[0].address + i * 20 + 8) & 0xffff) > 11) return 0;
    for (unsigned i = 0; i < occluder_count; ++i) {
        const unsigned index = ls_word(ls, pvs_occluder_indices + 4 * i);
        if (index >= 144 || ls_word(ls, pvs_occluders + index * 304 + 288) > 18) return 0;
    }
    return 1;
}

static unsigned vis_append(uint8_t* ls, unsigned counter, unsigned list, unsigned id) {
    const unsigned index = ls_word(ls, counter);
    for (unsigned lane = 0; lane < 16; lane += 4)
        store_ls_word(ls, counter + lane, ls_word(ls, counter + lane) + 1);
    store_ls_word(ls, list + index * 4, id);
    return index;
}

static void vis_stat(uint8_t* ls, unsigned address) {
    store_ls_word(ls, address, ls_word(ls, address) + 1);
}

static int vis_layout(const uint8_t* ls, unsigned count, int can_publish, VisibilityRange ranges[8]) {
    if (count > 256) return 0;
    const unsigned secondary = ls_word(ls, pvs_secondary_pointer);
    const unsigned auxiliary = ls_word(ls, pvs_auxiliary_pointer);
    const VisibilityRange spans[] = {
        {ls_word(ls, pvs_records), (20 * count + 15) & ~15u},
        {ls_word(ls, pvs_matrices), 64 * count},
        {ls_word(ls, pvs_spheres), 16 * count},
        {ls_word(ls, pvs_boxes), 64 * count},
        {ls_word(ls, pvs_stats_pointer), 32}, {ls_word(ls, pvs_primary_pointer), 16384},
        {secondary, secondary ? 8192 : 0},
        {auxiliary, auxiliary ? 8192 : 0}
    };
    if (!vis_validate(ls, count, spans, sizeof(spans) / sizeof(*spans))) return 0;
    if (count >= 4096 - ls_word(ls, pvs_primary_count) &&
        (!can_publish || (ls_word(ls, pvs_output_destination) & 15))) return 0;
    memcpy(ranges, spans, sizeof(spans));
    return 1;
}

int motorstorm_us_visibility_nonflushing(const uint8_t* ls, unsigned count) {
    VisibilityRange ranges[8];
    return count && vis_layout(ls, count, 0, ranges);
}

int motorstorm_us_visibility_classify(uint8_t* ls, unsigned count, uint32_t output_high,
                                     MotorstormVisibilityPublish publish, void* publication) {
    if (!count) return 1;
    VisibilityRange ranges[8];
    if (!vis_layout(ls, count, publish != NULL, ranges)) return 0;
    const unsigned stats = ranges[4].address, primary = ranges[5].address;
    const unsigned secondary = ranges[6].address, auxiliary = ranges[7].address;

    VisibilityScalar depth = 0;
    int omit_secondary = 0;
    for (unsigned i = 0; i < count; ++i) {
        const unsigned address = ranges[0].address + 20 * i;
        const unsigned flags = ls_word(ls, address + 12);
        if (!(flags & 1)) continue;
        const unsigned type = ls_word(ls, address + 8), kind = type & 0xffff;
        const VisibilityMatrix matrix = vis_matrix(ls, ranges[1].address + 64 * i);
        const VisibilitySphere sphere = vis_sphere(&matrix, vis_vector(ls, ranges[2].address + 16 * i),
                                                   ls_word(ls, address));
        store_ls_word(ls, address, sphere.object_radius);
        if (!(type & vis_lod(ls, sphere, kind)) ||
            vis_size_reject(ls, sphere, kind, ls_word(ls, address + 4), &depth, &omit_secondary)) {
            vis_stat(ls, stats + 8);
            continue;
        }
        VisibilityBoxCache box = {.matrix = &matrix, .ls = ls, .address = ranges[3].address + 64 * i};
        if (ls[pvs_frustum_enabled] &&
            (vis_frustum_sphere_reject(ls, sphere) || vis_frustum_box_reject(&box))) {
            vis_stat(ls, stats + 4);
            continue;
        }
        if (ls[pvs_occlusion_enabled] && vis_occluded(ls, sphere, &box)) {
            vis_stat(ls, stats);
            continue;
        }
        vis_stat(ls, stats + 12);
        const unsigned id = ls_word(ls, pvs_object_base) + i;
        if (auxiliary && flags >> 1) {
            if (ls_word(ls, pvs_auxiliary_count) < 2048) {
                const unsigned index = vis_append(ls, pvs_auxiliary_count, auxiliary, id);
                store_ls_word(ls, pvs_auxiliary_depth + 4 * index, depth);
            }
            if ((flags >> 1) == 2) vis_append(ls, pvs_special_count, pvs_special_list, id);
        } else {
            vis_append(ls, pvs_primary_count, primary, id);
            vis_stat(ls, stats + 16);
        }
        if (secondary && !omit_secondary) {
            const unsigned index = vis_append(ls, pvs_secondary_count, secondary, id);
            store_ls_word(ls, pvs_secondary_depth + 4 * index, depth);
        }
        if (ls_word(ls, pvs_primary_count) == 4096) {
            const uint32_t index = ls_word(ls, pvs_flush_index);
            const MotorstormVisibilityFlush flush = {
                primary, output_high, ls_word(ls, pvs_output_destination) + (index << 14),
                ls_word(ls, pvs_output_tag) & 31, ls + primary
            };
            publish(&flush, publication);
            memset(ls + pvs_primary_count, 0, 16);
            for (unsigned lane = 0; lane < 16; lane += 4)
                vis_stat(ls, pvs_flush_index + lane);
        }
    }
    return 1;
}


static int occluder_input(unsigned address, unsigned bytes, unsigned temporary) {
    return address >= 0x27010 && !(address & 15) && address <= 0x40000 &&
           bytes <= 0x40000 - address &&
           (address >= temporary + 16 || address + bytes <= temporary);
}

int motorstorm_us_visibility_occluder_supported(const uint8_t* ls, unsigned index,
                                               unsigned temporary_normal) {
    if (!ls || index >= 144 || (temporary_normal & 15) || temporary_normal < 0x27010 ||
        temporary_normal > 0x40000 - 16 || ls_word(ls, 0x166c0) != pvs_occluders ||
        index >= ls_word(ls, 0x166b0)) return 0;
    const unsigned records = ls_word(ls, 0x166a0);
    if (!occluder_input(records, (index + 1) * 28, temporary_normal)) return 0;
    const unsigned record = records + index * 28;
    const unsigned faces = ls_word(ls, record), edges = ls_word(ls, record + 4);
    const unsigned vertices = ls_word(ls, record + 8);
    // Eighteen planes fit before the existing output record's metadata.
    // Retain larger edge lists in the original implementation.
    if (faces > 15 || edges > 17 || vertices > 0x40000 / 16) return 0;
    const unsigned face_edges = ls_word(ls, 0x16710), edge_vertices = ls_word(ls, 0x16700);
    if (!occluder_input(face_edges, faces * 12, temporary_normal) ||
        !occluder_input(edge_vertices, edges * 8, temporary_normal) ||
        !occluder_input(ls_word(ls, 0x166f0), faces * 16, temporary_normal) ||
        !occluder_input(ls_word(ls, 0x166e0), vertices * 16, temporary_normal)) return 0;
    for (unsigned edge = 0; edge < edges; ++edge)
        if (ls_word(ls, edge_vertices + edge * 8) >= vertices ||
            ls_word(ls, edge_vertices + edge * 8 + 4) >= vertices) return 0;
    for (unsigned face = 0; face < faces; ++face)
        for (unsigned corner = 0; corner < 3; ++corner)
            if (ls_word(ls, face_edges + face * 12 + corner * 4) >= edges) return 0;
    return 1;
}

static void vis_store_vector(uint8_t* ls, unsigned address, VisibilityVector value) {
    for (unsigned lane = 0; lane < 4; ++lane)
        store_ls_word(ls, address + lane * 4, value._u32[lane]);
}

static VisibilityVector occluder_unit(VisibilityVector normal) {
    const VisibilityVector length = spu_splat_u32(vis_dot(normal, normal));
    const VisibilityVector inverse = spu_fi(length, spu_frsqest(length));
    const VisibilityVector half = spu_fm(inverse, spu_splat_u32(0x3f000000));
    const VisibilityVector residual = spu_fnms(inverse, spu_fm(inverse, length),
                                              spu_splat_u32(pvs_refinement));
    const VisibilityVector scale = spu_fma(residual, half, inverse);
    const uint32_t fourth = normal._u32[3];
    normal = spu_fm(normal, scale);
    normal._u32[3] = fourth;
    return normal;
}

static VisibilityVector occluder_plane(VisibilityVector normal, VisibilityVector point) {
    normal._u32[3] = vis_negate(vis_dot(normal, point));
    return normal;
}

int motorstorm_us_visibility_occluder(uint8_t* ls, unsigned index,
                                     unsigned temporary_normal) {
    if (!motorstorm_us_visibility_occluder_supported(ls, index, temporary_normal)) return 0;
    const unsigned record = ls_word(ls, 0x166a0) + index * 28;
    const unsigned face_count = ls_word(ls, record), edge_count = ls_word(ls, record + 4);
    const unsigned face_edges = ls_word(ls, 0x16710), edges = ls_word(ls, 0x16700);
    const unsigned vertices = ls_word(ls, 0x166e0), normals = ls_word(ls, 0x166f0);
    const VisibilityVector origin = vis_vector(ls, 0x16680);
    VisibilityVector accumulated = spu_splat_u32(0), planes[18], last_edge_normal;
    VisibilityVector farthest = vis_vector(ls, 0x16730);
    VisibilityScalar orientation = pvs_unit, farthest_squared = 0;
    uint8_t enabled[32] = {0};
    const VisibilityVector sentinel = spu_and(vis_vector(ls, 0x16750), spu_fsmbi(1));
    vis_store_vector(enabled, 16, sentinel);
    unsigned plane_count = 0, edge_planes = 0;
    // Shared triangle edges cancel, leaving the polygon boundary. Preserve
    // the original face order, orientation selection and fused accumulation.
    for (unsigned face = 0; face < face_count; ++face) {
        const VisibilityVector normal = vis_vector(ls, normals + face * 16);
        const unsigned first_edge = ls_word(ls, face_edges + face * 12);
        const unsigned vertex = ls_word(ls, edges + first_edge * 8);
        const VisibilityVector relative = spu_fs(vis_vector(ls, vertices + vertex * 16), origin);
        if (vis_greater(0, vis_dot(relative, normal))) orientation = 0xbf800000;
        accumulated = spu_fma(normal, spu_splat_u32(orientation), accumulated);
        for (unsigned corner = 0; corner < 3; ++corner)
            enabled[ls_word(ls, face_edges + face * 12 + corner * 4)] ^= 1;
    }
    for (unsigned edge = 0; edge < edge_count; ++edge) {
        if (!enabled[edge]) continue;
        const unsigned first = ls_word(ls, edges + edge * 8);
        const unsigned second = ls_word(ls, edges + edge * 8 + 4);
        const VisibilityVector point_a = vis_vector(ls, vertices + first * 16);
        const VisibilityVector point_b = vis_vector(ls, vertices + second * 16);
        const VisibilityVector a = spu_fs(point_a, origin), b = spu_fs(point_b, origin);
        VisibilityVector cross = spu_splat_u32(0);
        for (unsigned lane = 0; lane < 3; ++lane) {
            const unsigned y = (lane + 1) % 3, z = (lane + 2) % 3;
            cross._u32[lane] = vis_residual(a._u32[z], b._u32[y],
                                           spu_sf_mul(a._u32[y], b._u32[z]));
        }
        cross = spu_fm(cross, spu_splat_u32(orientation));
        last_edge_normal = occluder_unit(cross);
        planes[plane_count++] = occluder_plane(last_edge_normal, origin);
        ++edge_planes;
        const VisibilityScalar length_a = vis_dot(a, a), length_b = vis_dot(b, b);
        const int choose_a = vis_greater(length_a, length_b);
        const VisibilityScalar length = choose_a ? length_a : length_b;
        if (vis_greater(length, farthest_squared)) {
            farthest_squared = length;
            farthest = choose_a ? point_a : point_b;
        }
    }
    const VisibilityVector normal = occluder_unit(accumulated);
    planes[plane_count++] = occluder_plane(normal, farthest);
    // All inputs have been validated and consumed before the first write.
    const unsigned output = pvs_occluders + index * 304;
    for (unsigned plane = 0; plane < plane_count; ++plane)
        vis_store_vector(ls, output + plane * 16, planes[plane]);
    store_ls_word(ls, output + 0x120, plane_count);
    vis_store_vector(ls, 0x16580, spu_splat_u32(orientation));
    vis_store_vector(ls, 0x16720, normal);
    if (edge_planes) {
        vis_store_vector(ls, 0x16730, farthest);
        vis_store_vector(ls, temporary_normal, last_edge_normal);
    }
    memcpy(ls + 0x16740, enabled, sizeof(enabled));
    vis_store_vector(ls, 0x16760, spu_splat_u32(plane_count));
    vis_store_vector(ls, 0x16770, spu_splat_u32(face_count));
    for (unsigned face = 0; face < face_count; ++face)
        store_ls_word(ls, 0x16780 + face * 4, face);
    return 1;
}

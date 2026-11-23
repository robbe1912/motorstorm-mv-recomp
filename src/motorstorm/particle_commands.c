#include "particle_commands.h"
#include "spu_helpers.h"
#include <string.h>

typedef u128 Vector;

enum { STORE_SIZE = 0x40000, SLOT_WRITE_BYTES = 112, SLOT_BYTES = 96, RECORD_BYTES = 128 };
enum { OPERATOR_COLLISION = 5, OPERATOR_SLOT = 8 };

static uint32_t word(const uint8_t* ls, uint32_t at) {
    return (uint32_t)ls[at] << 24 | (uint32_t)ls[at + 1] << 16 |
           (uint32_t)ls[at + 2] << 8 | ls[at + 3];
}
static void put_word(uint8_t* ls, uint32_t at, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) ls[at + i] = (uint8_t)(value >> (24 - i * 8));
}
static int inside(uint32_t at, uint32_t size) {
    return at <= STORE_SIZE && size <= STORE_SIZE - at;
}
static int overlaps(uint32_t a, uint32_t as, uint32_t b, uint32_t bs) {
    return as && bs && a < b + bs && b < a + as;
}
static Vector load(const uint8_t* ls, uint32_t at) {
    Vector result;
    for (unsigned i = 0; i < 4; ++i) result._u32[i] = word(ls, at + 4 * i);
    return result;
}
static MotorstormCollisionVector collision_vector(Vector value) {
    MotorstormCollisionVector result;
    memcpy(result.component, value._u32, sizeof(result));
    return result;
}
static Vector pattern(uint32_t a, uint32_t b, uint32_t c, uint32_t d) {
    Vector result;
    result._u32[0] = a; result._u32[1] = b; result._u32[2] = c; result._u32[3] = d;
    return result;
}

// Operator 8 copies 96 payload bytes into one emitter slot of the header.
static int write_slot(uint8_t* ls, uint32_t header, uint32_t data) {
    const uint32_t index = word(ls, data + 4);
    if ((data & 15) || index >= MOTORSTORM_COMMAND_SLOT_COUNT) return 0;
    const uint32_t target = header + 704 + SLOT_BYTES * index;
    if (!inside(data, SLOT_WRITE_BYTES) || overlaps(data, SLOT_WRITE_BYTES, target, SLOT_BYTES)) return 0;
    memcpy(ls + target, ls + data + 16, SLOT_BYTES);
    return 1;
}

typedef struct {
    uint32_t count, records, events, used, capacity;
    int remove;
} CollisionState;

// World-to-box columns of a collision shape. The shape holds a 3x3 frame in
// three rows at 16, 32 and 48 and a scale vector at 64. The rows become the
// columns; the origin is the scaled combination of the three rows.
static void collision_box(const uint8_t* ls, uint32_t header, uint32_t shape, MotorstormCollisionBox* box) {
    const Vector a = load(ls, shape + 16), b = load(ls, shape + 32), c = load(ls, shape + 48);
    const Vector scale = spu_xor(load(ls, shape + 64), spu_splat_u32(0x80000000u));
    // Shuffle controls: (a0,c0,a1,c1), (a2,c2,a3,c3), (a2,c2,a3,zero), (a0,a1,a2,zero).
    const Vector first = pattern(0x00010203u, 0x10111213u, 0x04050607u, 0x14151617u);
    const Vector second = pattern(0x08090a0bu, 0x18191a1bu, 0x0c0d0e0fu, 0x1c1d1e1fu);
    const Vector tail = pattern(0x08090a0bu, 0x14151617u, 0x0c0d0e0fu, 0x80808080u);
    const Vector keep = pattern(0x00010203u, 0x04050607u, 0x08090a0bu, 0x10111213u);
    const Vector zero = spu_splat_u32(0), one = spu_splat_u32(0x3f800000u);
    const Vector leading = spu_shufb(a, c, first);
    const Vector row0 = spu_shufb(leading, b, first), row1 = spu_shufb(leading, b, tail);
    const Vector row2 = spu_shufb(spu_shufb(a, c, second), b, tail);
    const Vector partial = spu_fma(row1, spu_shufb(scale, scale, spu_splat_u32(0x04050607u)),
                                   spu_fm(row0, spu_shufb(scale, scale, spu_splat_u32(0x00010203u))));
    const Vector origin = spu_fma(row2, spu_shufb(scale, scale, spu_splat_u32(0x08090a0bu)), partial);
    const Vector columns[4] = {spu_shufb(row0, zero, keep), spu_shufb(row1, zero, keep),
                               spu_shufb(row2, zero, keep), spu_shufb(origin, one, keep)};
    memset(box, 0, sizeof(*box));
    for (unsigned i = 0; i < 4; ++i)
        box->columns[i] = collision_vector(columns[i]);
    for (unsigned i = 0; i < 4; ++i) {
        box->half_extent.component[i] = word(ls, shape + 80 + 4 * i);
        box->motion.component[i] = word(ls, shape + 96 + 4 * i);
    }
    box->step = word(ls, header + 1780);
    box->contact_metadata = word(ls, shape + 112);
}

// Checks the bounds of operator 5 and loads its typed batch.
static int collision_inputs(const uint8_t* ls, uint32_t header, uint32_t shape, uint32_t stack,
                            CollisionState* state, MotorstormCollisionBox* box,
                            MotorstormCollisionParticle* particles) {
    const uint32_t count = word(ls, header + 8), records = word(ls, header + 4);
    const uint32_t used = word(ls, header + MOTORSTORM_COMMAND_EVENTS);
    const uint32_t capacity = word(ls, header + MOTORSTORM_COMMAND_EVENTS + 4);
    const uint32_t events = word(ls, header + MOTORSTORM_COMMAND_EVENTS + 8);
    const uint32_t frame = stack - 400;
    if (!count || count > MOTORSTORM_COLLISION_PARTICLES || (shape & 15) || (records & 15) ||
        (events & 15) || (stack & 15) || frame < 0x3b000 ||
        !inside(frame, 432) || !inside(shape, 128) || !inside(records, count * RECORD_BYTES) ||
        word(ls, header + 12) < count || used > capacity || capacity > 0x4000 ||
        (capacity && !inside(events, capacity * 16)))
        return 0;
    const uint32_t ranges[][2] = {{header, 1784}, {shape, 128}, {frame, 432},
                                  {records, count * RECORD_BYTES}, {events, capacity * 16}};
    for (unsigned i = 0; i < 5; ++i)
        for (unsigned j = 0; j < i; ++j)
            if (overlaps(ranges[i][0], ranges[i][1], ranges[j][0], ranges[j][1])) return 0;
    state->count = count; state->records = records; state->events = events;
    state->used = used; state->capacity = capacity; state->remove = ls[shape + 116] != 0;
    collision_box(ls, header, shape, box);
    for (uint32_t i = 0; i < count; ++i) {
        const uint32_t record = records + i * RECORD_BYTES;
        particles[i].position = collision_vector(load(ls, record));
        particles[i].motion = collision_vector(load(ls, record + 48));
        particles[i].enabled = word(ls, record + 100);
    }
    return 1;
}

// Ordered publication of a collision batch. Contacts are appended to the event
// list while it has room; the removal flag moves the last record over each
// contacting record. The original visits records backwards. A full event list
// suppresses only the append, not the removal or its temporary payload write.
static void collision_publish(uint8_t* ls, uint32_t header, uint32_t stack, const CollisionState* state,
                              const MotorstormCollisionResult* result) {
    uint32_t used = state->used, remaining = state->count;
    for (uint32_t i = state->count; i-- > 0;) {
        if (!result->hit[i]) continue;
        for (unsigned lane = 0; lane < 4; ++lane)
            put_word(ls, stack - 400 + 32 + lane * 4, result->contact[i].component[lane]);
        if (used < state->capacity) {
            memcpy(ls + state->events + used * 16, ls + stack - 368, 16);
            put_word(ls, header + MOTORSTORM_COMMAND_EVENTS, ++used);
        }
        if (state->remove) {
            --remaining;
            put_word(ls, header + 8, remaining);
            memmove(ls + state->records + i * RECORD_BYTES, ls + state->records + remaining * RECORD_BYTES,
                    RECORD_BYTES);
        }
    }
}

// The completion flag is one when a life ratio reached one.
static uint32_t completion_flag(const uint8_t* ls, uint32_t header) {
    for (unsigned i = 0; i < 128; ++i) {
        float life;
        const uint32_t bits = word(ls, header + MOTORSTORM_COMMAND_LIFE + 4 * i);
        memcpy(&life, &bits, sizeof(life));
        if (!(1.0f > life)) return 1;
    }
    return 0;
}

int motorstorm_particle_commands_plan(uint8_t* image, MotorstormCommandState* state, uint32_t stack,
                                      uint32_t limit, MotorstormCommandResults* results,
                                      MotorstormCommandTrace* trace) {
    memset(trace, 0, sizeof(*trace));
    results->count = 0;
    const uint32_t header = state->header, count = state->count;
    if (!image || !state || !results || !trace || !limit || limit > MOTORSTORM_COMMANDS || (header & 15) ||
        !inside(header, 1784) || (int32_t)count <= 0 || state->index >= count)
        return 0;
    uint32_t list = state->list, data = state->data, index = state->index;
    while (trace->commands < limit) {
        if (!inside(list, 8)) break;
        const uint32_t opcode = image[list + 2], size = image[list + 3];
        if (opcode != OPERATOR_SLOT && opcode != OPERATOR_COLLISION) break;
        // Operators 5 and 8 leave the command counter unchanged; only the
        // operators 26 and 27 count, and they stay interpreted.
        if ((int32_t)word(image, header + MOTORSTORM_COMMAND_COUNTER) > 127) break;
        if (opcode == OPERATOR_SLOT) {
            if (!write_slot(image, header, data)) break;
            ++trace->slots;
        } else {
            CollisionState collision;
            MotorstormCollisionBox box;
            MotorstormCollisionParticle particles[MOTORSTORM_COLLISION_PARTICLES];
            MotorstormCollisionResult* result = &results->item[results->count];
            if (!collision_inputs(image, header, data, stack, &collision, &box, particles) ||
                !motorstorm_particle_box_contacts(particles, collision.count, &box, result)) break;
            ++results->count;
            collision_publish(image, header, stack, &collision, result);
            ++trace->collisions;
            trace->collision_list = list; trace->collision_data = data; trace->collision_index = index;
        }
        data += size << 4;
        if (word(image, header + MOTORSTORM_COMMAND_FLAG) == 1) {
            put_word(image, header + MOTORSTORM_COMMAND_FLAG, completion_flag(image, header));
            trace->scan[trace->commands] = 1;
        }
        ++trace->commands;
        ++index;
        list += 4;
        if (index == count) {
            trace->finished = 1;
            break;
        }
    }
    if (!trace->commands) return 0;
    state->list = list; state->data = data; state->index = index;
    return 1;
}

int motorstorm_particle_commands_apply(uint8_t* ls, const MotorstormCommandState* before, uint32_t stack,
                                       const MotorstormCommandResults* results,
                                       const MotorstormCommandTrace* trace,
                                       MotorstormCommandState* after) {
    const uint32_t header = before->header;
    uint32_t list = before->list, data = before->data, index = before->index, recorded = 0;
    if (!ls || !before || !results || !trace || !after || !trace->commands ||
        trace->commands > MOTORSTORM_COMMANDS || results->count != trace->collisions ||
        (int32_t)before->count <= 0 || index >= before->count) return 0;
    for (uint32_t k = 0; k < trace->commands; ++k) {
        if (!inside(list, 8)) return 0;
        const uint32_t opcode = ls[list + 2], size = ls[list + 3];
        if ((int32_t)word(ls, header + MOTORSTORM_COMMAND_COUNTER) > 127) return 0;
        if (opcode == OPERATOR_SLOT) {
            if (!write_slot(ls, header, data)) return 0;
        } else if (opcode == OPERATOR_COLLISION && recorded < results->count) {
            CollisionState collision;
            MotorstormCollisionBox box;
            MotorstormCollisionParticle particles[MOTORSTORM_COLLISION_PARTICLES];
            if (!collision_inputs(ls, header, data, stack, &collision, &box, particles)) return 0;
            collision_publish(ls, header, stack, &collision, &results->item[recorded++]);
        } else return 0;
        data += size << 4;
        if (trace->scan[k]) put_word(ls, header + MOTORSTORM_COMMAND_FLAG, completion_flag(ls, header));
        ++index;
        list += 4;
    }
    if (recorded != results->count) return 0;
    after->header = header; after->list = list; after->data = data; after->index = index;
    after->count = before->count;
    return 1;
}

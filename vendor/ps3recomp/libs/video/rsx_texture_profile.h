#ifndef RSX_TEXTURE_PROFILE_H
#define RSX_TEXTURE_PROFILE_H

#include <stdint.h>
#include <string.h>

/* Render-thread-only diagnostic wall times. No clock calls when disabled. */
enum rsx_texture_outcome {
    RSX_TEX_INVALID, RSX_TEX_FRAME_HIT, RSX_TEX_VALIDATED_HIT,
    RSX_TEX_STALE, RSX_TEX_MISS, RSX_TEX_FORCED, RSX_TEX_OUTCOMES
};
typedef double (*rsx_texture_clock)(void*);
typedef struct {
    uint64_t calls, failures, outcomes[RSX_TEX_OUTCOMES];
    uint64_t examined, checksum_calls, sampled_words, clock_errors;
    double setup, lookup, checksum, remainder, total;
} rsx_texture_profile;
typedef struct {
    rsx_texture_profile* stats;
    rsx_texture_clock clock;
    void* user;
    double start, lookup_start, checksum_start, setup, lookup, checksum;
    uint64_t examined, checksum_calls, sampled_words;
    int lookup_done, outcome;
} rsx_texture_profile_call;

static inline void rsx_texture_profile_begin(rsx_texture_profile_call* call,
        rsx_texture_profile* stats, rsx_texture_clock clock, void* user)
{
    memset(call, 0, sizeof(*call));
    if (!clock) return;
    call->stats = stats; call->clock = clock; call->user = user;
    call->start = clock(user);
}

static inline void rsx_texture_profile_lookup_begin(rsx_texture_profile_call* c)
{
    if (!c || !c->clock) return;
    c->lookup_start = c->clock(c->user);
    c->setup = c->lookup_start - c->start;
}

static inline void rsx_texture_profile_lookup_end(rsx_texture_profile_call* c,
        uint64_t examined, int outcome)
{
    if (!c || !c->clock || c->lookup_done) return;
    c->lookup = c->clock(c->user) - c->lookup_start;
    c->examined = examined; c->outcome = outcome; c->lookup_done = 1;
}

static inline void rsx_texture_profile_checksum_begin(rsx_texture_profile_call* c,
        uint32_t bytes)
{
    if (!c || !c->clock) return;
    uint32_t step = bytes > 4096 ? bytes / 1024 : 4;
    c->checksum_start = c->clock(c->user);
    c->checksum_calls++;
    if (bytes >= 4) c->sampled_words += 1 + (bytes - 4) / step;
}

static inline void rsx_texture_profile_checksum_end(rsx_texture_profile_call* c)
{
    if (c && c->clock) c->checksum += c->clock(c->user) - c->checksum_start;
}

static inline void rsx_texture_profile_finish(rsx_texture_profile_call* c, int result)
{
    if (!c || !c->clock) return;
    rsx_texture_profile* s = c->stats;
    double total = c->clock(c->user) - c->start;
    double remainder = total - c->setup - c->lookup - c->checksum;
    s->calls++; s->failures += result < 0; s->outcomes[c->outcome]++;
    s->examined += c->examined; s->checksum_calls += c->checksum_calls;
    s->sampled_words += c->sampled_words;
    s->total += total; s->setup += c->setup; s->lookup += c->lookup;
    s->checksum += c->checksum; s->remainder += remainder;
    if (total < 0 || c->setup < 0 || c->lookup < 0 || c->checksum < 0 || remainder < -1e-12)
        s->clock_errors++;
}

#endif

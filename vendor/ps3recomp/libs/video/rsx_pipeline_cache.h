/* Bounded pipeline metadata. Keys and resource ownership belong to the caller.
 * Growth preserves entries; at the cap FIFO replacement happens in place. */
#ifndef RSX_PIPELINE_CACHE_H
#define RSX_PIPELINE_CACHE_H
#include "rsx_slot_pool.h"
typedef struct {
    void *data;
    unsigned count, capacity, next;
} rsx_pipeline_cache;

static void *rsx_pipeline_cache_acquire(rsx_pipeline_cache *cache, size_t stride,
                                      unsigned initial, unsigned limit,
                                      int *replaced)
{
    if (!cache || !replaced || !stride || !initial || !limit ||
        cache->count > cache->capacity || cache->capacity > limit ||
        (cache->capacity && !cache->data)) return NULL;
    *replaced = 0;
    if (cache->count == cache->capacity && cache->capacity < limit) {
        unsigned capacity = cache->capacity;
        void *data = rsx_slot_pool_grow(cache->data, capacity, cache->count + 1,
                                      initial, limit, stride, &capacity);
        if (!data) return NULL; /* Existing entries/ownership remain intact. */
        cache->data = data;
        cache->capacity = capacity;
    }
    unsigned slot;
    if (cache->count < cache->capacity) slot = cache->count++;
    else {
        slot = cache->next;
        cache->next = (slot + 1) % cache->capacity;
        *replaced = 1;
    }
    return (char *)cache->data + (size_t)slot * stride;
}
#endif

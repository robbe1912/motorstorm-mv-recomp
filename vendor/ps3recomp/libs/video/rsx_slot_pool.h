/* Bounded metadata growth for resources pinned by a recorded working set.
 * realloc preserves stored resource identities; callers own GPU retirement. */
#ifndef RSX_SLOT_POOL_H
#define RSX_SLOT_POOL_H
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
static void* rsx_slot_pool_grow(void* old,unsigned capacity,unsigned required,
                              unsigned initial,unsigned limit,size_t stride,
                              unsigned* result_capacity)
{
    if(!result_capacity || !stride || !initial || capacity>limit ||
       required>limit || limit>SIZE_MAX/stride || (capacity && !old)) return NULL;
    *result_capacity=capacity;
    if(required<=capacity) return old;
    unsigned next=capacity?capacity:(initial<limit?initial:limit);
    while(next<required) next=next>limit/2?limit:next*2;
    void* p=realloc(old,(size_t)next*stride);
    if(!p) return NULL;
    memset((char*)p+(size_t)capacity*stride,0,(size_t)(next-capacity)*stride);
    *result_capacity=next;return p;
}
#endif

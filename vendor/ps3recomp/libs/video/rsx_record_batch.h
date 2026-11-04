/* Internal record batches are independent of guest flips. A capacity drain
 * submits work but never presents, and does not restart implicit clears. */
#ifndef PS3RECOMP_RSX_RECORD_BATCH_H
#define PS3RECOMP_RSX_RECORD_BATCH_H
#include <stdint.h>
typedef struct rsx_record_batch {
    int backing_initialized;
    int display_written;
} rsx_record_batch;
static int rsx_record_batch_begin(rsx_record_batch* state)
{
    int clear = !state->backing_initialized;
    state->backing_initialized = 1;
    return clear;
}
static void rsx_record_batch_display_write(rsx_record_batch* state)
{ state->display_written = 1; }
static void rsx_record_batch_presented(rsx_record_batch* state)
{ state->backing_initialized = 0; state->display_written = 0; }
static int rsx_record_batch_room(const uint32_t* count, uint32_t capacity,
                                 void* context, void (*submit)(void*, int))
{
    if (!capacity || *count > capacity) return 0;
    if (*count == capacity) submit(context, 0);
    return *count < capacity;
}
#endif

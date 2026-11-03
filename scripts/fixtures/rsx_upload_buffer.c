#include "rsx_upload_buffer.h"
#include <stdio.h>
#include <stdlib.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
typedef struct fixture { int allocations, retires, disposals, fail_allocate, fail_retire; uint64_t requested_bytes; } fixture;
static int allocate(void* context, uint64_t bytes, rsx_upload_buffer* b)
{
    fixture* f = context; ++f->allocations;
    f->requested_bytes = bytes;
    if (f->fail_allocate) return 0;
    b->memory = malloc((size_t)bytes); b->resource = b->memory;
    if (!b->memory) return 0;
    memset(b->memory, 0xCD, (size_t)bytes); return 1;
}
static int retire(void* context) { fixture* f = context; ++f->retires; return !f->fail_retire; }
static void dispose(void* context, rsx_upload_buffer* b)
{ fixture* f = context; ++f->disposals; free(b->memory); b->memory = b->resource = NULL; }
int main(void)
{
    fixture f = {0}; rsx_upload_ops ops = {&f, allocate, retire, dispose};
    rsx_upload_buffer b = {0};
    CHECK(allocate(&f, 2 * 8 * 16, &b)); b.capacity = 8;
    memset(b.memory, 0x17, 8 * 16);
    memset((unsigned char*)b.memory + 8 * 16, 0x62, 8 * 16);
    CHECK(rsx_upload_reserve(&b, 8 * 16, 6, 16, &ops));
    CHECK(b.capacity == 16 && f.retires == 1 && f.disposals == 1);
    for (size_t i = 0; i < 8 * 16; ++i) {
        CHECK(((unsigned char*)b.memory)[i] == 0x17);
        CHECK(((unsigned char*)b.memory)[16 * 16 + i] == 0x62);
    }
    /* Append the complete expanded strip, in each relocated parity half. */
    memset((unsigned char*)b.memory + 8 * 16, 0x35, 6 * 16);
    memset((unsigned char*)b.memory + 16 * 16 + 8 * 16, 0x49, 6 * 16);
    CHECK(rsx_upload_reserve(&b, 14 * 16, 2, 16, &ops));
    CHECK(b.capacity == 16 && f.retires == 1);
    void* old = b.memory; int disposed = f.disposals;
    f.fail_allocate = 1;
    CHECK(!rsx_upload_reserve(&b, 16 * 16, 1, 16, &ops));
    CHECK(b.memory == old && b.capacity == 16 && f.disposals == disposed);
    f.fail_allocate = 0; f.fail_retire = 1;
    CHECK(!rsx_upload_reserve(&b, 16 * 16, 1, 16, &ops));
    CHECK(b.memory == old && b.capacity == 16 && f.disposals == disposed + 1);
    f.fail_retire = 0;
    int allocated = f.allocations;
    CHECK(!rsx_upload_reserve(&b, 0, UINT64_MAX, 16, &ops));
    CHECK(!rsx_upload_reserve(&b, 1, 1, 16, &ops));
    CHECK(!rsx_upload_reserve(&b, 17 * 16, 1, 16, &ops));
    CHECK(!rsx_upload_reserve(&b, 0, 1, 0, &ops));
    CHECK(f.allocations == allocated);
    /* Check saturated 32-bit view arithmetic without allocating gigabytes. */
    if (SIZE_MAX > UINT32_MAX) {
        f.fail_allocate = 1;
        CHECK(!rsx_upload_reserve(&b, 0, UINT32_MAX / 16u, 16, &ops));
        CHECK(f.allocations == allocated + 1);
        CHECK(f.requested_bytes == (uint64_t)(UINT32_MAX / 16u) * 16u * 2u);
        CHECK(b.memory == old && b.capacity == 16);
        CHECK(!rsx_upload_reserve(&b, 0, (uint64_t)UINT32_MAX / 16u + 1u, 16, &ops));
        CHECK(f.allocations == allocated + 1);
        f.fail_allocate = 0;
    }
    CHECK(rsx_upload_reserve(&b, 14 * 16, 33, 16, &ops));
    CHECK(b.capacity == 64);
    for (size_t i = 0; i < 6 * 16; ++i) {
        CHECK(((unsigned char*)b.memory)[8 * 16 + i] == 0x35);
        CHECK(((unsigned char*)b.memory)[64 * 16 + 8 * 16 + i] == 0x49);
    }
    dispose(&f, &b);
    puts("PASS: upload growth preserves both parity halves, append data and failure rollback");
    return 0;
}

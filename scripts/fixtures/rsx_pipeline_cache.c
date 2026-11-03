/* Exercise production storage with authored identities and owned references. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int fail_allocation;
static void *test_realloc(void *p, size_t bytes) {
    return fail_allocation ? NULL : realloc(p, bytes);
}
#define realloc test_realloc
#include "rsx_pipeline_cache.h"
#undef realloc
typedef struct { unsigned key, references; unsigned payload[16]; } entry;
static unsigned checks, failures, releases;
static void check(int ok, const char *name) {
    ++checks;
    if (!ok) { ++failures; fprintf(stderr, "FAIL %s\n", name); }
}
static entry *find(rsx_pipeline_cache *c, unsigned key) {
    entry *entries = (entry *)c->data;
    for (unsigned i = 0; i < c->count; ++i)
        if (entries[i].key == key) return entries + i;
    return NULL;
}
static void release(entry *e) {
    if (e->references) { --e->references; ++releases; }
}
static int put(rsx_pipeline_cache *c, unsigned key, unsigned limit) {
    int replaced;
    entry *e = rsx_pipeline_cache_acquire(c, sizeof(*e), 256, limit, &replaced);
    if (!e) return 0;
    if (replaced) release(e);
    memset(e, 0, sizeof(*e));
    e->key = key; e->references = 1; e->payload[0] = key ^ 0xabc;
    return 1;
}
int main(int argc, char **argv) {
    unsigned limit = argc > 1 && !strcmp(argv[1], "--legacy") ? 256 : 4096;
    rsx_pipeline_cache c = {0};
    for (unsigned i = 0; i < 600; ++i) if (!put(&c, i, limit)) return 2;
    unsigned misses = 0;
    for (unsigned sweep = 0; sweep < 5; ++sweep)
        for (unsigned i = 0; i < 600; ++i) {
            entry *e = find(&c, i);
            if (!e) { ++misses; if (!put(&c, i, limit)) return 2; }
        }
    check(misses == 0, "repeated 600-key working set stays resident");
    if (limit == 256) {
        printf("legacy_misses=%u checks=%u failures=%u\n", misses, checks, failures);
        free(c.data); return failures ? 1 : 0;
    }
    check(c.count == 600 && c.capacity == 1024, "bounded geometric growth");
    int intact = 1;
    for (unsigned i = 0; i < 600; ++i) {
        entry *e = find(&c, i);
        if (!e || e->references != 1 || e->payload[0] != (i ^ 0xabc)) intact = 0;
    }
    check(intact && releases == 0, "growth preserves identities payloads and ownership");
    for (unsigned i = 600; i < 4096; ++i) if (!put(&c, i, limit)) return 2;
    check(c.capacity == limit && c.count == limit, "hard entry bound");
    entry *stable = find(&c, 10);
    check(put(&c, 4096, limit) && !find(&c, 0) && find(&c, 4096), "oldest entry replaced at cap");
    check(stable == find(&c, 10) && releases == 1, "replacement does not move other entries");
    for (unsigned i = 4097; i < 4106; ++i) if (!put(&c, i, limit)) return 2;
    check(!find(&c, 9) && find(&c, 10) && releases == 10, "FIFO cursor advances");
    for (unsigned i = 0; i < c.count; ++i) release((entry *)c.data + i);
    check(releases == 4106, "each cache-owned reference released exactly once");
    free(c.data);
    c = (rsx_pipeline_cache){0};
    for (unsigned i = 0; i < 256; ++i) if (!put(&c, i, limit)) return 2;
    rsx_pipeline_cache before = c;
    fail_allocation = 1;
    check(!put(&c, 256, limit) && !memcmp(&before, &c, sizeof(c)) && find(&c, 0),
          "allocation failure preserves existing entries and state");
    fail_allocation = 0;
    check(put(&c, 256, limit) && c.capacity == 512, "growth can recover after allocation failure");
    free(c.data);
    printf("checks=%u failures=%u warm_misses=%u\n", checks, failures, misses);
    return failures ? 1 : 0;
}

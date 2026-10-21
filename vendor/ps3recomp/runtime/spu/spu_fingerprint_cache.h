/* Exact, bounded memoization of stable byte-buffer fingerprints.
 * A key/pointer match alone NEVER authorizes a hit: compare every byte.
 * Callers retain the original requirement that the buffer stays stable
 * during a fingerprint call. This does not make concurrent writes atomic.
 */
#ifndef SPU_FINGERPRINT_CACHE_H
#define SPU_FINGERPRINT_CACHE_H
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#ifndef SPU_FP_ALLOC
#define SPU_FP_ALLOC malloc
#endif
#ifndef SPU_FP_FREE
#define SPU_FP_FREE free
#endif
#define SPU_FP_SLOTS 32u
#define SPU_FP_MIN_BUFFER 4096u
#define SPU_FP_MAX_BUFFER 262144u
#define SPU_FP_MAX_BYTES (4u * 1024u * 1024u)
typedef uint64_t (*spu_fp_raw_fn)(const void*, size_t);
typedef struct {
    const void* key;
    unsigned char* snapshot;
    size_t size;
    uint64_t hash;
} spu_fp_entry;
typedef struct {
    spu_fp_entry entries[SPU_FP_SLOTS];
    size_t retained_bytes;
    unsigned next;
    uint64_t calls, hits, misses, bypasses, comparison_span_bytes, bytes_hashed;
    uint64_t allocation_failures, evictions;
    uint64_t thread;
    int stats;
} spu_fp_cache;
static inline void spu_fp_drop(spu_fp_cache* c, unsigned slot) {
    spu_fp_entry* e = c->entries + slot;
    if (e->snapshot) {
        c->retained_bytes -= e->size;
        SPU_FP_FREE(e->snapshot);
        memset(e, 0, sizeof(*e));
        c->evictions++;
    }
}
static inline void spu_fp_clear(spu_fp_cache* c) {
    for (unsigned i = 0; i < SPU_FP_SLOTS; ++i) spu_fp_drop(c, i);
}
static inline uint64_t spu_fp_compute(spu_fp_cache* c, const void* data,
                                      size_t n, spu_fp_raw_fn raw) {
    if (!c) return raw(data, n);
    c->calls++;
    if (n < SPU_FP_MIN_BUFFER || n > SPU_FP_MAX_BUFFER) {
        c->bypasses++; c->bytes_hashed += n;
        return raw(data, n);
    }
    unsigned slot = SPU_FP_SLOTS;
    for (unsigned i = 0; i < SPU_FP_SLOTS; ++i) {
        spu_fp_entry* e = c->entries + i;
        if (e->snapshot && e->key == data && e->size == n) {
            c->comparison_span_bytes += n;
            if (!memcmp(e->snapshot, data, n)) { c->hits++; return e->hash; }
            slot = i; break;
        }
    }
    c->misses++; c->bytes_hashed += n;
    if (slot == SPU_FP_SLOTS) {
        slot = c->next; c->next = (c->next + 1) % SPU_FP_SLOTS;
        spu_fp_drop(c, slot);
        while (c->retained_bytes + n > SPU_FP_MAX_BYTES) {
            unsigned victim = c->next; c->next = (c->next + 1) % SPU_FP_SLOTS;
            spu_fp_drop(c, victim);
        }
        unsigned char* snapshot = (unsigned char*)SPU_FP_ALLOC(n);
        if (!snapshot) {
            c->allocation_failures++;
            fprintf(stderr, "[SPUFP] snapshot allocation failed; exact uncached result retained\n");
            return raw(data, n);
        }
        c->entries[slot].snapshot = snapshot;
        c->entries[slot].key = data;
        c->entries[slot].size = n;
        c->retained_bytes += n;
    }
    memcpy(c->entries[slot].snapshot, data, n);
    /* Hash the owned copy: a cache must never associate a hash from one read
     * with snapshot bytes from a different read, even across buffer reuse. */
    uint64_t hash = raw(c->entries[slot].snapshot, n);
    c->entries[slot].hash = hash;
    return hash;
}
static inline void spu_fp_report(spu_fp_cache* c) {
    if (c->stats) fprintf(stderr,
        "[SPUFP] thread=%llu cache=%p calls=%llu hits=%llu misses=%llu bypasses=%llu compare_span_bytes=%llu hashed_bytes=%llu retained_bytes=%zu evictions=%llu allocation_failures=%llu\n",
        (unsigned long long)c->thread, (void*)c,
        (unsigned long long)c->calls, (unsigned long long)c->hits,
        (unsigned long long)c->misses, (unsigned long long)c->bypasses,
        (unsigned long long)c->comparison_span_bytes, (unsigned long long)c->bytes_hashed,
        c->retained_bytes, (unsigned long long)c->evictions,
        (unsigned long long)c->allocation_failures);
}
static inline void spu_fp_destroy(void* value) {
    spu_fp_cache* c = (spu_fp_cache*)value;
    if (!c) return;
    spu_fp_report(c);
    spu_fp_clear(c); SPU_FP_FREE(c);
}
#ifdef _WIN32
#include <windows.h>
static DWORD spu_fp_key = FLS_OUT_OF_INDEXES;
static INIT_ONCE spu_fp_once = INIT_ONCE_STATIC_INIT;
static VOID CALLBACK spu_fp_destructor(PVOID p) { spu_fp_destroy(p); }
static BOOL CALLBACK spu_fp_make_key(PINIT_ONCE once, PVOID arg, PVOID* context) {
    (void)once; (void)arg; (void)context;
    spu_fp_key = FlsAlloc(spu_fp_destructor);
    if (spu_fp_key == FLS_OUT_OF_INDEXES)
        fprintf(stderr, "[SPUFP] FlsAlloc failed; using exact uncached fingerprints\n");
    return TRUE;
}
static inline spu_fp_cache* spu_fp_thread_get(void) {
    if (!InitOnceExecuteOnce(&spu_fp_once, spu_fp_make_key, NULL, NULL)) {
        fprintf(stderr, "[SPUFP] InitOnce failed; using exact uncached fingerprints\n"); return NULL;
    }
    return spu_fp_key == FLS_OUT_OF_INDEXES ? NULL : (spu_fp_cache*)FlsGetValue(spu_fp_key);
}
static inline int spu_fp_thread_set(spu_fp_cache* c) {
    return spu_fp_key != FLS_OUT_OF_INDEXES && FlsSetValue(spu_fp_key, c);
}
#else
#include <pthread.h>
static pthread_key_t spu_fp_key;
static pthread_once_t spu_fp_once = PTHREAD_ONCE_INIT;
static int spu_fp_key_valid;
static void spu_fp_make_key(void) {
    spu_fp_key_valid = pthread_key_create(&spu_fp_key, spu_fp_destroy) == 0;
    if (!spu_fp_key_valid) fprintf(stderr, "[SPUFP] pthread key creation failed; using exact uncached fingerprints\n");
}
static inline spu_fp_cache* spu_fp_thread_get(void) {
    if (pthread_once(&spu_fp_once, spu_fp_make_key)) {
        fprintf(stderr, "[SPUFP] pthread_once failed; using exact uncached fingerprints\n"); return NULL;
    }
    return spu_fp_key_valid ? (spu_fp_cache*)pthread_getspecific(spu_fp_key) : NULL;
}
static inline int spu_fp_thread_set(spu_fp_cache* c) {
    return spu_fp_key_valid && pthread_setspecific(spu_fp_key, c) == 0;
}
#endif
#if defined(_MSC_VER)
#define SPU_FP_THREAD_LOCAL __declspec(thread)
#else
#define SPU_FP_THREAD_LOCAL __thread
#endif
static inline void spu_fp_thread_release(void) {
    spu_fp_cache* c = spu_fp_thread_get();
    if (c) {
        if (spu_fp_thread_set(NULL)) spu_fp_destroy(c);
        else fprintf(stderr, "[SPUFP] detach failed; cache remains owned by thread destructor\n");
    }
}
static inline uint64_t spu_fp_cached(const void* data, size_t n, spu_fp_raw_fn raw) {
    static SPU_FP_THREAD_LOCAL int mode = -1;
    if (mode < 0) {
        const char* e = getenv("SPU_FINGERPRINT_CACHE");
        mode = e && *e && strcmp(e, "0");
    }
    if (!mode) return raw(data, n); /* Default: no cache allocation or byte comparisons. */
    spu_fp_cache* c = spu_fp_thread_get();
    if (!c) {
        c = (spu_fp_cache*)SPU_FP_ALLOC(sizeof(*c));
        if (!c) {
            fprintf(stderr, "[SPUFP] thread cache allocation failed; using exact uncached fingerprints\n");
            return raw(data, n);
        }
        memset(c, 0, sizeof(*c));
#ifdef _WIN32
        c->thread = GetCurrentThreadId();
#else
        c->thread = (uint64_t)(uintptr_t)pthread_self();
#endif
        const char* e = getenv("SPU_FINGERPRINT_STATS"); c->stats = e && *e && strcmp(e, "0");
        if (!spu_fp_thread_set(c)) {
            fprintf(stderr, "[SPUFP] thread cache installation failed; using exact uncached fingerprints\n");
            spu_fp_destroy(c); return raw(data, n);
        }
    }
    uint64_t result = spu_fp_compute(c, data, n, raw);
    /* Bounded live diagnostics even if an owned run stops persistent workers.
     * Powers of two produce at most64 lines per cache lifetime, no clocks. */
    if (c->stats && !(c->calls & (c->calls - 1))) spu_fp_report(c);
    return result;
}
#endif

/* Successful compiler blobs, keyed by the complete effective compiler input.
 * Callers own their returned reference; entries own a separate reference.
 * Callers serialize access and insert only successful compiler results.
 * The budget accounts for copied keys and the supplied bytecode size. */
#ifndef RSX_SHADER_CACHE_H
#define RSX_SHADER_CACHE_H
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifndef RSX_SHADER_CACHE_ENTRIES
#define RSX_SHADER_CACHE_ENTRIES 256
#endif
#ifndef RSX_SHADER_CACHE_BYTES
#define RSX_SHADER_CACHE_BYTES (32u * 1024u * 1024u)
#endif
typedef struct {
    const void* source; size_t bytes;
    const char *name, *entry, *target;
    unsigned flags1, flags2;
} rsx_shader_key;
typedef struct {
    void* context;
    void (*retain)(void*, void*);
    void (*release)(void*, void*);
} rsx_shader_blob_ops;
typedef struct {
    rsx_shader_key key; void *storage, *blob;
    size_t cost; uint64_t hash, stamp;
    unsigned tag; /* Caller provenance; never part of shader identity. */
} rsx_shader_cache_entry;
typedef struct {
    rsx_shader_cache_entry entries[RSX_SHADER_CACHE_ENTRIES];
    size_t bytes; unsigned count; uint64_t clock;
} rsx_shader_cache;
static uint64_t rsx_shader_key_hash(const rsx_shader_key* k)
{
    uint64_t h = UINT64_C(14695981039346656037);
    const unsigned char* p = (const unsigned char*)k->source;
    for (size_t i=0;i<k->bytes;i++) h=(h^p[i])*UINT64_C(1099511628211);
    return h;
}
static int rsx_shader_key_equal(const rsx_shader_key* a,const rsx_shader_key* b)
{
    return a->bytes==b->bytes && a->flags1==b->flags1 && a->flags2==b->flags2 &&
        !strcmp(a->name,b->name) && !strcmp(a->entry,b->entry) &&
        !strcmp(a->target,b->target) && !memcmp(a->source,b->source,a->bytes);
}
static int rsx_shader_key_copy(const rsx_shader_key* k,rsx_shader_key* out,void** storage)
{
    if(!k || !k->source || !k->bytes || k->bytes>1024u*1024u ||
       !k->name || !k->entry || !k->target)return 0;
    size_t n=strlen(k->name)+1,e=strlen(k->entry)+1,t=strlen(k->target)+1;
    if(n>256 || e>256 || t>256)return 0;
    unsigned char* p=(unsigned char*)malloc(k->bytes+n+e+t);if(!p)return 0;
    *out=*k;memcpy(p,k->source,k->bytes);out->source=p;
    memcpy(p+k->bytes,k->name,n);out->name=(char*)p+k->bytes;
    memcpy(p+k->bytes+n,k->entry,e);out->entry=(char*)p+k->bytes+n;
    memcpy(p+k->bytes+n+e,k->target,t);out->target=(char*)p+k->bytes+n+e;
    *storage=p;return 1;
}
static unsigned rsx_shader_cache_tag(const rsx_shader_cache* c,const rsx_shader_key* k)
{
    uint64_t hash=rsx_shader_key_hash(k);
    for(unsigned i=0;i<RSX_SHADER_CACHE_ENTRIES;i++)
        if(c->entries[i].blob && c->entries[i].hash==hash &&
           rsx_shader_key_equal(&c->entries[i].key,k))return c->entries[i].tag;
    return 0;
}
static void rsx_shader_cache_set_tag(rsx_shader_cache* c,const rsx_shader_key* k,unsigned tag)
{
    uint64_t hash=rsx_shader_key_hash(k);
    for(unsigned i=0;i<RSX_SHADER_CACHE_ENTRIES;i++)
        if(c->entries[i].blob && c->entries[i].hash==hash &&
           rsx_shader_key_equal(&c->entries[i].key,k)){c->entries[i].tag=tag;return;}
}
static void* rsx_shader_cache_get(rsx_shader_cache* c,const rsx_shader_key* k,
                                 const rsx_shader_blob_ops* ops)
{
    if(!k->source || !k->bytes || !k->name || !k->entry || !k->target)return NULL;
    uint64_t hash=rsx_shader_key_hash(k);
    for(unsigned i=0;i<RSX_SHADER_CACHE_ENTRIES;i++) {
        rsx_shader_cache_entry* e=&c->entries[i];
        if(e->blob && e->hash==hash && rsx_shader_key_equal(&e->key,k)) {
            e->stamp=++c->clock; ops->retain(ops->context,e->blob); return e->blob;
        }
    }
    return NULL;
}
static void rsx_shader_cache_drop(rsx_shader_cache* c,unsigned i,
                                  const rsx_shader_blob_ops* ops)
{
    rsx_shader_cache_entry* e=&c->entries[i];
    if(!e->blob)return;
    ops->release(ops->context,e->blob); free(e->storage);
    c->bytes-=e->cost;c->count--;memset(e,0,sizeof(*e));
}
static void rsx_shader_cache_remove(rsx_shader_cache* c,const rsx_shader_key* k,
                                    const rsx_shader_blob_ops* ops)
{
    uint64_t hash=rsx_shader_key_hash(k);
    for(unsigned i=0;i<RSX_SHADER_CACHE_ENTRIES;i++)
        if(c->entries[i].blob && c->entries[i].hash==hash &&
           rsx_shader_key_equal(&c->entries[i].key,k))rsx_shader_cache_drop(c,i,ops);
}
static int rsx_shader_cache_put(rsx_shader_cache* c,const rsx_shader_key* k,
                                void* blob,size_t blob_bytes,
                                const rsx_shader_blob_ops* ops)
{
    if(!blob || !blob_bytes || !k->source || !k->bytes ||
       !k->name || !k->entry || !k->target)return 0;
    size_t n=strlen(k->name)+1,a=strlen(k->entry)+1,t=strlen(k->target)+1;
    size_t strings=n+a+t;
    if(k->bytes>RSX_SHADER_CACHE_BYTES || strings>RSX_SHADER_CACHE_BYTES-k->bytes)
        return 0;
    size_t copied=k->bytes+strings;
    if(blob_bytes>RSX_SHADER_CACHE_BYTES-copied)return 0;
    size_t cost=copied+blob_bytes;
    unsigned char* storage=(unsigned char*)malloc(copied);
    if(!storage)return 0;
    rsx_shader_key saved=*k;uint64_t hash=rsx_shader_key_hash(k);
    memcpy(storage,k->source,k->bytes);saved.source=storage;
    memcpy(storage+k->bytes,k->name,n);saved.name=(char*)storage+k->bytes;
    memcpy(storage+k->bytes+n,k->entry,a);saved.entry=(char*)storage+k->bytes+n;
    memcpy(storage+k->bytes+n+a,k->target,t);saved.target=(char*)storage+k->bytes+n+a;
    for(unsigned i=0;i<RSX_SHADER_CACHE_ENTRIES;i++)
        if(c->entries[i].blob && c->entries[i].hash==hash &&
           rsx_shader_key_equal(&c->entries[i].key,&saved))rsx_shader_cache_drop(c,i,ops);
    while(c->count==RSX_SHADER_CACHE_ENTRIES || c->bytes>RSX_SHADER_CACHE_BYTES-cost) {
        unsigned oldest=RSX_SHADER_CACHE_ENTRIES;
        for(unsigned i=0;i<RSX_SHADER_CACHE_ENTRIES;i++)
            if(c->entries[i].blob && (oldest==RSX_SHADER_CACHE_ENTRIES ||
                 c->entries[i].stamp<c->entries[oldest].stamp))oldest=i;
        rsx_shader_cache_drop(c,oldest,ops);
    }
    unsigned slot=0;while(c->entries[slot].blob)slot++;
    rsx_shader_cache_entry* e=&c->entries[slot];e->key=saved;
    e->storage=storage;e->blob=blob;e->cost=cost;e->hash=hash;
    e->stamp=++c->clock;ops->retain(ops->context,blob);c->bytes+=cost;c->count++;
    return 1;
}
static void rsx_shader_cache_clear(rsx_shader_cache* c,const rsx_shader_blob_ops* ops)
{
    for(unsigned i=0;i<RSX_SHADER_CACHE_ENTRIES;i++)rsx_shader_cache_drop(c,i,ops);
}
#endif

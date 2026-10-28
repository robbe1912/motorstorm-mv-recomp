/* Hashes choose buckets; complete canonical bytes decide identity. A full
 * table/arena never suppresses work. One coordinator owns this bounded table. */
#ifndef RSX_PREFETCH_SEEN_H
#define RSX_PREFETCH_SEEN_H
#include <stdint.h>
#include <string.h>
#define RSX_PREFETCH_SEEN_COUNT 4096u
#define RSX_PREFETCH_KEY_MAX (17u*1024u)
#define RSX_PREFETCH_KEY_BYTES (16u*1024u*1024u)
typedef struct {uint64_t hash,generation;size_t size,offset;} rsx_prefetch_slot;
typedef struct {rsx_prefetch_slot slots[RSX_PREFETCH_SEEN_COUNT];uint64_t generation;
    size_t used;unsigned char bytes[RSX_PREFETCH_KEY_BYTES];} rsx_prefetch_seen;
static void rsx_prefetch_begin(rsx_prefetch_seen* s)
{
    s->used=0;
    if(!++s->generation){memset(s->slots,0,sizeof(s->slots));s->generation=1;}
}
static int rsx_prefetch_contains_or_add(rsx_prefetch_seen* s,uint64_t hash,const void* key,size_t size)
{
    if(!key || !size || size>RSX_PREFETCH_KEY_MAX)return 0;
    unsigned start=(unsigned)(hash^(hash>>32))&(RSX_PREFETCH_SEEN_COUNT-1);
    for(unsigned n=0;n<RSX_PREFETCH_SEEN_COUNT;n++){
        rsx_prefetch_slot* p=&s->slots[(start+n)&(RSX_PREFETCH_SEEN_COUNT-1)];
        if(p->generation!=s->generation){
            if(size>RSX_PREFETCH_KEY_BYTES-s->used)return 0;
            p->generation=s->generation;p->hash=hash;p->size=size;p->offset=s->used;
            memcpy(s->bytes+s->used,key,size);s->used+=size;return 0;
        }
        if(p->hash==hash && p->size==size && !memcmp(s->bytes+p->offset,key,size))return 1;
    }
    return 0;
}
#endif

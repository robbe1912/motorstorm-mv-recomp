/* Workers own immutable compiler keys and blobs only. The renderer owns
 * all disk/cache/device/PSO state. Stop/join precedes renderer teardown. */
#ifndef RSX_SHADER_POOL_BACKEND_H
#define RSX_SHADER_POOL_BACKEND_H
#include "rsx_fxc_pool.h"
#include "rsx_prefetch_seen.h"
static INIT_ONCE s_shader_pool_once=INIT_ONCE_STATIC_INIT;
static rsx_fxc_pool* s_shader_pool;
static int shader_prefetch_active;
static uint64_t shader_prefetch_generation;
static unsigned shader_queued,shader_claimed;
static rsx_prefetch_seen s_shader_seen;
static int shader_worker_compile(void* user,const rsx_shader_key* key,void** output,size_t* bytes)
{
    (void)user;ID3DBlob *blob=NULL,*error=NULL;
    HRESULT hr=D3DCompile(key->source,key->bytes,key->name,NULL,NULL,key->entry,key->target,
                          key->flags1,key->flags2,&blob,&error);
    if(error)error->lpVtbl->Release(error);
    if(FAILED(hr) || !blob){if(blob)blob->lpVtbl->Release(blob);return 0;}
    *output=blob;*bytes=blob->lpVtbl->GetBufferSize(blob);return 1;
}
static void shader_worker_release(void* user,void* pointer)
{ (void)user;ID3DBlob* blob=(ID3DBlob*)pointer;blob->lpVtbl->Release(blob); }
static BOOL CALLBACK shader_pool_initialize(PINIT_ONCE once,PVOID arg,PVOID* result)
{
    (void)once;(void)arg;(void)result;
    SYSTEM_INFO info;GetSystemInfo(&info);unsigned count=rsx_fxc_default_threads(info.dwNumberOfProcessors);
    const char* option=getenv("RSX_FXC_THREADS");
    if(option && *option){
        char* end=NULL;long n=strtol(option,&end,10);
        if(end!=option && !*end && n>=0 && n<=16)count=(unsigned)n;
    }
    s_shader_pool=rsx_fxc_pool_create(count,shader_worker_compile,shader_worker_release,NULL);
    if(shader_cache_stats())fprintf(stderr,"[FXCPOOL] threads=%u\n",s_shader_pool?s_shader_pool->count:0);
    return TRUE;
}
static int shader_pool_on(void)
{ InitOnceExecuteOnce(&s_shader_pool_once,shader_pool_initialize,NULL,NULL);return s_shader_pool!=NULL; }
static void shader_enqueue(const rsx_shader_key* key)
{ if(s_shader_pool && rsx_fxc_pool_enqueue(s_shader_pool,key,shader_prefetch_generation))shader_queued++; }
static int shader_claim(const rsx_shader_key* key,ID3DBlob** blob)
{
    void* result=NULL;
    if(!rsx_fxc_pool_claim(s_shader_pool,key,&result))return 0;
    *blob=(ID3DBlob*)result;shader_claimed++;return 1;
}

static int shader_prefetch_duplicate(const void* state,size_t state_bytes,const void* program,size_t bytes)
{
    unsigned char key[RSX_PREFETCH_KEY_MAX];
    if(!state || !program || !bytes || state_bytes>sizeof(key) || bytes>sizeof(key)-state_bytes)return 0;
    memcpy(key,state,state_bytes);memcpy(key+state_bytes,program,bytes);
    rsx_shader_key input={key,state_bytes+bytes,"prefetch","main","ps_5_0",0,0};
    return rsx_prefetch_contains_or_add(&s_shader_seen,rsx_shader_key_hash(&input),key,input.bytes);
}
static void shader_pool_finish(void)
{
    if(s_shader_pool && rsx_fxc_pool_shutdown(s_shader_pool,5000))s_shader_pool=NULL;
}
#endif

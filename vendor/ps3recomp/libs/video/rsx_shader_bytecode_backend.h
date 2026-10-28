/* Successful bytecode and provenance are owned by the renderer coordinator. */
#ifndef RSX_SHADER_BYTECODE_BACKEND_H
#define RSX_SHADER_BYTECODE_BACKEND_H
#include "rsx_shader_cache.h"
#include "rsx_shader_disk_backend.h"
#include "rsx_shader_pool_backend.h"
static rsx_shader_cache s_fp_bytecode;
static u64 s_fp_bytecode_hits,s_fp_bytecode_misses,s_fp_bytecode_failures,s_fp_bytecode_refusals;
static void fp_blob_retain(void* context,void* pointer)
{ (void)context;ID3DBlob* b=(ID3DBlob*)pointer;b->lpVtbl->AddRef(b); }
static void fp_blob_release(void* context,void* pointer)
{ (void)context;ID3DBlob* b=(ID3DBlob*)pointer;b->lpVtbl->Release(b); }
static const rsx_shader_blob_ops s_fp_blob_ops={NULL,fp_blob_retain,fp_blob_release};
static unsigned s_fp_disk_origin;
static HRESULT fp_compile_uncached(const rsx_shader_key* key,ID3DBlob** blob,ID3DBlob** error)
{
    return D3DCompile(key->source,key->bytes,key->name,NULL,NULL,key->entry,key->target,
                       key->flags1,key->flags2,blob,error);
}
static HRESULT fp_compile_cached(u32 fp,const char* source,ID3DBlob** blob,ID3DBlob** error)
{
    rsx_shader_key key={source,strlen(source),"guest_fp","main","ps_5_0",0,0};
    *error=NULL;*blob=NULL;s_fp_disk_origin=0;
    *blob=(ID3DBlob*)rsx_shader_cache_get(&s_fp_bytecode,&key,&s_fp_blob_ops);
    if(*blob){s_fp_disk_origin=rsx_shader_cache_tag(&s_fp_bytecode,&key);if(!shader_prefetch_active)s_fp_bytecode_hits++;return S_OK;}
    if(shader_prefetch_active){
        if(shader_disk_load(&key,blob)){
            if(rsx_shader_cache_put(&s_fp_bytecode,&key,*blob,(*blob)->lpVtbl->GetBufferSize(*blob),&s_fp_blob_ops))
                rsx_shader_cache_set_tag(&s_fp_bytecode,&key,1);
            (*blob)->lpVtbl->Release(*blob);*blob=NULL;
        }else shader_enqueue(&key);
        return E_PENDING;
    }
    s_fp_bytecode_misses++;HRESULT hr;
    if(shader_disk_load(&key,blob)){hr=S_OK;s_fp_disk_origin=1;}
    else if(shader_claim(&key,blob)){hr=S_OK;shader_disk_store(&key,*blob);}
    else{
        hr=fp_compile_uncached(&key,blob,error);
        if(SUCCEEDED(hr) && *blob)shader_disk_store(&key,*blob);
    }
    if(SUCCEEDED(hr) && !*blob)hr=E_FAIL;
    if(FAILED(hr))s_fp_bytecode_failures++;
    if(SUCCEEDED(hr) && *blob){
        if(rsx_shader_cache_put(&s_fp_bytecode,&key,*blob,(*blob)->lpVtbl->GetBufferSize(*blob),&s_fp_blob_ops))
            rsx_shader_cache_set_tag(&s_fp_bytecode,&key,s_fp_disk_origin);
        else{
            s_fp_bytecode_refusals++;
            fprintf(stderr,"[FPCACHE] Successful fp=%08X bytecode not retained: allocation/budget refusal\n",fp);
        }
    }
    return hr;
}
static size_t s_vs_disk_source_bytes;
#define RSX_VS_DISK_SOURCE_MAX (32u*1024u*1024u)
static HRESULT shader_compile_vs(const char* source,ID3DBlob** blob,ID3DBlob** error,char** disk_source)
{
    rsx_shader_key key={source,strlen(source),"guest_vp2","main","vs_5_0",0,0};
    *blob=NULL;*error=NULL;*disk_source=NULL;
    if(shader_disk_load(&key,blob)){
        if(key.bytes+1<=RSX_VS_DISK_SOURCE_MAX-s_vs_disk_source_bytes){
            *disk_source=(char*)malloc(key.bytes+1);
            if(*disk_source){memcpy(*disk_source,source,key.bytes+1);return S_OK;}
        }
        (*blob)->lpVtbl->Release(*blob);*blob=NULL;
    }
    HRESULT hr=fp_compile_uncached(&key,blob,error);
    if(SUCCEEDED(hr) && !*blob)hr=E_FAIL;
    if(SUCCEEDED(hr) && *blob)shader_disk_store(&key,*blob);
    return hr;
}
static void shader_forget_vs_source(char* source)
{
    if(source){s_vs_disk_source_bytes-=strlen(source)+1;free(source);}
}
#endif

/* Renderer-owner disk coordination; workers never access this state.
 * Exact compiler inputs and the loaded compiler DLL define cache identity. */
#ifndef RSX_SHADER_DISK_BACKEND_H
#define RSX_SHADER_DISK_BACKEND_H
#include "rsx_shader_disk_cache.h"
static unsigned shader_disk_hits,shader_disk_stores;
static INIT_ONCE s_shader_disk_once=INIT_ONCE_STATIC_INIT;
static rsx_shader_disk_cache s_shader_disk;
static wchar_t s_shader_disk_path[1024];
static DWORD s_shader_disk_error;
static const char* s_shader_disk_stage="initialize";
static int s_shader_disk_requested;
static volatile LONG s_shader_disk_notice;
static BOOL CALLBACK shader_disk_initialize(PINIT_ONCE once,PVOID arg,PVOID* result)
{
    (void)once;(void)arg;(void)result;
    unsigned char compiler[32];wchar_t* directory=s_shader_disk_path;
    DWORD n=GetEnvironmentVariableW(L"RSX_SHADER_DISK_CACHE",directory,1024);
    if(n && n<1024 && !wcscmp(directory,L"0"))return TRUE;
    s_shader_disk_requested=1;
    if(n>=1024){wcscpy(directory,L"<RSX_SHADER_DISK_CACHE too long>");s_shader_disk_error=ERROR_INSUFFICIENT_BUFFER;return TRUE;}
    if(!n){
        n=GetEnvironmentVariableW(L"LOCALAPPDATA",directory,1024);
        if(!n || n>=900){wcscpy(directory,L"<LOCALAPPDATA unavailable>");s_shader_disk_error=ERROR_BAD_PATHNAME;return TRUE;}
        wcscat(directory,L"\\ps3recomp\\shader-cache-v2");
    }
    s_shader_disk_stage="compiler-identity";
    if(!rsx_shader_disk_export_id(D3DCOMPILER_DLL_W,"D3DCompile",compiler)){
        s_shader_disk_error=GetLastError();return TRUE;
    }
    s_shader_disk_stage="directory";
    if(!rsx_shader_disk_init(&s_shader_disk,directory,compiler))s_shader_disk_error=GetLastError();
    return TRUE; /* Cache refusal always falls back to compilation. */
}
static void shader_disk_ready(void)
{ InitOnceExecuteOnce(&s_shader_disk_once,shader_disk_initialize,NULL,NULL); }
static int shader_disk_load(const rsx_shader_key* key,ID3DBlob** output)
{
    shader_disk_ready();void* bytes=NULL;size_t count=0;
    if(!rsx_shader_disk_load(&s_shader_disk,key,&bytes,&count))return 0;
    ID3DBlob* blob=NULL;HRESULT hr=D3DCreateBlob(count,&blob);
    if(FAILED(hr) || !blob){if(blob)blob->lpVtbl->Release(blob);free(bytes);return 0;}
    memcpy(blob->lpVtbl->GetBufferPointer(blob),bytes,count);*output=blob;shader_disk_hits++;
    free(bytes);return 1;
}
static void shader_disk_store(const rsx_shader_key* key,ID3DBlob* blob)
{
    shader_disk_ready();if(!blob || !s_shader_disk_requested)return;
    DWORD error=s_shader_disk_error;const char* stage=s_shader_disk_stage;
    if(s_shader_disk.enabled){
        if(rsx_shader_disk_store(&s_shader_disk,key,blob->lpVtbl->GetBufferPointer(blob),
            blob->lpVtbl->GetBufferSize(blob))){shader_disk_stores++;return;}
        error=GetLastError();stage="store";
    }
    if(InterlockedCompareExchange(&s_shader_disk_notice,1,0)==0){
        char path[4096];
        if(!WideCharToMultiByte(CP_UTF8,0,s_shader_disk_path,-1,path,sizeof(path),NULL,NULL))strcpy(path,"<path conversion failed>");
        fprintf(stderr,"[SHADERCACHE] first store failure stage=%s path=\"%s\" GetLastError=%lu\n",
            stage,path,(unsigned long)(error?error:ERROR_GEN_FAILURE));
    }
}
static int shader_cache_stats(void)
{
    static int value=-1;
    if(value<0){const char* e=getenv("RSX_SHADER_CACHE_STATS");value=e && !strcmp(e,"1");}
    return value;
}
#endif

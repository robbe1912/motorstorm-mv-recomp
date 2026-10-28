/* Versioned, exact compiler-input cache. Windows file operations use Unicode
 * paths; temporary files are unique and replaced in the same directory.
 * Cache failures never replace compilation failures or authorize a draw. */
#ifndef RSX_SHADER_DISK_CACHE_H
#define RSX_SHADER_DISK_CACHE_H
#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#include <stdio.h>
#include <wchar.h>
#include "rsx_shader_cache.h"
#define RSX_SHADER_DISK_SOURCE_MAX (1024u*1024u)
#define RSX_SHADER_DISK_BLOB_MAX (16u*1024u*1024u)
#define RSX_SHADER_DISK_HEADER 120u
typedef struct { wchar_t directory[1024];unsigned char compiler[32];int enabled;SRWLOCK io; } rsx_shader_disk_cache;
static INIT_ONCE rsx_disk_hash_once=INIT_ONCE_STATIC_INIT;
static BCRYPT_ALG_HANDLE rsx_disk_algorithm;
static volatile LONG64 rsx_disk_temp_counter;
static BOOL CALLBACK rsx_disk_hash_init(PINIT_ONCE once,PVOID arg,PVOID* result)
{
    (void)once;(void)arg;(void)result;
    if(BCryptOpenAlgorithmProvider(&rsx_disk_algorithm,BCRYPT_SHA256_ALGORITHM,NULL,0)<0)
        rsx_disk_algorithm=NULL;
    return TRUE;
}
static int rsx_disk_error(DWORD error)
{ SetLastError(error);return 0; }
static int rsx_shader_digest(const void* data,size_t size,unsigned char out[32])
{
    if(!data || size>MAXDWORD || !InitOnceExecuteOnce(&rsx_disk_hash_once,rsx_disk_hash_init,NULL,NULL) ||
       !rsx_disk_algorithm)return rsx_disk_error(ERROR_INVALID_FUNCTION);
    DWORD object_bytes=0,got=0;
    if(BCryptGetProperty(rsx_disk_algorithm,BCRYPT_OBJECT_LENGTH,(PUCHAR)&object_bytes,
        sizeof(object_bytes),&got,0)<0 || !object_bytes || object_bytes>65536)return rsx_disk_error(ERROR_INVALID_DATA);
    PUCHAR object=(PUCHAR)malloc(object_bytes);if(!object)return rsx_disk_error(ERROR_NOT_ENOUGH_MEMORY);
    BCRYPT_HASH_HANDLE hash=NULL;int ok=0;
    if(BCryptCreateHash(rsx_disk_algorithm,&hash,object,object_bytes,NULL,0,0)>=0 &&
       BCryptHashData(hash,(PUCHAR)data,(ULONG)size,0)>=0 &&
       BCryptFinishHash(hash,out,32,0)>=0)ok=1;
    if(hash)BCryptDestroyHash(hash);free(object);
    if(!ok)SetLastError(ERROR_CRC);return ok;
}
static uint32_t rsx_disk_u32(const unsigned char* p)
{ return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static void rsx_disk_put32(unsigned char* p,uint32_t value)
{ for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(value>>(8*i)); }
static int rsx_shader_disk_dxbc(const void* bytes,size_t size)
{
    const unsigned char* p=(const unsigned char*)bytes;
    if(!p || size<36 || size>RSX_SHADER_DISK_BLOB_MAX || memcmp(p,"DXBC",4) ||
       rsx_disk_u32(p+24)!=size)return 0;
    uint32_t count=rsx_disk_u32(p+28);
    if(!count || count>(size-32)/4 || count>256)return 0;
    size_t first=32+(size_t)count*4;
    for(uint32_t i=0;i<count;i++){
        uint32_t offset=rsx_disk_u32(p+32+4*i);
        if(offset<first || offset>size-8)return 0;
        uint32_t chunk=rsx_disk_u32(p+offset+4);
        if(chunk>size-offset-8)return 0;
    }
    return 1;
}
static int rsx_shader_disk_directory(const wchar_t* directory,wchar_t out[1024])
{
    DWORD count=GetFullPathNameW(directory,1024,out,NULL);
    if(!count)return 0;
    if(count>=900 || count<3 || out[1]!=L':' || out[2]!=L'\\')return rsx_disk_error(ERROR_BAD_PATHNAME);
    while(count>3 && out[count-1]==L'\\')out[--count]=0;
    /* Never traverse a reparse point while creating an owned cache path. */
    for(DWORD i=3;i<=count;i++)if(out[i]==L'\\' || !out[i]){
        wchar_t saved=out[i];out[i]=0;
        DWORD attributes=GetFileAttributesW(out);
        if(attributes==INVALID_FILE_ATTRIBUTES){
            if(!CreateDirectoryW(out,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS){out[i]=saved;return 0;}
            attributes=GetFileAttributesW(out);
        }
        out[i]=saved;
        if(attributes==INVALID_FILE_ATTRIBUTES)return 0;
        if(!(attributes&FILE_ATTRIBUTE_DIRECTORY))return rsx_disk_error(ERROR_DIRECTORY);
        if(attributes&FILE_ATTRIBUTE_REPARSE_POINT)return rsx_disk_error(ERROR_ACCESS_DENIED);
    }
    return 1;
}
/* The address must belong to the DLL, not the executable's import thunk. */
static int rsx_shader_disk_compiler_id(const void* address,unsigned char out[32])
{
    HMODULE module=NULL;wchar_t path[1024];
    if(!address || !out)return rsx_disk_error(ERROR_INVALID_PARAMETER);
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        (LPCWSTR)address,&module))return 0;
    if(module==GetModuleHandleW(NULL))return rsx_disk_error(ERROR_INVALID_ADDRESS);
    DWORD count=GetModuleFileNameW(module,path,1024);if(!count)return 0;
    if(count>=1024)return rsx_disk_error(ERROR_INSUFFICIENT_BUFFER);
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                           NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return 0;
    LARGE_INTEGER size;void* bytes=NULL;int ok=0;DWORD got=0,error=ERROR_SUCCESS;
    if(!GetFileSizeEx(file,&size)){error=GetLastError();goto done;}
    if(size.QuadPart<=0 || size.QuadPart>64u*1024u*1024u){error=ERROR_FILE_TOO_LARGE;goto done;}
    bytes=malloc((size_t)size.QuadPart);if(!bytes){error=ERROR_NOT_ENOUGH_MEMORY;goto done;}
    if(!ReadFile(file,bytes,(DWORD)size.QuadPart,&got,NULL)){error=GetLastError();goto done;}
    if(got!=(DWORD)size.QuadPart){error=ERROR_HANDLE_EOF;goto done;}
    ok=rsx_shader_digest(bytes,(size_t)size.QuadPart,out);if(!ok)error=GetLastError();
done:
    free(bytes);CloseHandle(file);if(!ok)SetLastError(error);return ok;
}
/* Resolve the already-loaded compiler export. Taking &D3DCompile directly can
 * name a linker-created import thunk inside the EXE on Windows. */
static int rsx_shader_disk_export_id(const wchar_t* dll,const char* name,unsigned char out[32])
{
    HMODULE module=GetModuleHandleW(dll);if(!module)return 0;
    FARPROC address=GetProcAddress(module,name);if(!address)return 0;
    return rsx_shader_disk_compiler_id((const void*)address,out);
}
static int rsx_shader_disk_init(rsx_shader_disk_cache* c,const wchar_t* directory,
                                const unsigned char compiler[32])
{
    memset(c,0,sizeof(*c));InitializeSRWLock(&c->io);
    if(!directory || !*directory || !compiler)return rsx_disk_error(ERROR_INVALID_PARAMETER);
    if(!rsx_shader_disk_directory(directory,c->directory))return 0;
    memcpy(c->compiler,compiler,32);c->enabled=1;return 1;
}
static int rsx_shader_disk_key(const rsx_shader_disk_cache* c,const rsx_shader_key* k,
                               unsigned char** bytes,size_t* size,unsigned char hash[32])
{
    if(!c || !c->enabled || !k || !k->source || !k->bytes || k->bytes>RSX_SHADER_DISK_SOURCE_MAX ||
       !k->name || !k->entry || !k->target)return rsx_disk_error(ERROR_INVALID_PARAMETER);
    size_t n=strlen(k->name),e=strlen(k->entry),t=strlen(k->target);
    if(n>255 || e>255 || t>255)return rsx_disk_error(ERROR_INVALID_PARAMETER);
    *size=32+24+n+e+t+k->bytes;
    unsigned char* p=(unsigned char*)malloc(*size);if(!p)return rsx_disk_error(ERROR_NOT_ENOUGH_MEMORY);
    memcpy(p,c->compiler,32);
    uint32_t fields[6]={k->flags1,k->flags2,(uint32_t)n,(uint32_t)e,(uint32_t)t,(uint32_t)k->bytes};
    for(unsigned i=0;i<6;i++)rsx_disk_put32(p+32+4*i,fields[i]);
    size_t at=56;memcpy(p+at,k->name,n);at+=n;memcpy(p+at,k->entry,e);at+=e;
    memcpy(p+at,k->target,t);at+=t;memcpy(p+at,k->source,k->bytes);
    if(!rsx_shader_digest(p,*size,hash)){free(p);return 0;}
    *bytes=p;return 1;
}
static int rsx_shader_disk_path(const rsx_shader_disk_cache* c,const unsigned char hash[32],wchar_t out[1200])
{
    size_t n=wcslen(c->directory);if(n>900)return rsx_disk_error(ERROR_BAD_PATHNAME);
    memcpy(out,c->directory,n*sizeof(wchar_t));out[n++]=L'\\';
    static const wchar_t hex[]=L"0123456789abcdef";
    for(unsigned i=0;i<32;i++){out[n++]=hex[hash[i]>>4];out[n++]=hex[hash[i]&15];}
    memcpy(out+n,L".bin",5*sizeof(wchar_t));return 1;
}
static int rsx_disk_read(HANDLE file,void* data,size_t size)
{ DWORD n=0;return size<=MAXDWORD && ReadFile(file,data,(DWORD)size,&n,NULL) && n==size; }
static int rsx_disk_write(HANDLE file,const void* data,size_t size)
{ DWORD n=0;
  if(size>MAXDWORD)return rsx_disk_error(ERROR_INVALID_PARAMETER);
  if(!WriteFile(file,data,(DWORD)size,&n,NULL))return 0;
  return n==size?1:rsx_disk_error(ERROR_WRITE_FAULT); }
static int rsx_shader_disk_load(rsx_shader_disk_cache* c,const rsx_shader_key* k,
                                void** output,size_t* output_bytes)
{
    if(!output || !output_bytes)return 0;*output=NULL;*output_bytes=0;
    unsigned char *key=NULL,*stored=NULL,*blob=NULL,digest[32],check[32],header[RSX_SHADER_DISK_HEADER];
    size_t key_bytes=0;wchar_t path[1200];HANDLE file=INVALID_HANDLE_VALUE;int ok=0,locked=0;
    if(!rsx_shader_disk_key(c,k,&key,&key_bytes,digest) || !rsx_shader_disk_path(c,digest,path))goto done;
    AcquireSRWLockShared(&c->io);locked=1;
    file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,
                     FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
    if(file==INVALID_HANDLE_VALUE)goto done;
    BY_HANDLE_FILE_INFORMATION info;LARGE_INTEGER size;
    if(!GetFileInformationByHandle(file,&info) || (info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT) ||
       !GetFileSizeEx(file,&size) || !rsx_disk_read(file,header,sizeof(header)))goto done;
    uint32_t stored_key=rsx_disk_u32(header+16),stored_blob=rsx_disk_u32(header+20);
    if(memcmp(header,"RSXDXB02",8) || rsx_disk_u32(header+8)!=2 || rsx_disk_u32(header+12) ||
       stored_key!=key_bytes || !stored_blob || stored_blob>RSX_SHADER_DISK_BLOB_MAX ||
       size.QuadPart!=(LONGLONG)(sizeof(header)+key_bytes+stored_blob) ||
       memcmp(header+24,digest,32) || memcmp(header+88,c->compiler,32))goto done;
    stored=(unsigned char*)malloc(key_bytes);blob=(unsigned char*)malloc(stored_blob);
    if(!stored || !blob || !rsx_disk_read(file,stored,key_bytes) || memcmp(stored,key,key_bytes) ||
       !rsx_disk_read(file,blob,stored_blob) || !rsx_shader_digest(blob,stored_blob,check) ||
       memcmp(check,header+56,32) || !rsx_shader_disk_dxbc(blob,stored_blob))goto done;
    *output=blob;blob=NULL;*output_bytes=stored_blob;ok=1;
done:
    if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
    if(locked)ReleaseSRWLockShared(&c->io);
    free(blob);free(stored);free(key);return ok;
}
static int rsx_shader_disk_store(rsx_shader_disk_cache* c,const rsx_shader_key* k,
                                 const void* blob,size_t blob_bytes)
{
    if(!rsx_shader_disk_dxbc(blob,blob_bytes))return rsx_disk_error(ERROR_INVALID_DATA);
    unsigned char *key=NULL,digest[32],header[RSX_SHADER_DISK_HEADER]={0};
    size_t key_bytes=0;wchar_t path[1200],temporary[1280]={0};HANDLE file=INVALID_HANDLE_VALUE;int ok=0;DWORD error=ERROR_SUCCESS;
    if(!rsx_shader_disk_key(c,k,&key,&key_bytes,digest) || !rsx_shader_disk_path(c,digest,path))goto done;
    memcpy(header,"RSXDXB02",8);rsx_disk_put32(header+8,2);rsx_disk_put32(header+16,(uint32_t)key_bytes);
    rsx_disk_put32(header+20,(uint32_t)blob_bytes);memcpy(header+24,digest,32);memcpy(header+88,c->compiler,32);
    if(!rsx_shader_digest(blob,blob_bytes,header+56))goto done;
    _snwprintf(temporary,1280,L"%s.%lu.%lu.%llu.tmp",path,GetCurrentProcessId(),GetCurrentThreadId(),
               (unsigned long long)InterlockedIncrement64(&rsx_disk_temp_counter));
    temporary[1279]=0;
    file=CreateFileW(temporary,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE && GetLastError()==ERROR_PATH_NOT_FOUND){
        /* A disposable cache directory may have been removed since init.
         * Recreate/validate it once; never bypass the reparse-point refusal. */
        wchar_t directory[1024];
        if(!rsx_shader_disk_directory(c->directory,directory))goto done;
        file=CreateFileW(temporary,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
    }
    if(file==INVALID_HANDLE_VALUE)goto done;
    ok=rsx_disk_write(file,header,sizeof(header)) && rsx_disk_write(file,key,key_bytes) &&
       rsx_disk_write(file,blob,blob_bytes);
    if(!ok)error=GetLastError();
    if(!CloseHandle(file) && ok){error=GetLastError();ok=0;}file=INVALID_HANDLE_VALUE;
    /* Same-directory rename; never COPY_ALLOWED or expose a partial final file.
     * A power-loss/corrupt file is a checked miss on the next load. */
    if(ok){
        /* A reader in this cache context must close its final-file handle before
         * replacement. Other processes/contexts may still deny a rename: that
         * is a disposable-cache miss, with the previous checked file retained. */
        AcquireSRWLockExclusive(&c->io);
        ok=MoveFileExW(temporary,path,MOVEFILE_REPLACE_EXISTING)!=0;
        if(!ok)error=GetLastError();
        ReleaseSRWLockExclusive(&c->io);
    }
done:
    if(!ok && !error)error=GetLastError();
    if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
    if(!ok && temporary[0])DeleteFileW(temporary);
    free(key);if(!ok)SetLastError(error?error:ERROR_GEN_FAILURE);return ok;
}
static void rsx_shader_disk_remove(rsx_shader_disk_cache* c,const rsx_shader_key* k)
{
    unsigned char* key=NULL,digest[32];size_t size=0;wchar_t path[1200];
    if(rsx_shader_disk_key(c,k,&key,&size,digest) && rsx_shader_disk_path(c,digest,path)){
        AcquireSRWLockExclusive(&c->io);DeleteFileW(path);ReleaseSRWLockExclusive(&c->io);
    }
    free(key);
}
#endif
#endif

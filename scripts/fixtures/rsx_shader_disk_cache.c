/* Authored shader/cache bytes; no game assets or reconstructed instructions. */
#include <windows.h>
#include <d3dcompiler.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_shader_disk_cache.h"
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL line=%d %s\n",__LINE__,#x);return 1;}}while(0)
static const char source[]="float4 main():SV_TARGET{return float4(1,0,0,1);}";
static rsx_shader_disk_cache cache;
static rsx_shader_key key={source,sizeof(source)-1,"authored","main","ps_5_0",0,0};
static const void* bytecode;static size_t bytecode_size;static volatile LONG thread_errors;
static DWORD WINAPI writer(LPVOID unused){
 (void)unused;
 for(unsigned i=0;i<20;i++)if(!rsx_shader_disk_store(&cache,&key,bytecode,bytecode_size))InterlockedIncrement(&thread_errors);
 return 0;
}
int main(int argc,char**argv)
{
 unsigned checks=0;CHECK(argc==2);
 wchar_t directory[1024];CHECK(MultiByteToWideChar(CP_UTF8,0,argv[1],-1,directory,1024)>0);
 unsigned char compiler[32];
 CHECK(!rsx_shader_disk_compiler_id((const void*)D3DCompile,compiler));
 CHECK(GetLastError()==ERROR_INVALID_ADDRESS);
 CHECK(rsx_shader_disk_export_id(D3DCOMPILER_DLL_W,"D3DCompile",compiler));
 unsigned char direct[32];HMODULE dll=GetModuleHandleW(D3DCOMPILER_DLL_W);CHECK(dll!=NULL);
 CHECK(rsx_shader_disk_compiler_id((const void*)GetProcAddress(dll,"D3DCompile"),direct));
 CHECK(!memcmp(compiler,direct,32));
 CHECK(rsx_shader_disk_init(&cache,directory,compiler));
 ID3DBlob *blob=NULL,*error=NULL;
 CHECK(SUCCEEDED(D3DCompile(source,sizeof(source)-1,"authored",NULL,NULL,"main","ps_5_0",0,0,&blob,&error)) && blob);
 if(error)error->lpVtbl->Release(error);
 bytecode=blob->lpVtbl->GetBufferPointer(blob);bytecode_size=blob->lpVtbl->GetBufferSize(blob);
 void* data=NULL;size_t bytes=0;
 CHECK(!rsx_shader_disk_load(&cache,&key,&data,&bytes));
 CHECK(rsx_shader_disk_store(&cache,&key,bytecode,bytecode_size));
 CHECK(rsx_shader_disk_load(&cache,&key,&data,&bytes) && bytes==bytecode_size && !memcmp(data,bytecode,bytes));free(data);
 rsx_shader_key changed=key;changed.flags1=1;
 CHECK(!rsx_shader_disk_load(&cache,&changed,&data,&bytes));
 changed=key;changed.entry="other";CHECK(!rsx_shader_disk_load(&cache,&changed,&data,&bytes));
 changed=key;changed.target="vs_5_0";CHECK(!rsx_shader_disk_load(&cache,&changed,&data,&bytes));
 static const char other[]="float4 main():SV_TARGET{return float4(0,1,0,1);}";
 changed=key;changed.source=other;changed.bytes=sizeof(other)-1;
 CHECK(!rsx_shader_disk_load(&cache,&changed,&data,&bytes));
 unsigned char *encoded=NULL,hash[32];size_t encoded_size;
 CHECK(rsx_shader_disk_key(&cache,&key,&encoded,&encoded_size,hash));
 wchar_t path[1200];CHECK(rsx_shader_disk_path(&cache,hash,path));
 FILE*f=_wfopen(path,L"r+b");CHECK(f!=NULL);CHECK(!fseek(f,-1,SEEK_END));int last=fgetc(f);
 CHECK(last!=EOF);CHECK(!fseek(f,-1,SEEK_END));CHECK(fputc(last^1,f)!=EOF);CHECK(!fclose(f));
 CHECK(!rsx_shader_disk_load(&cache,&key,&data,&bytes)); /* payload integrity */
 CHECK(rsx_shader_disk_store(&cache,&key,bytecode,bytecode_size));
 f=_wfopen(path,L"ab");CHECK(f!=NULL);CHECK(fputc(1,f)!=EOF);CHECK(!fclose(f));
 CHECK(!rsx_shader_disk_load(&cache,&key,&data,&bytes)); /* no trailing junk */
 CHECK(rsx_shader_disk_store(&cache,&key,bytecode,bytecode_size));
 /* Force a digest/name collision: header claims changed key, serialized full
  * key remains original. Correct source comparison must still reject it. */
 unsigned char* other_key=NULL,other_hash[32];size_t other_size;
 CHECK(rsx_shader_disk_key(&cache,&changed,&other_key,&other_size,other_hash));
 wchar_t collision[1200];CHECK(rsx_shader_disk_path(&cache,other_hash,collision));CHECK(CopyFileW(path,collision,FALSE));
 f=_wfopen(collision,L"r+b");CHECK(f!=NULL);CHECK(!fseek(f,24,SEEK_SET));
 CHECK(fwrite(other_hash,1,32,f)==32);CHECK(!fclose(f));
 CHECK(!rsx_shader_disk_load(&cache,&changed,&data,&bytes));
 free(other_key);free(encoded);
 /* A correct blob hash alone does not make a malformed DXBC container valid. */
 unsigned char* bad=(unsigned char*)malloc(bytecode_size);CHECK(bad!=NULL);memcpy(bad,bytecode,bytecode_size);
 rsx_disk_put32(bad+24,(uint32_t)bytecode_size-1);
 CHECK(!rsx_shader_disk_store(&cache,&key,bad,bytecode_size));free(bad);
 HANDLE a=CreateThread(NULL,0,writer,NULL,0,NULL),b=CreateThread(NULL,0,writer,NULL,0,NULL);
 CHECK(a && b);
 for(unsigned i=0;i<40;i++){
  if(rsx_shader_disk_load(&cache,&key,&data,&bytes)){CHECK(bytes==bytecode_size && !memcmp(data,bytecode,bytes));free(data);}
 }
 CHECK(WaitForSingleObject(a,10000)==WAIT_OBJECT_0);CHECK(WaitForSingleObject(b,10000)==WAIT_OBJECT_0);
 CloseHandle(a);CloseHandle(b);CHECK(thread_errors==0);
 CHECK(rsx_shader_disk_load(&cache,&key,&data,&bytes));free(data);
 rsx_shader_disk_remove(&cache,&key);CHECK(!rsx_shader_disk_load(&cache,&key,&data,&bytes));
 /* Initialization creates nested directories; store recreates a removed leaf. */
 wchar_t leaf[1200];_snwprintf(leaf,1200,L"%ls\\recreated\\leaf",directory);
 rsx_shader_disk_cache recreated;CHECK(rsx_shader_disk_init(&recreated,leaf,compiler));
 CHECK(RemoveDirectoryW(leaf));CHECK(rsx_shader_disk_store(&recreated,&key,bytecode,bytecode_size));
 CHECK(rsx_shader_disk_load(&recreated,&key,&data,&bytes));free(data);
 rsx_shader_disk_remove(&recreated,&key);CHECK(RemoveDirectoryW(leaf));
 HANDLE blocked=CreateFileW(leaf,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);CHECK(blocked!=INVALID_HANDLE_VALUE);CloseHandle(blocked);
 CHECK(!rsx_shader_disk_store(&recreated,&key,bytecode,bytecode_size));
 CHECK(GetLastError()==ERROR_PATH_NOT_FOUND || GetLastError()==ERROR_DIRECTORY);
 CHECK(DeleteFileW(leaf));
 blob->lpVtbl->Release(blob);
 printf("PASS disk key/integrity/collision/atomic checks=%u\n",checks);return 0;
}

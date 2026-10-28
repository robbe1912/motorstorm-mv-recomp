/* Authored HLSL; extract the actual backend disk initialization/load/store. */
#include <windows.h>
#include <d3dcompiler.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_shader_disk_cache.h"
#include "rsx_shader_disk_backend.h"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line=%d %s\n",__LINE__,#x);return 1;}}while(0)
int main(int argc,char** argv)
{
 CHECK(argc==3);CHECK(SetEnvironmentVariableA("RSX_SHADER_DISK_CACHE",argv[1]));
 static const char source[]="float4 main():SV_TARGET{return float4(1,0,0,1);}";
 rsx_shader_key key={source,sizeof(source)-1,"authored-backend","main","ps_5_0",0,0};
 ID3DBlob *blob=NULL,*error=NULL;
 if(!strcmp(argv[2],"warm")){
  CHECK(shader_disk_load(&key,&blob));CHECK(shader_disk_hits==1 && shader_disk_stores==0);
 }else{
  CHECK(!shader_disk_load(&key,&blob));
  CHECK(SUCCEEDED(D3DCompile(source,sizeof(source)-1,"authored-backend",NULL,NULL,"main","ps_5_0",0,0,&blob,&error)) && blob);
  if(error)error->lpVtbl->Release(error);
  if(!strcmp(argv[2],"store-blocked")){
   CHECK(s_shader_disk.enabled);CHECK(RemoveDirectoryW(s_shader_disk.directory));
   HANDLE file=CreateFileW(s_shader_disk.directory,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
   CHECK(file!=INVALID_HANDLE_VALUE);CloseHandle(file);
  }
  shader_disk_store(&key,blob);shader_disk_store(&key,blob);
  if(!strcmp(argv[2],"cold")){
   CHECK(s_shader_disk.enabled && shader_disk_stores==2 && !s_shader_disk_notice);
  }else if(!strcmp(argv[2],"blocked")){
   CHECK(s_shader_disk_requested && !s_shader_disk.enabled && s_shader_disk_notice==1 && !shader_disk_stores);
   CHECK(s_shader_disk_error==ERROR_DIRECTORY || s_shader_disk_error==ERROR_ALREADY_EXISTS);
  }else if(!strcmp(argv[2],"store-blocked")){
   CHECK(s_shader_disk.enabled && s_shader_disk_notice==1 && !shader_disk_stores);
   CHECK(DeleteFileW(s_shader_disk.directory));
  }else if(!strcmp(argv[2],"disabled")){
   CHECK(!s_shader_disk_requested && !s_shader_disk.enabled && !s_shader_disk_notice && !shader_disk_stores);
  }else CHECK(0);
 }
 CHECK(blob->lpVtbl->GetBufferSize(blob)>0);blob->lpVtbl->Release(blob);
 printf("PASS production disk mode=%s hits=%u stores=%u\n",argv[2],shader_disk_hits,shader_disk_stores);return 0;
}

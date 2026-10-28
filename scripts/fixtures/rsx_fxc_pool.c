#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_fxc_pool.h"
static DWORD owner_thread;static volatile LONG wrong_compile_thread;
static volatile LONG compiles,releases,live;static HANDLE entered,gate;
static int compile(void* user,const rsx_shader_key* key,void** out,size_t* bytes){
 (void)user;if(GetCurrentThreadId()==owner_thread)InterlockedIncrement(&wrong_compile_thread);InterlockedIncrement(&compiles);
 if(!strcmp(key->entry,"held")){SetEvent(entered);WaitForSingleObject(gate,5000);}
 unsigned* value=(unsigned*)malloc(sizeof(unsigned));if(!value)return 0;
 *value=key->flags1;*out=value;*bytes=sizeof(*value);InterlockedIncrement(&live);
 return strcmp(key->entry,"fail")!=0;
}
static void release(void* user,void* blob){(void)user;free(blob);InterlockedIncrement(&releases);InterlockedDecrement(&live);}
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL line=%d %s\n",__LINE__,#x);return 1;}}while(0)
typedef struct {rsx_fxc_pool*p;rsx_shader_key key;void* blob;int result;} claim_args;
static DWORD WINAPI claim_thread(LPVOID arg){claim_args*a=(claim_args*)arg;a->result=rsx_fxc_pool_claim(a->p,&a->key,&a->blob);return 0;}
int main(void){
 owner_thread=GetCurrentThreadId();unsigned checks=0;CHECK(rsx_fxc_default_threads(1)==0);CHECK(rsx_fxc_default_threads(2)==1);
 CHECK(rsx_fxc_default_threads(8)==7);CHECK(rsx_fxc_default_threads(24)==8);
 rsx_fxc_pool*p=rsx_fxc_pool_create(2,compile,release,NULL);CHECK(p!=NULL);
 rsx_shader_key a={"authored",8,"fixture","main","ps_5_0",17,0};void* blob=NULL;
 CHECK(rsx_fxc_pool_enqueue(p,&a,1));CHECK(rsx_fxc_pool_enqueue(p,&a,1));
 CHECK(rsx_fxc_pool_claim(p,&a,&blob)&&*(unsigned*)blob==17);release(NULL,blob);
 CHECK(compiles==1 && live==0);
 rsx_shader_key b=a;b.flags1=19;
 CHECK(rsx_fxc_pool_enqueue(p,&a,2));CHECK(rsx_fxc_pool_enqueue(p,&b,2));
 CHECK(rsx_fxc_pool_claim(p,&b,&blob)&&*(unsigned*)blob==19);release(NULL,blob);
 CHECK(rsx_fxc_pool_claim(p,&a,&blob)&&*(unsigned*)blob==17);release(NULL,blob);
 rsx_shader_key fail=a;fail.entry="fail";
 CHECK(rsx_fxc_pool_enqueue(p,&fail,3));CHECK(!rsx_fxc_pool_claim(p,&fail,&blob));
 CHECK(live==0); /* Failure result is released; caller may compile synchronously. */
 entered=CreateEventW(NULL,TRUE,FALSE,NULL);gate=CreateEventW(NULL,TRUE,FALSE,NULL);
 rsx_shader_key held=a;held.entry="held";
 CHECK(rsx_fxc_pool_enqueue(p,&held,4));CHECK(WaitForSingleObject(entered,5000)==WAIT_OBJECT_0);
 claim_args args={p,held,NULL,0};HANDLE waiter=CreateThread(NULL,0,claim_thread,&args,0,NULL);
 for(unsigned i=0;i<100;i++){EnterCriticalSection(&p->lock);unsigned ready=p->claimers;LeaveCriticalSection(&p->lock);if(ready)break;Sleep(1);}
 EnterCriticalSection(&p->lock);unsigned leased=p->claimers;LeaveCriticalSection(&p->lock);CHECK(leased==1);
 CHECK(!rsx_fxc_pool_claim(p,&held,&blob)); /* Second claimant cannot own/free it. */
 CHECK(rsx_fxc_pool_enqueue(p,&a,40));CHECK(!rsx_fxc_pool_shutdown(p,0));
 SetEvent(gate);CHECK(WaitForSingleObject(waiter,5000)==WAIT_OBJECT_0);
 CHECK(args.result==1 && args.blob!=NULL);release(NULL,args.blob);
 CHECK(rsx_fxc_pool_shutdown(p,5000));CloseHandle(waiter);CloseHandle(gate);CloseHandle(entered);
 CHECK(live==0);
 /* Reclaim unclaimed completed jobs while retaining exact-key behavior. */
 p=rsx_fxc_pool_create(1,compile,release,NULL);CHECK(p!=NULL);
 for(unsigned i=0;i<100;i++){
   rsx_shader_key k=a;k.flags1=i;
   CHECK(rsx_fxc_pool_enqueue(p,&k,100+i));
   if(i%3==0){CHECK(rsx_fxc_pool_claim(p,&k,&blob));release(NULL,blob);}
 }
 CHECK(rsx_fxc_pool_shutdown(p,5000));CHECK(live==0);
 CHECK(!wrong_compile_thread);
 printf("PASS pool checks=%u compiles=%ld releases=%ld\n",checks,compiles,releases);return 0;
}

/* Operation benchmark of the actual selected Windows wait branches. No game. */
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL %s error=%lu\n",#x,GetLastError());exit(7);}}while(0)
#include "../native_short_sleep.c"
static LARGE_INTEGER s_qpc_freq;
static unsigned requested_us;
static void ensure_qpc_init(void){}
static void actual_wait(uint64_t usec){ /* ACTUAL_WINDOWS_BRANCH */ }
static uint64_t thread_cpu(void){FILETIME a,b,k,u;CHECK(GetThreadTimes(GetCurrentThread(),&a,&b,&k,&u));ULARGE_INTEGER x,y;x.LowPart=k.dwLowDateTime;x.HighPart=k.dwHighDateTime;y.LowPart=u.dwLowDateTime;y.HighPart=u.dwHighDateTime;return x.QuadPart+y.QuadPart;}
static uint64_t now(void){LARGE_INTEGER q;CHECK(QueryPerformanceCounter(&q));return q.QuadPart;}
static int order(const void*a,const void*b){uint64_t x=*(const uint64_t*)a,y=*(const uint64_t*)b;return(x>y)-(x<y);}
static DWORD WINAPI bench(LPVOID arg){unsigned count=(unsigned)(uintptr_t)arg;CHECK(QueryPerformanceFrequency(&s_qpc_freq));DWORD_PTR allowed,system;CHECK(GetProcessAffinityMask(GetCurrentProcess(),&allowed,&system));DWORD_PTR bit=allowed&(~allowed+1),old=SetThreadAffinityMask(GetCurrentThread(),bit);CHECK(old);uint64_t* deltas=(uint64_t*)calloc(count,sizeof(uint64_t));CHECK(deltas);
 for(int i=0;i<32;i++)actual_wait(requested_us);
 ULONG64 cycles0,cycles1;CHECK(QueryThreadCycleTime(GetCurrentThread(),&cycles0));uint64_t c0=thread_cpu(),t0=now();for(unsigned i=0;i<count;i++){uint64_t b=now();actual_wait(requested_us);deltas[i]=now()-b;CHECK(deltas[i]*1000000>=(uint64_t)requested_us*(uint64_t)s_qpc_freq.QuadPart);}uint64_t elapsed=now()-t0,cpu=thread_cpu()-c0;CHECK(QueryThreadCycleTime(GetCurrentThread(),&cycles1));qsort(deltas,count,sizeof(uint64_t),order);
 printf("{\"operations\":%u,\"warmups\":32,\"affinity\":%llu,\"requested_us\":%u,\"wall_ms\":%.6f,\"cpu_ms\":%.6f,\"thread_cycles\":%llu,\"minimum_us\":%.6f,\"median_us\":%.6f,\"maximum_us\":%.6f}\n",count,(unsigned long long)bit,requested_us,elapsed*1000.0/s_qpc_freq.QuadPart,cpu/10000.0,(unsigned long long)(cycles1-cycles0),deltas[0]*1000000.0/s_qpc_freq.QuadPart,deltas[count/2]*1000000.0/s_qpc_freq.QuadPart,deltas[count-1]*1000000.0/s_qpc_freq.QuadPart);
 free(deltas);CHECK(SetThreadAffinityMask(GetCurrentThread(),old));return 0;}
int main(int argc,char**argv){CHECK(argc==3);requested_us=(unsigned)strtoul(argv[2],NULL,10);CHECK(requested_us>=1&&requested_us<1000);unsigned n=(unsigned)strtoul(argv[1],NULL,10);CHECK(n>=100&&n<=100000);HANDLE thread=CreateThread(NULL,0,bench,(LPVOID)(uintptr_t)n,0,NULL);CHECK(thread);CHECK(WaitForSingleObject(thread,120000)==WAIT_OBJECT_0);DWORD code;CHECK(GetExitCodeThread(thread,&code));CHECK(CloseHandle(thread));return (int)code;}

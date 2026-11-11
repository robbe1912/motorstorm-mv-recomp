/* Real Windows timers/FLS, authored requests; no game or desktop control. */
#include <windows.h>
#include <fenv.h>
#include <xmmintrin.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <crtdbg.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL %s (%lu)\n",#x,GetLastError());exit(7);}}while(0)
static volatile LONG creates,closes,arms;static LARGE_INTEGER frequency;
static HANDLE WINAPI counted_create(LPSECURITY_ATTRIBUTES a,LPCWSTR n,DWORD f,DWORD access){CHECK(f==2);InterlockedIncrement(&creates);return CreateWaitableTimerExW(a,n,f,access);}
static BOOL WINAPI counted_close(HANDLE h){InterlockedIncrement(&closes);return CloseHandle(h);}
static BOOL WINAPI counted_arm(HANDLE h,const LARGE_INTEGER* due,LONG period,PTIMERAPCROUTINE cb,LPVOID arg,PREASON_CONTEXT reason,ULONG delay){LONG k=InterlockedIncrement(&arms);LARGE_INTEGER early;early.QuadPart=-1;return SetWaitableTimerEx(h,k==1?&early:due,period,cb,arg,reason,delay);}
#define CreateWaitableTimerExW counted_create
#define CloseHandle counted_close
#define SetWaitableTimerEx counted_arm
#include "../native_short_sleep.c"
#undef CreateWaitableTimerExW
#undef CloseHandle
#undef SetWaitableTimerEx
static DWORD WINAPI worker(LPVOID arg){(void)arg;int rounds[]={FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO};
 for(int i=0;i<32;i++){CHECK(!fesetround(rounds[i%4]));unsigned csr=(_mm_getcsr()&~0x8040u)|((i&4)?0x8000:0)|((i&8)?0x40:0)|0x21;_mm_setcsr(csr);int flags=fetestexcept(FE_ALL_EXCEPT);LARGE_INTEGER before,after;CHECK(QueryPerformanceCounter(&before));CHECK(ps3_native_short_sleep(500)==1);CHECK(QueryPerformanceCounter(&after));CHECK((after.QuadPart-before.QuadPart)*1000000>=500*frequency.QuadPart);CHECK(_mm_getcsr()==csr&&fegetround()==rounds[i%4]&&fetestexcept(FE_ALL_EXCEPT)==flags);}
 return 0;}
int main(void){_set_error_mode(_OUT_TO_STDERR);_CrtSetReportMode(_CRT_ASSERT,_CRTDBG_MODE_FILE);_CrtSetReportFile(_CRT_ASSERT,_CRTDBG_FILE_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);CHECK(QueryPerformanceFrequency(&frequency));HANDLE threads[4];for(int i=0;i<4;i++){threads[i]=CreateThread(NULL,0,worker,NULL,0,NULL);CHECK(threads[i]);}CHECK(WaitForMultipleObjects(4,threads,TRUE,10000)==WAIT_OBJECT_0);for(int i=0;i<4;i++){DWORD code;CHECK(GetExitCodeThread(threads[i],&code)&&!code);CHECK(CloseHandle(threads[i]));}CHECK(creates==4&&closes==4&&arms>=128);printf("PASS real timers: 4 owned/FLS-exit-closed, 128 not-before/FP checks, early notification injected/not-before preserved; arms=%ld\n",arms);return 0;}

/* Authored deterministic Win32 outcomes; these are not real OS timing tests. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fenv.h>
#include <assert.h>
#include <limits.h>
#if defined(_M_X64) || defined(_M_IX86) || defined(__SSE__)
#include <xmmintrin.h>
#endif
#ifdef _WIN32
#include <crtdbg.h>
#endif
/* Standard headers precede the simulated platform selection on POSIX. */
#ifndef _WIN32
#define _WIN32
#endif
#include "short_sleep_fake_windows.h"
static int queries;static int mode,creates,closes,arms,waits,early,once_calls;static int64_t clock_ticks=1000,last_due;
static PVOID fls_value;static void (*destructor)(PVOID);static DWORD error=123;
#include "../native_short_sleep.c"
static DWORD GetLastError(void){return error;} static void SetLastError(DWORD x){error=x;}
static BOOL QueryPerformanceFrequency(LARGE_INTEGER* x){x->QuadPart=mode==15?0:mode==13?10000003:mode==21?INT64_MAX:10000000;return mode!=14;}
static BOOL QueryPerformanceCounter(LARGE_INTEGER* x){if(mode==16)return 0;if(mode==13&&++queries==2)clock_ticks=6000;x->QuadPart=clock_ticks;if(mode==17)x->QuadPart=INT64_MAX-1;if(mode==18&&waits)x->QuadPart=500;return 1;}
static BOOL CloseHandle(HANDLE x){assert(x==(HANDLE)(uintptr_t)88);closes++;return 1;}
static DWORD FlsAlloc(void (*f)(PVOID)){destructor=f;return mode==5?FLS_OUT_OF_INDEXES:3;}
static PVOID FlsGetValue(DWORD x){assert(x==3);return fls_value;}
static BOOL FlsSetValue(DWORD x,PVOID p){assert(x==3);if(mode==6&&p)return 0;fls_value=p;return 1;}
static BOOL InitOnceExecuteOnce(PINIT_ONCE x,BOOL (*f)(PINIT_ONCE,PVOID,PVOID*),PVOID a,PVOID* c){once_calls++;if(mode==4)return 0;if(!x->done){if(!f(x,a,c))return 0;x->done=1;}return 1;}
static HANDLE CreateWaitableTimerExW(void* a,void* b,DWORD flags,DWORD access){assert(!a&&!b&&flags==2&&access==(SYNCHRONIZE|TIMER_MODIFY_STATE));creates++;return mode==7?NULL:(HANDLE)(uintptr_t)88;}
static BOOL SetWaitableTimerEx(HANDLE h,const LARGE_INTEGER* due,int period,void* cb,void* arg,void* wake,DWORD delay){assert(h==(HANDLE)(uintptr_t)88&&due->QuadPart<0&&!period&&!cb&&!arg&&!wake&&!delay);arms++;last_due=-due->QuadPart;assert(last_due>0);return mode!=8;}
static DWORD WaitForSingleObject(HANDLE h,DWORD timeout){assert(h==(HANDLE)(uintptr_t)88&&timeout==INFINITE);waits++;fesetround(FE_DOWNWARD);feraiseexcept(FE_DIVBYZERO);assert(waits<=4);if(mode==9)return WAIT_FAILED;if(mode==2&&!early++){clock_ticks+=last_due/3;}else clock_ticks+=last_due;return WAIT_OBJECT_0;}
static LARGE_INTEGER s_qpc_freq={10000000};static int switches;
static void ensure_qpc_init(void){}
static BOOL SwitchToThread(void){switches++;clock_ticks+=500;return 1;}
static HANDLE CreateWaitableTimerW(void* a,BOOL b,void* c){(void)a;(void)b;(void)c;abort();}
static BOOL SetWaitableTimer(HANDLE h,LARGE_INTEGER* d,int p,void* f,void* a,BOOL r){(void)h;(void)d;(void)p;(void)f;(void)a;(void)r;abort();}
static void Sleep(DWORD x){(void)x;abort();}
static void actual_caller(uint64_t usec){ /* ACTUAL_WINDOWS_BRANCH */ }
int main(int argc,char**argv){assert(argc==2);mode=atoi(argv[1]);
#ifdef _MSC_VER
 _set_error_mode(_OUT_TO_STDERR);_CrtSetReportMode(_CRT_ASSERT,_CRTDBG_MODE_FILE);_CrtSetReportFile(_CRT_ASSERT,_CRTDBG_FILE_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
 if(mode==0||mode==3){assert(!ps3_native_short_sleep(0)&&!ps3_native_short_sleep(1000)&&!ps3_native_short_sleep(UINT64_MAX));assert(!once_calls);}
 if(mode==20){actual_caller(500);assert(!creates&&!arms&&!waits&&switches==10);return 0;}
 int old=fegetround();assert(!fesetround(FE_UPWARD));feraiseexcept(FE_INVALID|FE_INEXACT);int flags=fetestexcept(FE_ALL_EXCEPT);
#if defined(SHORT_SLEEP_MXCSR)
 unsigned csr=_mm_getcsr();
#endif
 uint64_t request=mode==10?1:mode==11?999:500;actual_caller(request);int result=!switches;
 assert(fegetround()==FE_UPWARD&&fetestexcept(FE_ALL_EXCEPT)==flags);
#if defined(SHORT_SLEEP_MXCSR)
 assert(_mm_getcsr()==csr);
#endif
 if(mode==1||mode==2||mode==0||mode==3||mode==10||mode==11||mode==13){assert(result==1&&clock_ticks>=1000+(request*(uint64_t)(mode==13?10000003:10000000)+999999)/1000000);assert(waits==(mode==2?2:1));assert(creates==1);int save=waits;assert(ps3_native_short_sleep(500)==1);assert(creates==1&&waits==save+1);destructor(fls_value);fls_value=NULL;assert(closes==1);}
 else {assert(result==0);if(mode==6||mode==8||mode==9)assert(closes==1&&!fls_value);else assert(!closes);}
 fesetround(old);puts("PASS actual short-wait state machine");return 0;
}

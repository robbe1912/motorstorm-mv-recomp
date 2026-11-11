#ifndef SHORT_SLEEP_FAKE_WINDOWS_H
#define SHORT_SLEEP_FAKE_WINDOWS_H
#include <stdint.h>
#define WINAPI
#define CALLBACK
#define TRUE 1
#define FALSE 0
#define INFINITE 0xffffffffu
#define WAIT_OBJECT_0 0
#define WAIT_FAILED 0xffffffffu
#define SYNCHRONIZE 0x100000u
#define TIMER_MODIFY_STATE 2
#define FLS_OUT_OF_INDEXES 0xffffffffu
typedef void VOID; typedef void* PVOID; typedef void* HANDLE;
typedef uint32_t DWORD; typedef int BOOL; typedef int64_t LONGLONG;
typedef struct {int64_t QuadPart;} LARGE_INTEGER;
typedef struct {int done;} INIT_ONCE; typedef INIT_ONCE* PINIT_ONCE;
#define INIT_ONCE_STATIC_INIT {0}
static DWORD GetLastError(void); static void SetLastError(DWORD);
static BOOL QueryPerformanceFrequency(LARGE_INTEGER*); static BOOL QueryPerformanceCounter(LARGE_INTEGER*);
static BOOL CloseHandle(HANDLE); static DWORD FlsAlloc(void (*)(PVOID));
static PVOID FlsGetValue(DWORD); static BOOL FlsSetValue(DWORD,PVOID);
static BOOL InitOnceExecuteOnce(PINIT_ONCE,BOOL (*)(PINIT_ONCE,PVOID,PVOID*),PVOID,PVOID*);
static HANDLE CreateWaitableTimerExW(void*,void*,DWORD,DWORD);
static BOOL SetWaitableTimerEx(HANDLE,const LARGE_INTEGER*,int,void*,void*,void*,DWORD);
static DWORD WaitForSingleObject(HANDLE,DWORD);
static void YieldProcessor(void) {}
#endif

/* Actual wait body, authored COM/clock/event outcomes. No GPU proof. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#ifdef _WIN32
#include <crtdbg.h>
#endif
typedef uint64_t u64;typedef uint32_t DWORD;typedef int HRESULT;typedef void* HANDLE;
#define E_FAIL (-1)
#define FAILED(x) ((x)<0)
#define WAIT_OBJECT_0 0
static int mode,waits,registrations,signals;static u64 completed,clock_now;
typedef struct Fence Fence;typedef struct Queue Queue;typedef struct Device Device;
static u64 get_completed(Fence*f){(void)f;return mode==2?UINT64_MAX:completed;}
static HRESULT set_event(Fence*f,u64 value,HANDLE e){(void)f;(void)e;assert(value==1);++registrations;return mode==5?-1:0;}
static HRESULT signal_queue(Queue*q,Fence*f,u64 value){(void)q;(void)f;assert(value==1);++signals;return mode==4?-1:0;}
static HRESULT removed(Device*d){(void)d;return mode==3?-1:0;}
struct Fence { const struct FenceOps {u64(*GetCompletedValue)(Fence*);HRESULT(*SetEventOnCompletion)(Fence*,u64,HANDLE);}*lpVtbl;};
struct Queue { const struct QueueOps {HRESULT(*Signal)(Queue*,Fence*,u64);}*lpVtbl;};
struct Device { const struct DeviceOps {HRESULT(*GetDeviceRemovedReason)(Device*);}*lpVtbl;};
static const struct FenceOps fence_ops={get_completed,set_event};static Fence fence={&fence_ops};
static const struct QueueOps queue_ops={signal_queue};static Queue queue={&queue_ops};
static const struct DeviceOps device_ops={removed};static Device device={&device_ops};
static struct {Queue*cmd_queue;Device*device;}s_d3d={&queue,&device};
static Fence*s_cpu_surface_fence=&fence;static HANDLE s_cpu_surface_event=(void*)1;static u64 s_cpu_surface_fence_value;
static u64 GetTickCount64(void){return clock_now;}
static DWORD WaitForSingleObject(HANDLE event,DWORD duration){assert(event&&duration&&duration<=30000);if(++waits>8)exit(6);if(mode==6)return 0xffffffff;if(mode==7){clock_now+=30001;return 0;}if(mode!=1||waits>1)completed=1;return 0;}
static void cpu_surface_fail(const char*operation,HRESULT code){assert(code<0);fprintf(stderr,"FAIL %s\n",operation);exit(9);}
#define CPU_SURFACE_HR(call) do{HRESULT result=(call);if(FAILED(result))cpu_surface_fail(#call,result);}while(0)
// WAIT_FUNCTION
int main(int argc,char**argv){
#ifdef _WIN32
 _set_error_mode(_OUT_TO_STDERR);_CrtSetReportMode(_CRT_ASSERT,_CRTDBG_MODE_FILE);_CrtSetReportFile(_CRT_ASSERT,_CRTDBG_FILE_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
 assert(argc==2);mode=atoi(argv[1]);if(mode==8)s_cpu_surface_fence_value=UINT64_MAX;cpu_surface_fence_wait();if(mode>=2){fprintf(stderr,"FAIL missing error\n");return 7;}assert(completed==1&&signals==1);assert(waits==(mode==1?2:1));assert(registrations==waits);return 0;}

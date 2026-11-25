/* Authored headless fixture. WAIT_FUNCTION is replaced with actual production C. */
#include <windows.h>
#include <d3d12.h>
#include <d3d12sdklayers.h>
#include <dxgi1_4.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint64_t u64;
static struct { ID3D12Device*device; ID3D12CommandQueue*cmd_queue; } s_d3d;
static ID3D12Fence*s_cpu_surface_fence;
static HANDLE s_cpu_surface_event;
static u64 s_cpu_surface_fence_value;
static void cpu_surface_fail(const char*operation,HRESULT result){fprintf(stderr,"FAIL %s %08lX\n",operation,(unsigned long)result);exit(9);}
#define CPU_SURFACE_HR(call) do{HRESULT result=(call);if(FAILED(result))cpu_surface_fail(#call,result);}while(0)
// WAIT_FUNCTION
static DWORD WINAPI release_gate(void*arg){Sleep(100);ID3D12Fence*f=arg;return FAILED(f->lpVtbl->Signal(f,1));}
int main(void){
 ID3D12Debug*debug=NULL;CPU_SURFACE_HR(D3D12GetDebugInterface(&IID_ID3D12Debug,(void**)&debug));debug->lpVtbl->EnableDebugLayer(debug);debug->lpVtbl->Release(debug);
 CPU_SURFACE_HR(D3D12CreateDevice(NULL,D3D_FEATURE_LEVEL_11_0,&IID_ID3D12Device,(void**)&s_d3d.device));
 IDXGIFactory4*factory=NULL;IDXGIAdapter1*adapter=NULL;CPU_SURFACE_HR(CreateDXGIFactory1(&IID_IDXGIFactory4,(void**)&factory));LUID luid;s_d3d.device->lpVtbl->GetAdapterLuid(s_d3d.device,&luid);CPU_SURFACE_HR(factory->lpVtbl->EnumAdapterByLuid(factory,luid,&IID_IDXGIAdapter1,(void**)&adapter));DXGI_ADAPTER_DESC1 desc;CPU_SURFACE_HR(adapter->lpVtbl->GetDesc1(adapter,&desc));if(desc.Flags&DXGI_ADAPTER_FLAG_SOFTWARE)return 8;wprintf(L"Hardware: %ls\n",desc.Description);
 D3D12_COMMAND_QUEUE_DESC q={0};q.Type=D3D12_COMMAND_LIST_TYPE_DIRECT;CPU_SURFACE_HR(s_d3d.device->lpVtbl->CreateCommandQueue(s_d3d.device,&q,&IID_ID3D12CommandQueue,(void**)&s_d3d.cmd_queue));
 CPU_SURFACE_HR(s_d3d.device->lpVtbl->CreateFence(s_d3d.device,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void**)&s_cpu_surface_fence));s_cpu_surface_event=CreateEvent(NULL,FALSE,FALSE,NULL);if(!s_cpu_surface_event)return 8;
 ID3D12Fence*gate=NULL;CPU_SURFACE_HR(s_d3d.device->lpVtbl->CreateFence(s_d3d.device,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void**)&gate));
 CPU_SURFACE_HR(s_d3d.cmd_queue->lpVtbl->Wait(s_d3d.cmd_queue,gate,1));if(!SetEvent(s_cpu_surface_event))return 8;
 HANDLE worker=CreateThread(NULL,0,release_gate,gate,0,NULL);if(!worker)return 8;
 cpu_surface_fence_wait();int target_complete=s_cpu_surface_fence->lpVtbl->GetCompletedValue(s_cpu_surface_fence)>=s_cpu_surface_fence_value;
 if(WaitForSingleObject(worker,2000)!=WAIT_OBJECT_0)return 8;DWORD code=1;if(!GetExitCodeThread(worker,&code)||code)return 8;CloseHandle(worker);
 /* Drain even an historical early return before releasing queue/fence ownership. */
 CPU_SURFACE_HR(s_cpu_surface_fence->lpVtbl->SetEventOnCompletion(s_cpu_surface_fence,s_cpu_surface_fence_value,s_cpu_surface_event));if(WaitForSingleObject(s_cpu_surface_event,2000)!=WAIT_OBJECT_0)return 8;
 if(!target_complete){fprintf(stderr,"FAIL target_complete: stale event admitted unfinished GPU work\n");return 7;}
 for(int i=0;i<32;i++)cpu_surface_fence_wait();
 ID3D12InfoQueue*info=NULL;CPU_SURFACE_HR(s_d3d.device->lpVtbl->QueryInterface(s_d3d.device,&IID_ID3D12InfoQueue,(void**)&info));UINT64 messages=info->lpVtbl->GetNumStoredMessages(info);if(messages){for(UINT64 i=0;i<messages;i++){SIZE_T size=0;info->lpVtbl->GetMessage(info,i,NULL,&size);D3D12_MESSAGE*m=malloc(size);CPU_SURFACE_HR(info->lpVtbl->GetMessage(info,i,m,&size));fprintf(stderr,"validation %s\n",m->pDescription);free(m);}return 8;}
 info->lpVtbl->Release(info);gate->lpVtbl->Release(gate);CloseHandle(s_cpu_surface_event);s_cpu_surface_fence->lpVtbl->Release(s_cpu_surface_fence);s_d3d.cmd_queue->lpVtbl->Release(s_d3d.cmd_queue);adapter->lpVtbl->Release(adapter);factory->lpVtbl->Release(factory);s_d3d.device->lpVtbl->Release(s_d3d.device);
 puts("PASS actual CPU-surface fence: stale event, target completion, repeated reuse, zero validation messages");return 0;
}

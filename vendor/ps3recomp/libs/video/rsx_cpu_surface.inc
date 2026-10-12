/* Render-thread service for CPU loads from host-rendered guest surfaces. */
#include "ps3emu/guest_read_sync.h"
#include "rsx_surface_readback.h"
typedef struct CpuSurfaceRequest {
    struct CpuSurfaceRequest *next;
    u32 address, bytes;
    HANDLE done;
    int status;
} CpuSurfaceRequest;
static SRWLOCK s_cpu_surface_lock = SRWLOCK_INIT;
static CpuSurfaceRequest *s_cpu_surface_head, *s_cpu_surface_tail;
static volatile LONG s_cpu_surface_thread;
static ID3D12CommandAllocator *s_cpu_surface_alloc;
static ID3D12GraphicsCommandList *s_cpu_surface_list;
static ID3D12Fence *s_cpu_surface_fence;
static HANDLE s_cpu_surface_event;
static u64 s_cpu_surface_fence_value;
static int s_cpu_surface_live;
static int s_cpu_surface_recording;
static void cpu_surface_fail(const char *operation, HRESULT result) {
    fprintf(stderr,"[CPUSURFACE] %s failed: 0x%08lX\n",operation,(unsigned long)result);abort();
}
#define CPU_SURFACE_HR(call) do { HRESULT _result=(call); if(FAILED(_result))cpu_surface_fail(#call,_result); } while(0)
static void cpu_surface_fence_wait(void) {
    u64 value=++s_cpu_surface_fence_value;
    CPU_SURFACE_HR(s_d3d.cmd_queue->lpVtbl->Signal(s_d3d.cmd_queue,s_cpu_surface_fence,value));
    if(s_cpu_surface_fence->lpVtbl->GetCompletedValue(s_cpu_surface_fence)<value) {
        CPU_SURFACE_HR(s_cpu_surface_fence->lpVtbl->SetEventOnCompletion(s_cpu_surface_fence,value,s_cpu_surface_event));
        if(WaitForSingleObject(s_cpu_surface_event,30000)!=WAIT_OBJECT_0)cpu_surface_fail("GPU fence wait",E_FAIL);
    }
    CPU_SURFACE_HR(s_d3d.device->lpVtbl->GetDeviceRemovedReason(s_d3d.device));
}
static void cpu_surface_copy(OffRT *r) {
    extern uint8_t *vm_base;
    if(!r->res || !r->cpu_address || !r->cpu_pitch || !r->gpu_generation || r->cpu_generation==r->gpu_generation)return;
    unsigned bpp=rsx_surface_readback_bpp(r->cpu_format);
    if(!bpp || r->cpu_pitch%bpp)cpu_surface_fail("unsupported guest surface layout",E_INVALIDARG);
    u32 width=r->w;
    if(width>r->cpu_pitch/bpp)width=r->cpu_pitch/bpp;
    u32 pitch=(r->w*bpp+255)&~255u;
    u64 bytes=(u64)pitch*r->h;
    u64 guest_bytes=(u64)r->cpu_pitch*r->h;
    if(!width || !r->h || bytes>256u*1024u*1024u || (u64)r->cpu_address+guest_bytes>0x100000000ull)
        cpu_surface_fail("surface copy bounds",E_INVALIDARG);
    if(!r->cpu_readback) {
        D3D12_HEAP_PROPERTIES hp={0};hp.Type=D3D12_HEAP_TYPE_READBACK;
        D3D12_RESOURCE_DESC desc={0};desc.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;
        desc.Width=bytes;desc.Height=1;desc.DepthOrArraySize=1;desc.MipLevels=1;desc.SampleDesc.Count=1;
        desc.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
        CPU_SURFACE_HR(s_d3d.device->lpVtbl->CreateCommittedResource(s_d3d.device,&hp,D3D12_HEAP_FLAG_NONE,&desc,
            D3D12_RESOURCE_STATE_COPY_DEST,NULL,&IID_ID3D12Resource,(void **)&r->cpu_readback));
    }
    cpu_surface_fence_wait();
    CPU_SURFACE_HR(s_cpu_surface_alloc->lpVtbl->Reset(s_cpu_surface_alloc));
    CPU_SURFACE_HR(s_cpu_surface_list->lpVtbl->Reset(s_cpu_surface_list,s_cpu_surface_alloc,NULL));
    D3D12_RESOURCE_BARRIER barrier={0};barrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition.pResource=r->res;barrier.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    barrier.Transition.StateBefore=r->st;barrier.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;
    if(r->st!=D3D12_RESOURCE_STATE_COPY_SOURCE)s_cpu_surface_list->lpVtbl->ResourceBarrier(s_cpu_surface_list,1,&barrier);
    D3D12_TEXTURE_COPY_LOCATION src={0},dst={0};src.pResource=r->res;src.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    dst.pResource=r->cpu_readback;dst.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    dst.PlacedFootprint.Footprint.Format=(DXGI_FORMAT)r->dxgi;
    dst.PlacedFootprint.Footprint.Width=r->w;dst.PlacedFootprint.Footprint.Height=r->h;
    dst.PlacedFootprint.Footprint.Depth=1;dst.PlacedFootprint.Footprint.RowPitch=pitch;
    s_cpu_surface_list->lpVtbl->CopyTextureRegion(s_cpu_surface_list,&dst,0,0,0,&src,NULL);
    if(r->st!=D3D12_RESOURCE_STATE_COPY_SOURCE) {
        barrier.Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_SOURCE;barrier.Transition.StateAfter=r->st;
        s_cpu_surface_list->lpVtbl->ResourceBarrier(s_cpu_surface_list,1,&barrier);
    }
    CPU_SURFACE_HR(s_cpu_surface_list->lpVtbl->Close(s_cpu_surface_list));
    ID3D12CommandList *lists[]={(ID3D12CommandList *)s_cpu_surface_list};
    s_d3d.cmd_queue->lpVtbl->ExecuteCommandLists(s_d3d.cmd_queue,1,lists);
    cpu_surface_fence_wait();
    D3D12_RANGE range={0,(SIZE_T)bytes};void *mapped=NULL;
    CPU_SURFACE_HR(r->cpu_readback->lpVtbl->Map(r->cpu_readback,0,&range,&mapped));
    if(!mapped || rsx_surface_readback_rows(vm_base+r->cpu_address,(size_t)guest_bytes,r->cpu_pitch,
        mapped,(size_t)bytes,pitch,width,r->h,r->cpu_format))cpu_surface_fail("guest surface packing",E_INVALIDARG);
    D3D12_RANGE empty={0,0};r->cpu_readback->lpVtbl->Unmap(r->cpu_readback,0,&empty);
    r->cpu_generation=r->gpu_generation;
    static unsigned logged;const char *log=getenv("RSX_CPU_SURFACE_LOG");
    if(log && logged++<(unsigned)strtoul(log,NULL,10))fprintf(stderr,"[CPUSURFACE] synchronized ea=%08X offset=%08X pitch=%u size=%ux%u format=%u generation=%llu\n",
        r->cpu_address,r->off,r->cpu_pitch,width,r->h,r->cpu_format&31u,(unsigned long long)r->gpu_generation);
}
static void cpu_surface_read(u32 address,u32 bytes) {
    for(int i=0;i<CPU_SURFACE_CAPACITY;i++) {
        OffRT *r=&s_d3d.off_rt[i];
        if(!r->res || !r->cpu_address)continue;
        u64 end=(u64)r->cpu_address+(u64)r->cpu_pitch*r->h;
        if((u64)address<end && (u64)address+bytes>r->cpu_address){
            if(s_cpu_surface_recording && r->gpu_generation && r->cpu_generation!=r->gpu_generation)cpu_surface_fail("CPU load requires pending recorded surface writes",E_FAIL);
            cpu_surface_copy(r);
        }
    }
}
static void cpu_surface_service(void) {
    LONG thread=(LONG)GetCurrentThreadId();
    LONG owner=InterlockedCompareExchange(&s_cpu_surface_thread,thread,0);
    if(owner && owner!=thread)cpu_surface_fail("renderer service thread changed",E_FAIL);
    AcquireSRWLockExclusive(&s_cpu_surface_lock);
    CpuSurfaceRequest *request=s_cpu_surface_head;s_cpu_surface_head=s_cpu_surface_tail=NULL;
    ReleaseSRWLockExclusive(&s_cpu_surface_lock);
    while(request) {
        CpuSurfaceRequest *next=request->next;
        cpu_surface_read(request->address,request->bytes);request->status=0;
        if(!SetEvent(request->done))cpu_surface_fail("CPU completion event",E_FAIL);
        request=next;
    }
}
static void cpu_surface_request(u32 address,u32 bytes,void *opaque) {
    (void)opaque;
    if((LONG)GetCurrentThreadId()==InterlockedCompareExchange(&s_cpu_surface_thread,0,0)){cpu_surface_read(address,bytes);return;}
    CpuSurfaceRequest request={0};request.address=address;request.bytes=bytes;request.status=-1;
    request.done=CreateEventA(NULL,FALSE,FALSE,NULL);
    if(!request.done)cpu_surface_fail("CPU read event creation",E_FAIL);
    AcquireSRWLockExclusive(&s_cpu_surface_lock);
    if(!s_cpu_surface_live){ReleaseSRWLockExclusive(&s_cpu_surface_lock);CloseHandle(request.done);return;}
    if(s_cpu_surface_tail)s_cpu_surface_tail->next=&request;else s_cpu_surface_head=&request;
    s_cpu_surface_tail=&request;ReleaseSRWLockExclusive(&s_cpu_surface_lock);
    extern void *cellGcm_fifo_kick_event(void);
    HANDLE kick=(HANDLE)cellGcm_fifo_kick_event();if(kick&&!SetEvent(kick))cpu_surface_fail("renderer kick",E_FAIL);
    if(WaitForSingleObject(request.done,30000)!=WAIT_OBJECT_0 || request.status)cpu_surface_fail("CPU read synchronization",E_FAIL);
    CloseHandle(request.done);
}
static void cpu_surface_init(void) {
    s_cpu_surface_thread=0;
    CPU_SURFACE_HR(s_d3d.device->lpVtbl->CreateCommandAllocator(s_d3d.device,D3D12_COMMAND_LIST_TYPE_DIRECT,
        &IID_ID3D12CommandAllocator,(void **)&s_cpu_surface_alloc));
    CPU_SURFACE_HR(s_d3d.device->lpVtbl->CreateCommandList(s_d3d.device,0,D3D12_COMMAND_LIST_TYPE_DIRECT,
        s_cpu_surface_alloc,NULL,&IID_ID3D12GraphicsCommandList,(void **)&s_cpu_surface_list));
    CPU_SURFACE_HR(s_cpu_surface_list->lpVtbl->Close(s_cpu_surface_list));
    CPU_SURFACE_HR(s_d3d.device->lpVtbl->CreateFence(s_d3d.device,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void **)&s_cpu_surface_fence));
    s_cpu_surface_event=CreateEventA(NULL,FALSE,FALSE,NULL);if(!s_cpu_surface_event)cpu_surface_fail("GPU event creation",E_FAIL);
    s_cpu_surface_live=1;vm_read_sync_set_handler(cpu_surface_request,NULL);
}
static void cpu_surface_retire(OffRT *r) {
    cpu_surface_copy(r);
    if(r->cpu_readback){r->cpu_readback->lpVtbl->Release(r->cpu_readback);r->cpu_readback=NULL;}
    r->cpu_address=r->cpu_pitch=0;r->gpu_generation=r->cpu_generation=0;
}
static void cpu_surface_shutdown(void) {
    vm_read_sync_set_handler(NULL,NULL);
    AcquireSRWLockExclusive(&s_cpu_surface_lock);
    for(int i=0;i<CPU_SURFACE_CAPACITY;i++)cpu_surface_retire(&s_d3d.off_rt[i]);
    s_cpu_surface_live=0;
    CpuSurfaceRequest *request=s_cpu_surface_head;s_cpu_surface_head=s_cpu_surface_tail=NULL;
    ReleaseSRWLockExclusive(&s_cpu_surface_lock);
    while(request){CpuSurfaceRequest *next=request->next;request->status=0;if(!SetEvent(request->done))cpu_surface_fail("shutdown CPU completion",E_FAIL);request=next;}
    if(s_cpu_surface_list)s_cpu_surface_list->lpVtbl->Release(s_cpu_surface_list);
    if(s_cpu_surface_alloc)s_cpu_surface_alloc->lpVtbl->Release(s_cpu_surface_alloc);
    if(s_cpu_surface_fence)s_cpu_surface_fence->lpVtbl->Release(s_cpu_surface_fence);
    if(s_cpu_surface_event)CloseHandle(s_cpu_surface_event);
}
static void cpu_surface_capture(D3D12DrawRecord *draw) {
    const rsx_state *st=s_d3d.current_rsx_state;
    for(unsigned i=0;i<4;i++) {
        draw->cpu_address[i]=draw->cpu_pitch[i]=0;
        if(!st)continue;
        unsigned source=(!i&&st->color_target==2)?1:i;
        u32 dma=st->surface_color_dma[source];
        if(dma!=CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER && dma!=CELL_GCM_CONTEXT_DMA_MEMORY_HOST_BUFFER)continue;
        extern u32 cellGcmResolveLocated(int local,u32 offset);
        draw->cpu_address[i]=cellGcmResolveLocated(dma==CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER,st->surface_color_offset[source]);
        draw->cpu_pitch[i]=st->surface_color_pitch[source];
    }
}
static void cpu_surface_bind(int index,const D3D12DrawRecord *draw,unsigned target) {
    if(index<0)return;OffRT *r=&s_d3d.off_rt[index];
    u32 address=draw->cpu_address[target],pitch=draw->cpu_pitch[target];
    if(address==0xffffffffu || !pitch)return;
    if(r->cpu_address && address!=r->cpu_address)cpu_surface_fail("surface memory identity changed at one offset",E_INVALIDARG);
    if(r->cpu_pitch!=pitch)r->cpu_generation=0;
    r->cpu_address=address;r->cpu_pitch=pitch;r->cpu_format=draw->rt_fmt;
    if(address && vm_read_sync_mark_range(address,(u64)pitch*r->h))cpu_surface_fail("guest surface registration",E_INVALIDARG);
}
static void cpu_surface_written(int primary,const int secondary[3]) {
    if(primary>=0)s_d3d.off_rt[primary].gpu_generation++;
    for(int i=0;i<3;i++)if(secondary[i]>=0)s_d3d.off_rt[secondary[i]].gpu_generation++;
}
#undef CPU_SURFACE_HR

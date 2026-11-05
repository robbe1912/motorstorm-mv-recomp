/* Authored headless DX12 functional fixture. See tools/test_rsx_texture_gpu.py. */

#include "backend-static.c"
#include <crtdbg.h>
uint8_t* vm_base;
/* Link-only diagnostic boundary: no VRAM relocation is part of this fixture. */
u32 rsx_find_vram_upload(u32 bytes){(void)bytes;fprintf(stderr,"UNEXPECTED VRAM relocation boundary\n");abort();}
static void gpu_errors(void){
 if(!s_d3d.device)return;
 fprintf(stderr,"Device reason=%08lX\n",(unsigned long)s_d3d.device->lpVtbl->GetDeviceRemovedReason(s_d3d.device));
 ID3D12InfoQueue*q=NULL;if(FAILED(s_d3d.device->lpVtbl->QueryInterface(s_d3d.device,&IID_ID3D12InfoQueue,(void**)&q)))return;
 uint64_t count=q->lpVtbl->GetNumStoredMessagesAllowedByRetrievalFilter(q);
 for(uint64_t i=0;i<count;i++){SIZE_T n=0;q->lpVtbl->GetMessage(q,i,NULL,&n);D3D12_MESSAGE*m=malloc(n);if(m&&SUCCEEDED(q->lpVtbl->GetMessage(q,i,m,&n)))fprintf(stderr,"D3D12 severity=%u: %s\n",m->Severity,m->pDescription);free(m);}q->lpVtbl->Release(q);
}
#define REQUIRE(c) do{if(!(c)){fprintf(stderr,"GPU contract failed line %d: %s\n",__LINE__,#c);gpu_errors();exit(7);}}while(0)
#define HR(c) do{HRESULT h=(c);if(FAILED(h)){fprintf(stderr,"GPU HRESULT line %d: %08lX\n",__LINE__,(unsigned long)h);exit(8);}}while(0)
static ID3D12Resource* rb;
static D3D12_PLACED_SUBRESOURCE_FOOTPRINT rb_fp;
static uint64_t rb_size;
static void reset_commands(void){HR(s_d3d.cmd_allocators[0]->lpVtbl->Reset(s_d3d.cmd_allocators[0]));HR(s_d3d.cmd_list->lpVtbl->Reset(s_d3d.cmd_list,s_d3d.cmd_allocators[0],NULL));}
static void submit(void){HR(s_d3d.cmd_list->lpVtbl->Close(s_d3d.cmd_list));ID3D12CommandList*l=(ID3D12CommandList*)s_d3d.cmd_list;s_d3d.cmd_queue->lpVtbl->ExecuteCommandLists(s_d3d.cmd_queue,1,&l);}
static void capture_face(int slot,unsigned face){
 ID3D12Resource*r=s_d3d.vp_tex[slot].res;
 D3D12_RESOURCE_DESC td;r->lpVtbl->GetDesc(r,&td);
 REQUIRE(td.Format==DXGI_FORMAT_R8G8B8A8_UNORM);
 if(!rb){
  s_d3d.device->lpVtbl->GetCopyableFootprints(s_d3d.device,&td,0,1,0,&rb_fp,NULL,NULL,&rb_size);
  D3D12_HEAP_PROPERTIES hp={0};hp.Type=D3D12_HEAP_TYPE_READBACK;
  D3D12_RESOURCE_DESC d={0};d.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;d.Width=rb_size;d.Height=1;d.DepthOrArraySize=1;d.MipLevels=1;d.SampleDesc.Count=1;d.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
  HR(s_d3d.device->lpVtbl->CreateCommittedResource(s_d3d.device,&hp,D3D12_HEAP_FLAG_NONE,&d,D3D12_RESOURCE_STATE_COPY_DEST,NULL,&IID_ID3D12Resource,(void**)&rb));
 }
 D3D12_RESOURCE_BARRIER b={0};b.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;b.Transition.pResource=r;b.Transition.StateBefore=D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;b.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;b.Transition.Subresource=face;
 s_d3d.cmd_list->lpVtbl->ResourceBarrier(s_d3d.cmd_list,1,&b);
 D3D12_TEXTURE_COPY_LOCATION dst={0},src={0};dst.pResource=rb;dst.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;dst.PlacedFootprint=rb_fp;src.pResource=r;src.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;src.SubresourceIndex=face;
 s_d3d.cmd_list->lpVtbl->CopyTextureRegion(s_d3d.cmd_list,&dst,0,0,0,&src,NULL);
 b.Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_SOURCE;b.Transition.StateAfter=D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;s_d3d.cmd_list->lpVtbl->ResourceBarrier(s_d3d.cmd_list,1,&b);
}
static void capture(int slot){capture_face(slot,0);}
static void pixels_argb(const uint8_t* argb){
 void*p=NULL;D3D12_RANGE range={0,(SIZE_T)rb_size};HR(rb->lpVtbl->Map(rb,0,&range,&p));
 for(unsigned y=0;y<128;y++)for(unsigned x=0;x<128;x++){
  const uint8_t*src=argb+(y*128+x)*4;uint8_t*v=(uint8_t*)p+y*rb_fp.Footprint.RowPitch+x*4;
  REQUIRE(v[0]==src[1]&&v[1]==src[2]&&v[2]==src[3]&&v[3]==src[0]);
 }
 D3D12_RANGE wr={0,0};rb->lpVtbl->Unmap(rb,0,&wr);
}
static void pixels(int r,int g,int b){
 void*p=NULL;D3D12_RANGE range={0,(SIZE_T)rb_size};HR(rb->lpVtbl->Map(rb,0,&range,&p));
 for(unsigned y=0;y<128;y++)for(unsigned x=0;x<128;x++){
  uint8_t*v=(uint8_t*)p+y*rb_fp.Footprint.RowPitch+x*4;
  REQUIRE(v[0]==r&&v[1]==g&&v[2]==b&&v[3]==255);
 }
 D3D12_RANGE wr={0,0};rb->lpVtbl->Unmap(rb,0,&wr);
}
static int upload(unsigned id){return vp_upload_tex_slot_impl(0x1000+id*0x10000,128,128,0xa5,0,1,NULL);}
static DWORD WINAPI release_gate(void* value){
 Sleep(500);ID3D12Fence*gate=value;return FAILED(gate->lpVtbl->Signal(gate,1))?1:0;
}

/* Execute real 2D/cube SRVs through the production descriptor writer. */
static void sample_descriptors(int a,int b,int cube) {
    static const char shader[]=
        "Texture2D<float4>A:register(t0);Texture2D<float4>B:register(t1);"
        "TextureCube<float4>C:register(t2);SamplerState S:register(s0);"
        "RWStructuredBuffer<uint4>O:register(u0);[numthreads(1,1,1)]void main(){"
        "O[0]=uint4(round(A.Load(int3(0,0,0))*255));O[1]=uint4(round(B.Load(int3(0,0,0))*255));"
        "float3 D[6]={float3(1,0,0),float3(-1,0,0),float3(0,1,0),float3(0,-1,0),float3(0,0,1),float3(0,0,-1)};"
        "for(uint i=0;i<6;i++)O[i+2]=uint4(round(C.SampleLevel(S,D[i],0)*255));}";
    ID3DBlob *cs=NULL,*errors=NULL,*signature=NULL;
    HRESULT hr=D3DCompile(shader,sizeof(shader)-1,NULL,NULL,NULL,"main","cs_5_0",D3DCOMPILE_OPTIMIZATION_LEVEL3,0,&cs,&errors);
    if(errors){fprintf(stderr,"Shader compiler: %s\n",(char*)errors->lpVtbl->GetBufferPointer(errors));errors->lpVtbl->Release(errors);errors=NULL;} HR(hr);
    D3D12_DESCRIPTOR_RANGE range={0};range.RangeType=D3D12_DESCRIPTOR_RANGE_TYPE_SRV;range.NumDescriptors=3;
    D3D12_ROOT_PARAMETER params[2]={0};params[0].ParameterType=D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    params[0].DescriptorTable.NumDescriptorRanges=1;params[0].DescriptorTable.pDescriptorRanges=&range;
    params[1].ParameterType=D3D12_ROOT_PARAMETER_TYPE_UAV;
    D3D12_STATIC_SAMPLER_DESC sampler={0};sampler.Filter=D3D12_FILTER_MIN_MAG_MIP_POINT;
    sampler.AddressU=sampler.AddressV=sampler.AddressW=D3D12_TEXTURE_ADDRESS_MODE_CLAMP;
    sampler.ComparisonFunc=D3D12_COMPARISON_FUNC_NEVER;sampler.MaxLOD=D3D12_FLOAT32_MAX;
    D3D12_ROOT_SIGNATURE_DESC desc={0};desc.NumParameters=2;desc.pParameters=params;desc.NumStaticSamplers=1;desc.pStaticSamplers=&sampler;
    hr=D3D12SerializeRootSignature(&desc,D3D_ROOT_SIGNATURE_VERSION_1,&signature,&errors);
    if(errors){fprintf(stderr,"Root signature: %s\n",(char*)errors->lpVtbl->GetBufferPointer(errors));errors->lpVtbl->Release(errors);}HR(hr);
    ID3D12RootSignature*root=NULL;ID3D12PipelineState*pso=NULL;
    HR(s_d3d.device->lpVtbl->CreateRootSignature(s_d3d.device,0,signature->lpVtbl->GetBufferPointer(signature),signature->lpVtbl->GetBufferSize(signature),&IID_ID3D12RootSignature,(void**)&root));
    D3D12_COMPUTE_PIPELINE_STATE_DESC pd={0};pd.pRootSignature=root;pd.CS.pShaderBytecode=cs->lpVtbl->GetBufferPointer(cs);pd.CS.BytecodeLength=cs->lpVtbl->GetBufferSize(cs);
    HR(s_d3d.device->lpVtbl->CreateComputePipelineState(s_d3d.device,&pd,&IID_ID3D12PipelineState,(void**)&pso));
    D3D12_RESOURCE_DESC rd={0};rd.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;rd.Width=128;rd.Height=1;rd.DepthOrArraySize=1;
    rd.MipLevels=1;rd.SampleDesc.Count=1;rd.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;rd.Flags=D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS;
    D3D12_HEAP_PROPERTIES hp={0};hp.Type=D3D12_HEAP_TYPE_DEFAULT;ID3D12Resource*out=NULL,*read=NULL;
    HR(s_d3d.device->lpVtbl->CreateCommittedResource(s_d3d.device,&hp,0,&rd,D3D12_RESOURCE_STATE_COMMON,NULL,&IID_ID3D12Resource,(void**)&out));
    hp.Type=D3D12_HEAP_TYPE_READBACK;rd.Flags=0;
    HR(s_d3d.device->lpVtbl->CreateCommittedResource(s_d3d.device,&hp,0,&rd,D3D12_RESOURCE_STATE_COPY_DEST,NULL,&IID_ID3D12Resource,(void**)&read));
    D3D12_RESOURCE_BARRIER output_state={0};output_state.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    output_state.Transition.pResource=out;output_state.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    output_state.Transition.StateBefore=D3D12_RESOURCE_STATE_COMMON;output_state.Transition.StateAfter=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
    s_d3d.cmd_list->lpVtbl->ResourceBarrier(s_d3d.cmd_list,1,&output_state);
    int slots[3]={a,b,cube};ID3D12Resource*kept[3];
    for(unsigned i=0;i<3;i++){
        kept[i]=s_d3d.vp_tex[slots[i]].res;
        srv_write_ex(i,kept[i],DXGI_FORMAT_R8G8B8A8_UNORM,D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING,i==2);
        D3D12_RESOURCE_BARRIER tr={0};tr.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;tr.Transition.pResource=kept[i];
        tr.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;tr.Transition.StateBefore=D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
        tr.Transition.StateAfter=D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;s_d3d.cmd_list->lpVtbl->ResourceBarrier(s_d3d.cmd_list,1,&tr);
    }
    /* A later upload/descriptor must preserve all already recorded bindings. */
    int later=upload(2);REQUIRE(later>=0&&later!=a&&later!=b&&later!=cube);
    srv_write_ex(3,s_d3d.vp_tex[later].res,DXGI_FORMAT_R8G8B8A8_UNORM,D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING,0);
    s_d3d.cmd_list->lpVtbl->SetDescriptorHeaps(s_d3d.cmd_list,1,&s_d3d.srv_heap);
    s_d3d.cmd_list->lpVtbl->SetComputeRootSignature(s_d3d.cmd_list,root);s_d3d.cmd_list->lpVtbl->SetPipelineState(s_d3d.cmd_list,pso);REQUIRE(rsx_gpu_reference_hold(&s_gpu_pso_refs,pso,&s_gpu_pso_ops));
    D3D12_GPU_DESCRIPTOR_HANDLE start;s_d3d.srv_heap->lpVtbl->GetGPUDescriptorHandleForHeapStart(s_d3d.srv_heap,&start);
    s_d3d.cmd_list->lpVtbl->SetComputeRootDescriptorTable(s_d3d.cmd_list,0,start);
    s_d3d.cmd_list->lpVtbl->SetComputeRootUnorderedAccessView(s_d3d.cmd_list,1,out->lpVtbl->GetGPUVirtualAddress(out));s_d3d.cmd_list->lpVtbl->Dispatch(s_d3d.cmd_list,1,1,1);
    D3D12_RESOURCE_BARRIER tr={0};tr.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;tr.Transition.pResource=out;tr.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    tr.Transition.StateBefore=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;tr.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;s_d3d.cmd_list->lpVtbl->ResourceBarrier(s_d3d.cmd_list,1,&tr);
    s_d3d.cmd_list->lpVtbl->CopyBufferRegion(s_d3d.cmd_list,read,0,out,0,128);
    for(unsigned i=0;i<3;i++){
        tr.Transition.pResource=kept[i];tr.Transition.StateBefore=D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;tr.Transition.StateAfter=D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
        s_d3d.cmd_list->lpVtbl->ResourceBarrier(s_d3d.cmd_list,1,&tr);
    }
    ID3D12Fence*gate=NULL;HR(s_d3d.device->lpVtbl->CreateFence(s_d3d.device,0,0,&IID_ID3D12Fence,(void**)&gate));HR(s_d3d.cmd_queue->lpVtbl->Wait(s_d3d.cmd_queue,gate,1));submit();
    for(unsigned i=0;i<3;i++)REQUIRE(s_d3d.vp_tex[slots[i]].res==kept[i]&&s_d3d.vp_tex[slots[i]].used);
    HANDLE worker=CreateThread(NULL,0,release_gate,gate,0,NULL);REQUIRE(worker);gpu_pso_retire();
    REQUIRE(WaitForSingleObject(worker,2000)==WAIT_OBJECT_0);DWORD code=1;REQUIRE(GetExitCodeThread(worker,&code)&&code==0);CloseHandle(worker);gate->lpVtbl->Release(gate);
    D3D12_RANGE read_range={0,128};uint32_t*values=NULL;HR(read->lpVtbl->Map(read,0,&read_range,(void**)&values));
    const uint32_t expected[8][4]={{255,0,0,255},{0,255,0,255},{0,0,0,255},{255,0,0,255},{0,255,0,255},{255,255,0,255},{0,0,255,255},{255,0,255,255}};
    for(unsigned i=0;i<8;i++)for(unsigned c=0;c<4;c++)REQUIRE(values[4*i+c]==expected[i][c]);
    D3D12_RANGE written={0,0};read->lpVtbl->Unmap(read,0,&written);read->lpVtbl->Release(read);out->lpVtbl->Release(out);
    pso->lpVtbl->Release(pso);root->lpVtbl->Release(root);signature->lpVtbl->Release(signature);cs->lpVtbl->Release(cs);
}
int main(int argc,char**argv){
 _set_error_mode(_OUT_TO_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
 ID3D12Debug*debug=NULL;HR(D3D12GetDebugInterface(&IID_ID3D12Debug,(void**)&debug));debug->lpVtbl->EnableDebugLayer(debug);debug->lpVtbl->Release(debug);
 const char*choice=getenv("RSX_TEST_ADAPTER");int warp=choice&&!strcmp(choice,"warp");IDXGIAdapter*chosen=NULL;
 if(warp){IDXGIFactory4*f=NULL;HR(CreateDXGIFactory1(&IID_IDXGIFactory4,(void**)&f));HR(f->lpVtbl->EnumWarpAdapter(f,&IID_IDXGIAdapter,(void**)&chosen));f->lpVtbl->Release(f);}
 HR(D3D12CreateDevice(chosen,D3D_FEATURE_LEVEL_11_0,&IID_ID3D12Device,(void**)&s_d3d.device));if(chosen)chosen->lpVtbl->Release(chosen);
 LUID luid;s_d3d.device->lpVtbl->GetAdapterLuid(s_d3d.device,&luid);
 IDXGIFactory4*factory=NULL;IDXGIAdapter1*adapter=NULL;DXGI_ADAPTER_DESC1 ad;
 HR(CreateDXGIFactory1(&IID_IDXGIFactory4,(void**)&factory));
 HR(factory->lpVtbl->EnumAdapterByLuid(factory,luid,&IID_IDXGIAdapter1,(void**)&adapter));HR(adapter->lpVtbl->GetDesc1(adapter,&ad));
 printf("Adapter vendor=%04X device=%04X flags=%u name=%ls\n",ad.VendorId,ad.DeviceId,ad.Flags,ad.Description);
 REQUIRE(warp?!!(ad.Flags&DXGI_ADAPTER_FLAG_SOFTWARE):!(ad.Flags&DXGI_ADAPTER_FLAG_SOFTWARE));adapter->lpVtbl->Release(adapter);factory->lpVtbl->Release(factory);
 ID3D12InfoQueue*info=NULL;HR(s_d3d.device->lpVtbl->QueryInterface(s_d3d.device,&IID_ID3D12InfoQueue,(void**)&info));
 D3D12_COMMAND_QUEUE_DESC q={0};q.Type=D3D12_COMMAND_LIST_TYPE_DIRECT;
 HR(s_d3d.device->lpVtbl->CreateCommandQueue(s_d3d.device,&q,&IID_ID3D12CommandQueue,(void**)&s_d3d.cmd_queue));
 HR(s_d3d.device->lpVtbl->CreateCommandAllocator(s_d3d.device,D3D12_COMMAND_LIST_TYPE_DIRECT,&IID_ID3D12CommandAllocator,(void**)&s_d3d.cmd_allocators[0]));
 HR(s_d3d.device->lpVtbl->CreateCommandList(s_d3d.device,0,D3D12_COMMAND_LIST_TYPE_DIRECT,s_d3d.cmd_allocators[0],NULL,&IID_ID3D12GraphicsCommandList,(void**)&s_d3d.cmd_list));
 HR(s_d3d.device->lpVtbl->CreateFence(s_d3d.device,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void**)&s_d3d.fence));s_d3d.fence_event=CreateEvent(NULL,FALSE,FALSE,NULL);REQUIRE(s_d3d.fence_event);
 D3D12_DESCRIPTOR_HEAP_DESC hd={0};hd.Type=D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;hd.NumDescriptors=64;hd.Flags=D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
 HR(s_d3d.device->lpVtbl->CreateDescriptorHeap(s_d3d.device,&hd,&IID_ID3D12DescriptorHeap,(void**)&s_d3d.srv_heap));
 s_d3d.srv_inc=s_d3d.device->lpVtbl->GetDescriptorHandleIncrementSize(s_d3d.device,D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
 s_d3d.vp_tex_capacity=10;s_d3d.vp_tex=calloc(10,sizeof(VPTexSlot));REQUIRE(s_d3d.vp_tex);
 vm_base=calloc(1,2*1024*1024);REQUIRE(vm_base);
 for(unsigned id=0;id<11;id++)for(unsigned j=0;j<128*128;j++){
  uint8_t*v=vm_base+0x1000+id*0x10000+j*4;v[0]=255;v[1]=id%3==0?255:0;v[2]=id%3==1?255:0;v[3]=id%3==2?255:0;
 }
 const int growth=argc>1&&!strcmp(argv[1],"growth-only");
 REQUIRE(texture_retention_budget()==(growth?2u:1u)*1024*1024);
 ID3D12Fence*gate=NULL;
 if(argc>1) HR(s_d3d.cmd_list->lpVtbl->Close(s_d3d.cmd_list));
 if(argc>1&&!strcmp(argv[1],"stale-wake-only")){
  HR(s_d3d.device->lpVtbl->CreateFence(s_d3d.device,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void**)&gate));
  HR(s_d3d.cmd_queue->lpVtbl->Wait(s_d3d.cmd_queue,gate,1));
  REQUIRE(SetEvent(s_d3d.fence_event)); /* stale notification, not GPU completion */
  HANDLE worker=CreateThread(NULL,0,release_gate,gate,0,NULL);REQUIRE(worker);
  int retired_ok=rsx_gpu_reference_retire(&s_gpu_pso_refs,&s_gpu_pso_ops);REQUIRE(WaitForSingleObject(worker,2000)==WAIT_OBJECT_0);
  DWORD code=1;REQUIRE(GetExitCodeThread(worker,&code));CloseHandle(worker);REQUIRE(code==0);REQUIRE(retired_ok);
  REQUIRE(s_d3d.fence->lpVtbl->GetCompletedValue(s_d3d.fence)>=s_d3d.fence_values[0]);
  goto finish;
 }

 if(argc>1&&!strcmp(argv[1],"descriptor-only")){
  const u32 source=0x100000,stride=81920;
  for(unsigned f=0;f<6;f++)for(unsigned i=0;i<128*128;i++){
   uint8_t*p=vm_base+source+f*stride+i*4;p[0]=255;p[1]=(f&1)?255:0;p[2]=(f&2)?255:0;p[3]=(f&4)?255:0;
  }
  reset_commands();int a=upload(0),b=upload(1),c=vp_upload_tex_slot_impl(source,128,128,0xA5,1,2,NULL);REQUIRE(a>=0&&b>=0&&c>=0);
  sample_descriptors(a,b,c);gpu_pso_retire();texture_retention_begin_batch();
  for(unsigned i=0;i<s_d3d.vp_tex_capacity;i++)texture_slot_release(&s_d3d.vp_tex[i]);REQUIRE(!s_d3d.vp_tex_bytes);goto finish;
 }
 if(growth){
  reset_commands();for(unsigned id=0;id<10;id++)REQUIRE(upload(id)==(int)id);
  ID3D12Resource*keep=s_d3d.vp_tex[0].res;submit();REQUIRE(vp_upload_retire(NULL));
  gpu_pso_retire();texture_retention_begin_batch();reset_commands();
  int grown=upload(10);REQUIRE(grown==10&&s_d3d.vp_tex_capacity>10&&s_d3d.vp_tex[0].res==keep);
  capture(grown);submit();REQUIRE(vp_upload_retire(NULL));pixels_argb(vm_base+0x1000+10*0x10000);
  gpu_pso_retire();texture_retention_begin_batch();
  for(unsigned i=0;i<s_d3d.vp_tex_capacity;i++)texture_slot_release(&s_d3d.vp_tex[i]);REQUIRE(!s_d3d.vp_tex_bytes);
  goto finish;
 }
 if(argc==1){
 int a=upload(0),b=upload(1);fprintf(stderr,"slots A=%d B=%d bytes=%llu\n",a,b,(unsigned long long)s_d3d.vp_tex_bytes);REQUIRE(a==0&&b==1);ID3D12Resource*ra=s_d3d.vp_tex[a].res,*rbefore=s_d3d.vp_tex[b].res;
 capture(a);submit();REQUIRE(vp_upload_retire(NULL));pixels(255,0,0);
 gpu_pso_retire();texture_retention_begin_batch();reset_commands();
 int c=upload(2);REQUIRE(c==2&&s_d3d.vp_tex[a].res==ra&&s_d3d.vp_tex[b].res==rbefore);
 REQUIRE(upload(0)==a&&upload(1)==b);
 for(unsigned id=3;id<10;id++)REQUIRE(upload(id)==(int)id);
 REQUIRE(s_d3d.vp_tex_bytes>texture_retention_budget());REQUIRE(s_d3d.vp_tex_peak_over_budget==s_d3d.vp_tex_bytes-texture_retention_budget());
 capture(c);
 HR(s_d3d.device->lpVtbl->CreateFence(s_d3d.device,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void**)&gate));
 HR(s_d3d.cmd_queue->lpVtbl->Wait(s_d3d.cmd_queue,gate,1));submit();
 REQUIRE(!rsx_gpu_reference_retire(&s_gpu_pso_refs,&s_gpu_pso_ops));REQUIRE(s_d3d.vp_tex[a].res==ra&&s_d3d.vp_tex[b].res==rbefore&&s_d3d.vp_tex[a].used&&s_d3d.vp_tex[b].used);
 HR(gate->lpVtbl->Signal(gate,1));gpu_pso_retire();pixels(0,0,255);
 gpu_pso_retire();texture_retention_begin_batch();REQUIRE(s_d3d.vp_tex_bytes<=texture_retention_budget());REQUIRE(s_d3d.vp_tex_evictions>0);
 for(unsigned i=0;i<10;i++)texture_slot_release(&s_d3d.vp_tex[i]);REQUIRE(!s_d3d.vp_tex_bytes);
 }
 if(argc==1||strcmp(argv[1],"cube-only")) {
  reset_commands();int slot=upload(0);REQUIRE(slot>=0);
  capture(slot);submit();REQUIRE(vp_upload_retire(NULL));pixels_argb(vm_base+0x1000);
  gpu_pso_retire();texture_retention_begin_batch();reset_commands();
  vm_base[0x1000+7]^=255; /* outside the actual sparse 64-byte sampling step */
  REQUIRE(upload(0)==slot);capture(slot);submit();REQUIRE(vp_upload_retire(NULL));pixels_argb(vm_base+0x1000);
  gpu_pso_retire();texture_retention_begin_batch();
  for(unsigned i=0;i<10;i++)texture_slot_release(&s_d3d.vp_tex[i]);
 }
 const unsigned cube_off=0x100000,cube_stride=81920;
 for(unsigned f=0;f<6;f++)for(unsigned j=0;j<128*128;j++){
  uint8_t*v=vm_base+cube_off+f*cube_stride+j*4;v[0]=255;v[1]=(f&1)?255:0;v[2]=(f&2)?255:0;v[3]=(f&4)?255:0;
 }
 reset_commands();int cube=vp_upload_tex_slot_impl(cube_off,128,128,0xa5,1,2,NULL);REQUIRE(cube>=0);
 for(unsigned f=0;f<6;f++){
  capture_face(cube,f);submit();REQUIRE(vp_upload_retire(NULL));pixels_argb(vm_base+cube_off+f*cube_stride);
  gpu_pso_retire();texture_retention_begin_batch();reset_commands();
 }
 vm_base[cube_off+5*cube_stride+7]^=255;
 REQUIRE(vp_upload_tex_slot_impl(cube_off,128,128,0xa5,1,2,NULL)==cube);
 capture_face(cube,5);submit();REQUIRE(vp_upload_retire(NULL));pixels_argb(vm_base+cube_off+5*cube_stride);
 gpu_pso_retire();texture_retention_begin_batch();
 for(unsigned i=0;i<10;i++)texture_slot_release(&s_d3d.vp_tex[i]);REQUIRE(!s_d3d.vp_tex_bytes);
 finish: ;
 unsigned errors=0;uint64_t count=info->lpVtbl->GetNumStoredMessagesAllowedByRetrievalFilter(info);
 for(uint64_t i=0;i<count;i++){SIZE_T n=0;HR(info->lpVtbl->GetMessage(info,i,NULL,&n));D3D12_MESSAGE*m=malloc(n);REQUIRE(m);HR(info->lpVtbl->GetMessage(info,i,m,&n));fprintf(stderr,"D3D12 validation severity=%u id=%u: %s\n",m->Severity,m->ID,m->pDescription);if(m->Severity<=D3D12_MESSAGE_SEVERITY_ERROR)++errors;free(m);}
 printf("D3D12 validation messages=%llu errors=%u\n",(unsigned long long)count,errors);REQUIRE(!errors);printf("PASS GPU phase=%s allocations=%llu evictions=%llu peak=%llu\n",argc>1?argv[1]:"full",(unsigned long long)s_d3d.vp_tex_allocations,(unsigned long long)s_d3d.vp_tex_evictions,(unsigned long long)s_d3d.vp_tex_peak_bytes);
 if(gate)gate->lpVtbl->Release(gate);if(rb)rb->lpVtbl->Release(rb);info->lpVtbl->Release(info);s_d3d.cmd_list->lpVtbl->Release(s_d3d.cmd_list);s_d3d.cmd_allocators[0]->lpVtbl->Release(s_d3d.cmd_allocators[0]);s_d3d.fence->lpVtbl->Release(s_d3d.fence);CloseHandle(s_d3d.fence_event);s_d3d.cmd_queue->lpVtbl->Release(s_d3d.cmd_queue);s_d3d.srv_heap->lpVtbl->Release(s_d3d.srv_heap);s_d3d.device->lpVtbl->Release(s_d3d.device);free(vm_base);free(s_d3d.vp_tex);return 0;
}

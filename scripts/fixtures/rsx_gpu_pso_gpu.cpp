// Authored D3D12 draws retain evicted cache entries until the GPU fence.
#include <windows.h>
#include <d3d12.h>
#include <d3d12sdklayers.h>
#include <dxgi1_4.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include "rsx_gpu_references.h"
using Microsoft::WRL::ComPtr;
static unsigned checks,failures;
static void check(bool ok,const char *s){++checks;if(!ok){++failures;fprintf(stderr,"FAIL %s\n",s);}}
static void hr(HRESULT h){if(FAILED(h)){char b[64];sprintf_s(b,"HRESULT %08X",(unsigned)h);throw std::runtime_error(b);}}
static ComPtr<ID3DBlob> compile(const char *s,const char *target){ComPtr<ID3DBlob>b,e;HRESULT h=D3DCompile(s,strlen(s),"authored",nullptr,nullptr,"main",target,0,0,&b,&e);if(FAILED(h)&&e)fprintf(stderr,"%.*s",(int)e->GetBufferSize(),(char*)e->GetBufferPointer());hr(h);return b;}
struct retirement{ID3D12Device *device;ID3D12Fence *fence;HANDLE event;UINT64 value;bool fail;};
static void retain(void *,void *p){((ID3D12PipelineState*)p)->AddRef();}
static void release(void *,void *p){((ID3D12PipelineState*)p)->Release();}
static int retire(void *p){auto &r=*(retirement*)p;if(r.fail)return 0;if(r.fence->GetCompletedValue()<r.value){if(FAILED(r.fence->SetEventOnCompletion(r.value,r.event))||WaitForSingleObject(r.event,30000)!=WAIT_OBJECT_0)return 0;}return r.device->GetDeviceRemovedReason()==S_OK&&r.fence->GetCompletedValue()>=r.value;}
int main(int argc,char **argv){try{
 bool hardware=argc>1&&!strcmp(argv[1],"--hardware");ComPtr<ID3D12Debug>debug;if(SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug))))debug->EnableDebugLayer();
 ComPtr<IDXGIFactory4>factory;hr(CreateDXGIFactory1(IID_PPV_ARGS(&factory)));ComPtr<IDXGIAdapter>adapter;if(!hardware)hr(factory->EnumWarpAdapter(IID_PPV_ARGS(&adapter)));
 ComPtr<ID3D12Device>device;hr(D3D12CreateDevice(adapter.Get(),D3D_FEATURE_LEVEL_11_0,IID_PPV_ARGS(&device)));
 ComPtr<ID3D12InfoQueue>info;device.As(&info);printf("debug_layer=%s info_queue=%s\n",debug?"enabled":"unavailable",info?"available":"unavailable");
 D3D12_COMMAND_QUEUE_DESC qd={};ComPtr<ID3D12CommandQueue>queue;hr(device->CreateCommandQueue(&qd,IID_PPV_ARGS(&queue)));
 ComPtr<ID3D12CommandAllocator>alloc;hr(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,IID_PPV_ARGS(&alloc)));
 ComPtr<ID3D12GraphicsCommandList>list;hr(device->CreateCommandList(0,D3D12_COMMAND_LIST_TYPE_DIRECT,alloc.Get(),nullptr,IID_PPV_ARGS(&list)));
 D3D12_ROOT_SIGNATURE_DESC rd={};ComPtr<ID3DBlob>serialized,error;hr(D3D12SerializeRootSignature(&rd,D3D_ROOT_SIGNATURE_VERSION_1,&serialized,&error));ComPtr<ID3D12RootSignature>root;hr(device->CreateRootSignature(0,serialized->GetBufferPointer(),serialized->GetBufferSize(),IID_PPV_ARGS(&root)));
 auto vs=compile("float4 main(uint i:SV_VertexID):SV_POSITION{float2 p[3]={float2(-1,-1),float2(-1,3),float2(3,-1)};return float4(p[i],0,1);}","vs_5_0");
 auto red=compile("float4 main():SV_TARGET{return float4(1,0,0,1);}","ps_5_0"),green=compile("float4 main():SV_TARGET{return float4(0,1,0,1);}","ps_5_0");
 D3D12_GRAPHICS_PIPELINE_STATE_DESC pd={};pd.pRootSignature=root.Get();pd.VS={vs->GetBufferPointer(),vs->GetBufferSize()};pd.SampleMask=UINT_MAX;pd.RasterizerState.FillMode=D3D12_FILL_MODE_SOLID;pd.RasterizerState.CullMode=D3D12_CULL_MODE_NONE;pd.RasterizerState.DepthClipEnable=TRUE;auto &blend=pd.BlendState.RenderTarget[0];blend.SrcBlend=blend.SrcBlendAlpha=D3D12_BLEND_ONE;blend.DestBlend=blend.DestBlendAlpha=D3D12_BLEND_ZERO;blend.BlendOp=blend.BlendOpAlpha=D3D12_BLEND_OP_ADD;blend.RenderTargetWriteMask=D3D12_COLOR_WRITE_ENABLE_ALL;pd.PrimitiveTopologyType=D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;pd.NumRenderTargets=1;pd.RTVFormats[0]=DXGI_FORMAT_R8G8B8A8_UNORM;pd.SampleDesc.Count=1;
 D3D12_HEAP_PROPERTIES hp={};hp.Type=D3D12_HEAP_TYPE_DEFAULT;D3D12_RESOURCE_DESC td={};td.Dimension=D3D12_RESOURCE_DIMENSION_TEXTURE2D;td.Width=td.Height=8;td.DepthOrArraySize=td.MipLevels=1;td.Format=DXGI_FORMAT_R8G8B8A8_UNORM;td.SampleDesc.Count=1;td.Flags=D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET;ComPtr<ID3D12Resource>target;hr(device->CreateCommittedResource(&hp,D3D12_HEAP_FLAG_NONE,&td,D3D12_RESOURCE_STATE_RENDER_TARGET,nullptr,IID_PPV_ARGS(&target)));
 D3D12_DESCRIPTOR_HEAP_DESC hd={};hd.Type=D3D12_DESCRIPTOR_HEAP_TYPE_RTV;hd.NumDescriptors=1;ComPtr<ID3D12DescriptorHeap>heap;hr(device->CreateDescriptorHeap(&hd,IID_PPV_ARGS(&heap)));auto rtv=heap->GetCPUDescriptorHandleForHeapStart();device->CreateRenderTargetView(target.Get(),nullptr,rtv);
 D3D12_PLACED_SUBRESOURCE_FOOTPRINT fp={};UINT rows=0;UINT64 rowbytes=0,total=0;device->GetCopyableFootprints(&td,0,1,0,&fp,&rows,&rowbytes,&total);D3D12_RESOURCE_DESC bd={};bd.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;bd.Width=total;bd.Height=bd.DepthOrArraySize=bd.MipLevels=1;bd.SampleDesc.Count=1;bd.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;hp.Type=D3D12_HEAP_TYPE_READBACK;ComPtr<ID3D12Resource>readback;hr(device->CreateCommittedResource(&hp,D3D12_HEAP_FLAG_NONE,&bd,D3D12_RESOURCE_STATE_COPY_DEST,nullptr,IID_PPV_ARGS(&readback)));
 ComPtr<ID3D12Fence>fence;hr(device->CreateFence(0,D3D12_FENCE_FLAG_NONE,IID_PPV_ARGS(&fence)));HANDLE event=CreateEventW(nullptr,FALSE,FALSE,nullptr);if(!event)throw std::runtime_error("CreateEvent");retirement done={device.Get(),fence.Get(),event,1,true};rsx_gpu_reference_ops ops={&done,retain,release,retire};rsx_gpu_references held={};
 list->SetGraphicsRootSignature(root.Get());list->OMSetRenderTargets(1,&rtv,FALSE,nullptr);D3D12_VIEWPORT vp={0,0,8,8,0,1};list->RSSetViewports(1,&vp);list->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
 for(unsigned n=0;n<2;++n){auto blob=n?green:red;pd.PS={blob->GetBufferPointer(),blob->GetBufferSize()};ComPtr<ID3D12PipelineState>cache;hr(device->CreateGraphicsPipelineState(&pd,IID_PPV_ARGS(&cache)));if(!rsx_gpu_reference_hold(&held,cache.Get(),&ops))throw std::runtime_error("hold");if(!n)check(rsx_gpu_reference_hold(&held,cache.Get(),&ops)&&held.count==1,"real PSO repeated binding retained once");list->SetPipelineState(cache.Get());D3D12_RECT rect={(LONG)(n*4),0,(LONG)(n*4+4),8};list->RSSetScissorRects(1,&rect);list->DrawInstanced(3,1,0,0);cache.Reset();}
 check(held.count==2,"evicted cache PSOs owned by recorded submission");check(!rsx_gpu_reference_retire(&held,&ops)&&held.count==2,"failed retirement preserves real PSOs");
 D3D12_RESOURCE_BARRIER barrier={};barrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;barrier.Transition.pResource=target.Get();barrier.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;barrier.Transition.StateBefore=D3D12_RESOURCE_STATE_RENDER_TARGET;barrier.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;list->ResourceBarrier(1,&barrier);D3D12_TEXTURE_COPY_LOCATION dst={};dst.pResource=readback.Get();dst.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;dst.PlacedFootprint=fp;D3D12_TEXTURE_COPY_LOCATION src={};src.pResource=target.Get();src.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;list->CopyTextureRegion(&dst,0,0,0,&src,nullptr);hr(list->Close());ID3D12CommandList *commands[]={list.Get()};queue->ExecuteCommandLists(1,commands);hr(queue->Signal(fence.Get(),1));done.fail=false;bool retired=rsx_gpu_reference_retire(&held,&ops)!=0;check(retired&&!held.count,"fenced execution releases real PSOs");if(!retired)throw std::runtime_error("GPU retirement");
 void *data=nullptr;D3D12_RANGE range={0,(SIZE_T)total};hr(readback->Map(0,&range,&data));bool pixels=true;for(unsigned y=0;y<8;++y)for(unsigned x=0;x<8;++x){auto p=(unsigned char*)data+fp.Offset+y*fp.Footprint.RowPitch+x*4;pixels &= p[0]==(x<4?255:0)&&p[1]==(x<4?0:255)&&p[2]==0&&p[3]==255;}readback->Unmap(0,nullptr);check(pixels,"all pixels from both evicted PSOs");
 unsigned critical=0;if(info)for(UINT64 i=0;i<info->GetNumStoredMessages();++i){SIZE_T size=0;hr(info->GetMessage(i,nullptr,&size));auto message=(D3D12_MESSAGE*)malloc(size);if(!message)throw std::runtime_error("message allocation");hr(info->GetMessage(i,message,&size));if(message->Severity<=D3D12_MESSAGE_SEVERITY_ERROR){fprintf(stderr,"%s\n",message->pDescription);++critical;}free(message);}check(!critical,"no critical D3D12 validation errors");CloseHandle(event);printf("checks=%u failures=%u\n",checks,failures);return failures?1:0;
 }catch(const std::exception &e){fprintf(stderr,"%s\n",e.what());return 2;}}

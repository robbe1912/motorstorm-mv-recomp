/* Authored NV40 PK2H programs through the production decompiler and GPU. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <limits>
#include "rsx_fp_decompiler.h"
using Microsoft::WRL::ComPtr;
static void checked(HRESULT hr,const char* what) {
    if(FAILED(hr)){fprintf(stderr,"%s: %08X\n",what,(unsigned)hr);exit(2);}
}
static ComPtr<ID3DBlob> compile(const std::string& text,const char* target) {
    ComPtr<ID3DBlob> code,error;
    HRESULT hr=D3DCompile(text.data(),text.size(),nullptr,nullptr,nullptr,"main",target,
                         D3DCOMPILE_OPTIMIZATION_LEVEL3,0,&code,&error);
    if(FAILED(hr)&&error)fwrite(error->GetBufferPointer(),1,error->GetBufferSize(),stderr);
    checked(hr,"compile");return code;
}
static void word(u8* p,u32 v) {
    v=(v<<16)|(v>>16);p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;
}
static std::string shader(unsigned mask,bool half_source,bool omit) {
    u8 code[32]={};u8* ins=code;
    const u32 swizzle=0xE4u<<9,exec=7u<<18;
    if(half_source){
        word(ins,(1u<<24)|(15u<<9)|(1u<<7)|(1u<<1)|(4u<<13));
        word(ins+4,swizzle|exec|1u);ins+=16;
    }
    word(ins,((omit?0u:0x24u)<<24)|(mask<<9)|(4u<<13)|1u);
    word(ins+4,swizzle|exec|(half_source?(1u<<8)|(1u<<2):1u));
    static char hlsl[65536];
    int n=rsx_fp_decompile(code,half_source?32:16,0x40,hlsl,sizeof hlsl);
    if(n!=(half_source?2:1)){fprintf(stderr,"decompile failed\n");exit(2);}
    std::string s=hlsl;
    // TC0 is unbounded; COL0/COL1 are correctly clamped before FP execution.
    // Supply exact source bits at PS entry, avoiding interpolation of -0.
    std::string entry="float4 main(PSInput input) : SV_TARGET";
    auto at=s.find(entry);if(at==s.npos){fprintf(stderr,"missing entry\n");exit(2);}
    s.replace(at,entry.size(),"uint4 main(PSInput input) : SV_TARGET");
    at=s.find('{',at);s.insert(at+1,"\n input.tc0=asfloat(test_bits);\n");
    const std::string tail="return (_o == _o) ? _o : (float4)0;";
    at=s.find(tail);if(at==s.npos){fprintf(stderr,"missing export\n");exit(2);}
    // Integer export observes packed bits, including float subnormals, directly.
    s.replace(at,tail.size(),"return asuint(r[0]);");
    return "cbuffer TestValues : register(b2) { uint4 test_bits; };\n"+s;
}
int main(int argc,char** argv) {
    bool hardware=false,omit=false;
    for(int i=1;i<argc;++i){hardware|=!strcmp(argv[i],"--hardware");omit|=!strcmp(argv[i],"--omit-pack");}
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> ctx;D3D_FEATURE_LEVEL level;
    checked(D3D11CreateDevice(nullptr,hardware?D3D_DRIVER_TYPE_HARDWARE:D3D_DRIVER_TYPE_WARP,
        nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,&level,&ctx),"device");
    auto vs_code=compile("struct O { float4 p:SV_POSITION; }; O main(uint i:SV_VertexID) { O o; "
        "o.p=float4(i==2?3:-1,i==1?3:-1,0,1);return o;}","vs_5_0");
    ComPtr<ID3D11VertexShader> vs;checked(device->CreateVertexShader(vs_code->GetBufferPointer(),vs_code->GetBufferSize(),nullptr,&vs),"VS");
    D3D11_TEXTURE2D_DESC td={};td.Width=td.Height=1;td.MipLevels=td.ArraySize=1;
    td.Format=DXGI_FORMAT_R32G32B32A32_UINT;td.SampleDesc.Count=1;td.BindFlags=D3D11_BIND_RENDER_TARGET;
    ComPtr<ID3D11Texture2D> rt,readback;checked(device->CreateTexture2D(&td,nullptr,&rt),"target");
    td.BindFlags=0;td.Usage=D3D11_USAGE_STAGING;td.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
    checked(device->CreateTexture2D(&td,nullptr,&readback),"readback");
    ComPtr<ID3D11RenderTargetView> rtv;checked(device->CreateRenderTargetView(rt.Get(),nullptr,&rtv),"RTV");
    D3D11_BUFFER_DESC bd={};bd.ByteWidth=16;bd.Usage=D3D11_USAGE_DEFAULT;bd.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    ComPtr<ID3D11Buffer> values;checked(device->CreateBuffer(&bd,nullptr,&values),"values");
    D3D11_RASTERIZER_DESC rd={};rd.FillMode=D3D11_FILL_SOLID;rd.CullMode=D3D11_CULL_NONE;rd.DepthClipEnable=TRUE;
    ComPtr<ID3D11RasterizerState> raster;checked(device->CreateRasterizerState(&rd,&raster),"raster");
    D3D11_VIEWPORT vp={0,0,1,1,0,1};ctx->RSSetViewports(1,&vp);ctx->RSSetState(raster.Get());
    ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);ctx->VSSetShader(vs.Get(),nullptr,0);
    ID3D11RenderTargetView* target=rtv.Get();ctx->OMSetRenderTargets(1,&target,nullptr);
    ID3D11Buffer* cb=values.Get();ctx->PSSetConstantBuffers(2,1,&cb);
    struct Case {float x,y;u32 expected;} cases[]={
        {.5f,.25f,0x34003800u},{-.5f,1.5f,0x3E00B800u},{-0.f,0.f,0x00008000u},
        {0.f,0.f,0},{1.00048828125f,1.00146484375f,0x3C023C00u},
        {0.000000059604644775390625f,65504.f,0x7BFF0001u},
        {-0.000000059604644775390625f,-65504.f,0xFBFF8001u},{65520.f,-65520.f,0xFC007C00u}
    };
    unsigned checks=0,failures=0;
    for(unsigned mode=0;mode<3;++mode){
        unsigned mask=mode==1?6:15;auto ps_code=compile(shader(mask,mode==2,omit),"ps_5_0");
        ComPtr<ID3D11PixelShader> ps;checked(device->CreatePixelShader(ps_code->GetBufferPointer(),ps_code->GetBufferSize(),nullptr,&ps),"PS");ctx->PSSetShader(ps.Get(),nullptr,0);
        for(unsigned i=0;i<sizeof cases/sizeof *cases;++i){
            float input[4]={cases[i].x,cases[i].y,0,0};
            // Half-source cases start with exactly representable register values;
            // full-source modes above exercise the pack instruction's rounding.
            if(mode==2 && i==4){input[0]=1.f;input[1]=1.001953125f;}
            if(mode==2 && i==7){input[0]=std::numeric_limits<float>::infinity();input[1]=-input[0];}
            ctx->UpdateSubresource(values.Get(),0,nullptr,input,0,0);
            ctx->Draw(3,0);ctx->CopyResource(readback.Get(),rt.Get());D3D11_MAPPED_SUBRESOURCE mapped;
            checked(ctx->Map(readback.Get(),0,D3D11_MAP_READ,0,&mapped),"map");u32 actual[4];memcpy(actual,mapped.pData,16);ctx->Unmap(readback.Get(),0);
            bool ok=true;for(unsigned c=0;c<4;++c)ok&=actual[c]==((mask&(1u<<c))?cases[i].expected:0u);
            ++checks;if(!ok)++failures;
            printf("%s mode=%u case=%u expected=%08X actual=%08X/%08X/%08X/%08X\n",ok?"PASS":"FAIL",mode,i,cases[i].expected,actual[0],actual[1],actual[2],actual[3]);
        }
    }
    printf("device=%s checks=%u failures=%u\n",hardware?"hardware":"WARP",checks,failures);return failures?1:0;
}

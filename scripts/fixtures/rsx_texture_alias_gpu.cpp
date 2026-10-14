/* Authored typed-render-target sampling regression; no guest payloads. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstring>
#include "rsx_texture_alias.h"
using Microsoft::WRL::ComPtr;

static void check(HRESULT hr, const char* what) {
    if (FAILED(hr)) { fprintf(stderr, "%s: %08X\n", what, (unsigned)hr); exit(2); }
}
static ComPtr<ID3DBlob> compile(const char* text, const char* target) {
    ComPtr<ID3DBlob> code, error;
    HRESULT hr = D3DCompile(text, strlen(text), nullptr, nullptr, nullptr, "main",
        target, D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &code, &error);
    if (FAILED(hr) && error) fwrite(error->GetBufferPointer(), 1, error->GetBufferSize(), stderr);
    check(hr, "D3DCompile"); return code;
}
int main(int argc, char** argv) {
    bool old = argc > 1 && !strcmp(argv[1], "--unpatched");
    bool hardware = argc > 1 && !strcmp(argv[1], "--hardware");
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    D3D_FEATURE_LEVEL level;
    check(D3D11CreateDevice(nullptr, hardware ? D3D_DRIVER_TYPE_HARDWARE : D3D_DRIVER_TYPE_WARP,
        nullptr, 0, nullptr, 0, D3D11_SDK_VERSION, &device, &level, &context), "device");
    if (level < D3D_FEATURE_LEVEL_11_0) return 2;
    auto vs = compile("float4 main(uint i:SV_VertexID):SV_Position {"
        "return float4(i==1?3:-1,i==2?3:-1,0,1);}", "vs_5_0");
    ComPtr<ID3D11VertexShader> vertex;
    check(device->CreateVertexShader(vs->GetBufferPointer(), vs->GetBufferSize(), nullptr, &vertex), "VS");
    context->VSSetShader(vertex.Get(), nullptr, 0);
    context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    D3D11_RASTERIZER_DESC raster = {}; raster.FillMode = D3D11_FILL_SOLID; raster.CullMode = D3D11_CULL_NONE;
    ComPtr<ID3D11RasterizerState> rs;
    check(device->CreateRasterizerState(&raster, &rs), "raster"); context->RSSetState(rs.Get());
    D3D11_VIEWPORT vp = {0,0,1,1,0,1}; context->RSSetViewports(1,&vp);
    // Host RGBA stores guest ARGB byte order. Four distinct XY16F pairs.
    unsigned char bytes[] = {0,0x38,0,0x3c, 0,0x40,0,0xbc,
                             0,0xb4,0,0x34, 0,0x42,0,0x40};
    D3D11_TEXTURE2D_DESC td = {}; td.Width=td.Height=2; td.MipLevels=td.ArraySize=1;
    td.Format=DXGI_FORMAT_R8G8B8A8_UNORM; td.SampleDesc.Count=1; td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    D3D11_SUBRESOURCE_DATA initial = {bytes,8,0}; ComPtr<ID3D11Texture2D> texture;
    check(device->CreateTexture2D(&td,&initial,&texture), "source");
    ComPtr<ID3D11ShaderResourceView> srv;
    check(device->CreateShaderResourceView(texture.Get(),nullptr,&srv), "SRV");
    ID3D11ShaderResourceView* views[16]; for (auto& view : views) view=srv.Get();
    context->PSSetShaderResources(0,16,views);
    td.Width=td.Height=1; td.Format=DXGI_FORMAT_R32G32B32A32_FLOAT; td.BindFlags=D3D11_BIND_RENDER_TARGET;
    ComPtr<ID3D11Texture2D> output, readback;
    check(device->CreateTexture2D(&td,nullptr,&output), "output");
    ComPtr<ID3D11RenderTargetView> rtv;
    check(device->CreateRenderTargetView(output.Get(),nullptr,&rtv), "RTV");
    auto rtvptr=rtv.Get(); context->OMSetRenderTargets(1,&rtvptr,nullptr);
    td.BindFlags=0; td.Usage=D3D11_USAGE_STAGING; td.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
    check(device->CreateTexture2D(&td,nullptr,&readback), "readback");
    struct Case { unsigned unit; float u,v; unsigned remap; bool named; float want[4];
                  const char* method; const char* extra; } cases[] = {
        {0,.25f,.25f,0x29e4,false,{1,.5f,0,1}},
        {0,.75f,.25f,0xaae4,false,{-1,2,0,1}},
        {0,-2,2,0xaae4,false,{.25f,-.25f,0,1}},
        {1,.5f,.5f,0xaae4,false,{.5625f,1.3125f,0,1}},
        {1,0,0,0xaae4,true,{.5625f,1.3125f,0,1}},
        {0,.25f,.25f,0xaa1b,false,{.5f,1,1,0},"SampleLevel",",0"},
        {1,.5f,.5f,0xaae4,false,{.5625f,1.3125f,0,1},"SampleBias",",0"},
    };
    int failed=0;
    unsigned remaps[16]={};
    for (unsigned index=0; index<sizeof cases/sizeof cases[0]; ++index) {
        const auto& c=cases[index]; char text[65536], name[32];
        if (c.named) snprintf(name,sizeof name,"rsx_tex%u",c.unit);
        else snprintf(name,sizeof name,"rsx_tex[%u]",c.unit);
        snprintf(text,sizeof text,
            "%s\nSamplerState rsx_samp[16]:register(s0);\n"
            "float4 main(float4 p:SV_Position):SV_Target { return %s.%s(rsx_samp[%u],float2(%.9g,%.9g)%s); }\n",
            c.named ? "Texture2D rsx_tex1:register(t1);" : "Texture2D rsx_tex[16]:register(t0);",
            name,c.method?c.method:"Sample",c.unit,(double)c.u,(double)c.v,c.extra?c.extra:"");
        remaps[c.unit]=c.remap;
        if (!old && rsx_texture_alias_apply(text,sizeof text,1u<<c.unit,remaps,c.named?4u:0u,1u)!=1) return 3;
        auto ps=compile(text,"ps_5_0"); ComPtr<ID3D11PixelShader> pixel;
        check(device->CreatePixelShader(ps->GetBufferPointer(),ps->GetBufferSize(),nullptr,&pixel),"PS");
        context->PSSetShader(pixel.Get(),nullptr,0);
        D3D11_SAMPLER_DESC sd={}; sd.MaxLOD=D3D11_FLOAT32_MAX;
        sd.Filter=c.unit==0?D3D11_FILTER_MIN_MAG_MIP_POINT:D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        sd.AddressU=sd.AddressV=sd.AddressW=c.unit==0?D3D11_TEXTURE_ADDRESS_CLAMP:D3D11_TEXTURE_ADDRESS_WRAP;
        ComPtr<ID3D11SamplerState> sampler; check(device->CreateSamplerState(&sd,&sampler),"sampler");
        auto sp=sampler.Get(); context->PSSetSamplers(c.unit,1,&sp);
        context->Draw(3,0); context->CopyResource(readback.Get(),output.Get());
        D3D11_MAPPED_SUBRESOURCE mapped; check(context->Map(readback.Get(),0,D3D11_MAP_READ,0,&mapped),"map");
        float actual[4]; memcpy(actual,mapped.pData,sizeof actual); context->Unmap(readback.Get(),0);
        bool ok=true; for(unsigned channel=0;channel<4;++channel)
            if (!std::isfinite(actual[channel]) || fabs(actual[channel]-c.want[channel])>1e-5f) ok=false;
        printf("case %u: %.6f %.6f %.6f %.6f %s\n",index,actual[0],actual[1],actual[2],actual[3],ok?"PASS":"FAIL");
        failed+=!ok;
    }
    char control[512]="Texture2D rsx_tex[16];\nfloat4 main():SV_Target{return 0;}\n", copy[512];
    strcpy(copy,control);
    if (rsx_texture_alias_apply(control,sizeof control,0,remaps,0,1)!=0 || strcmp(copy,control)) return 4;
    if (rsx_texture_alias_apply(control,sizeof control,1,remaps,1,1)!=-1) return 5;
    if (rsx_texture_alias_apply(control,strlen(control)+1,1,remaps,0,1)!=-1) return 6;
    if (rsx_texture_alias_xy16(0xbf,1)!=1 || rsx_texture_alias_xy16(0xa5,1) || rsx_texture_alias_xy16(0xbf,0)) return 7;
    if (rsx_texture_alias_key(1,remaps,1)==rsx_texture_alias_key(0,remaps,1)) return 8;
    printf("device=%s unpatched=%d failed=%d\n",hardware?"hardware":"WARP",old,failed);
    return failed?1:0;
}

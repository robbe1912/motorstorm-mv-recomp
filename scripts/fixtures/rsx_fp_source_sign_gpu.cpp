/* Authored source negation consumed as raw bits through the production decompiler. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "rsx_fp_decompiler.h"
using Microsoft::WRL::ComPtr;
static void checked(HRESULT hr,const char* what) {
    if(FAILED(hr)){fprintf(stderr,"%s: %08X\n",what,(unsigned)hr);exit(2);}
}
static ComPtr<ID3DBlob> compile(const std::string& text,const char* target) {
    ComPtr<ID3DBlob> code,error;
    HRESULT hr=D3DCompile(text.data(),text.size(),nullptr,nullptr,nullptr,"main",target,
                         0,0,&code,&error);
    if(FAILED(hr)&&error)fwrite(error->GetBufferPointer(),1,error->GetBufferSize(),stderr);
    checked(hr,"compile");return code;
}
static void word(u8* p,u32 v) {
    v=(v<<16)|(v>>16);p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;
}
static std::string shader(bool absolute,bool legacy) {
    u8 code[16]={};const u32 swizzle=0xE4u<<9,exec=7u<<18;
    word(code,(1u<<24)|(15u<<9)|(4u<<13)|1u);
    word(code+4,swizzle|exec|1u|(1u<<17)|(absolute?(1u<<29):0));
    static char hlsl[65536];
    if(rsx_fp_decompile(code,sizeof code,0x40,hlsl,sizeof hlsl)!=1)exit(2);
    std::string s=hlsl,entry="float4 main(PSInput input) : SV_TARGET";
    auto at=s.find(entry);if(at==s.npos)exit(2);
    s.replace(at,entry.size(),"uint4 main(PSInput input) : SV_TARGET");
    at=s.find('{',at);s.insert(at+1,"\n input.tc0=asfloat(test_bits);\n");
    const std::string tail="return (_o == _o) ? _o : (float4)0;";
    at=s.find(tail);if(at==s.npos)exit(2);
    s.replace(at,tail.size(),
        "uint bits=asuint(r[0].x); uint packed=(bits & 0xffff0000u) | "
        "(f32tof16(input.tc0.y) & 65535u); return uint4(packed,bits,asuint(r[0].y),0);");
    if(legacy){
        const std::string pre="asfloat(asuint(",post=") ^ 0x80000000u)";
        at=s.find(pre);if(at!=s.npos){auto end=s.find(post,at);if(end==s.npos)exit(2);
            auto expr=s.substr(at+pre.size(),end-at-pre.size());
            s.replace(at,end+post.size()-at,"-("+expr+")");}
    }
    return "cbuffer TestValues : register(b2) { uint4 test_bits; };\n"+s;
}
int main(int argc,char** argv) {
    bool hardware=false,legacy=false;
    for(int i=1;i<argc;++i){hardware|=!strcmp(argv[i],"--hardware");legacy|=!strcmp(argv[i],"--legacy-negate");}
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
    const u32 cases[]={0x3f000000u,0xbf000000u,0u,0x80000000u,
        0x7f800000u,0xff800000u,0x7fc12345u,0xffc12345u};
    unsigned checks=0,failures=0;
    for(unsigned mode=0;mode<2;++mode){
        auto ps_code=compile(shader(mode!=0,legacy),"ps_5_0");
        ComPtr<ID3D11PixelShader> ps;checked(device->CreatePixelShader(ps_code->GetBufferPointer(),ps_code->GetBufferSize(),nullptr,&ps),"PS");ctx->PSSetShader(ps.Get(),nullptr,0);
        for(unsigned i=0;i<sizeof cases/sizeof *cases;++i){
            u32 input[4]={cases[i],0x3e800000u,0,0};
            ctx->UpdateSubresource(values.Get(),0,nullptr,input,0,0);
            ctx->Draw(3,0);ctx->CopyResource(readback.Get(),rt.Get());D3D11_MAPPED_SUBRESOURCE mapped;
            checked(ctx->Map(readback.Get(),0,D3D11_MAP_READ,0,&mapped),"map");u32 actual[4];memcpy(actual,mapped.pData,16);ctx->Unmap(readback.Get(),0);
            u32 bits=(mode?(cases[i]&0x7fffffffu):cases[i])^0x80000000u;
            u32 expected[4]={(bits&0xffff0000u)|0x3400u,bits,0xbe800000u,0};
            bool ok=!memcmp(actual,expected,sizeof expected);++checks;if(!ok)++failures;
            printf("%s mode=%u case=%u expected=%08X actual=%08X bits=%08X/%08X\n",ok?"PASS":"FAIL",mode,i,expected[0],actual[0],bits,actual[1]);
        }
    }
    printf("checks=%u failures=%u\n",checks,failures);return failures?1:0;
}

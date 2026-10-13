#define WIN32_LEAN_AND_MEAN
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <vector>
#include <windows.h>
#include <wrl/client.h>
using Microsoft::WRL::ComPtr;
static void ck(HRESULT h, const char *s) {
  if (FAILED(h)) {
    fprintf(stderr, "%s HRESULT=%08X\n", s, (unsigned)h);
    exit(2);
  }
}
static std::vector<char> read(const char *p) {
  FILE *f = fopen(p, "rb");
  if (!f)
    exit(3);
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  rewind(f);
  if (n < 1 || n > 16 * 1024 * 1024)
    exit(4);
  std::vector<char> b(n);
  if (fread(b.data(), 1, n, f) != (size_t)n)
    exit(5);
  fclose(f);
  return b;
}
int main(int argc, char **argv) {
  if (argc != 6)
    return 2;
  bool hardware = strcmp(argv[5], "hardware") == 0;
  if (!hardware && strcmp(argv[5], "warp") != 0) {
    fprintf(stderr, "device must be hardware or warp\n");
    return 2;
  }
  auto source = read(argv[1]), vertices = read(argv[2]),
       constants = read(argv[3]);
  bool expect_zero = atoi(argv[4]) == 0;
  if (vertices.size() % 256 || constants.size() != 8224)
    return 6;
  ComPtr<ID3D11Device> d;
  ComPtr<ID3D11DeviceContext> c;
  D3D_FEATURE_LEVEL level;
  ck(D3D11CreateDevice(
         nullptr, (hardware ? D3D_DRIVER_TYPE_HARDWARE : D3D_DRIVER_TYPE_WARP),
         nullptr, 0, nullptr, 0, D3D11_SDK_VERSION, &d, &level, &c),
     "device");
  ComPtr<ID3DBlob> vsb, psb, err;
  HRESULT h = D3DCompile(source.data(), source.size(), argv[1], nullptr,
                         nullptr, "main", "vs_5_0",
                         D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &vsb, &err);
  if (FAILED(h) && err)
    fwrite(err->GetBufferPointer(), 1, err->GetBufferSize(), stderr);
  ck(h, "compile-vs");
  const char ps[] = "float4 main():SV_Target{return float4(0.3,0.6,0.9,1);}";
  ck(D3DCompile(ps, sizeof(ps) - 1, nullptr, nullptr, nullptr, "main", "ps_5_0",
                0, 0, &psb, &err),
     "compile-ps");
  ComPtr<ID3D11VertexShader> vs;
  ComPtr<ID3D11PixelShader> pixel;
  ck(d->CreateVertexShader(vsb->GetBufferPointer(), vsb->GetBufferSize(),
                           nullptr, &vs),
     "vs");
  ck(d->CreatePixelShader(psb->GetBufferPointer(), psb->GetBufferSize(),
                          nullptr, &pixel),
     "ps");
  D3D11_INPUT_ELEMENT_DESC il[16] = {};
  for (unsigned i = 0; i < 16; i++) {
    il[i].SemanticName = "ATTR";
    il[i].SemanticIndex = i;
    il[i].Format = DXGI_FORMAT_R32G32B32A32_FLOAT;
    il[i].AlignedByteOffset = i * 16;
  }
  ComPtr<ID3D11InputLayout> layout;
  ck(d->CreateInputLayout(il, 16, vsb->GetBufferPointer(), vsb->GetBufferSize(),
                          &layout),
     "layout");
  D3D11_BUFFER_DESC bd = {};
  bd.ByteWidth = (UINT)vertices.size();
  bd.Usage = D3D11_USAGE_IMMUTABLE;
  bd.BindFlags = D3D11_BIND_VERTEX_BUFFER;
  D3D11_SUBRESOURCE_DATA init = {vertices.data()};
  ComPtr<ID3D11Buffer> vb;
  ck(d->CreateBuffer(&bd, &init, &vb), "vb");
  bd.ByteWidth = (UINT)constants.size();
  bd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
  init.pSysMem = constants.data();
  ComPtr<ID3D11Buffer> cb;
  ck(d->CreateBuffer(&bd, &init, &cb), "cb");
  D3D11_TEXTURE2D_DESC td = {};
  td.Width = 256;
  td.Height = 256;
  td.MipLevels = 1;
  td.ArraySize = 1;
  td.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
  td.SampleDesc.Count = 1;
  td.BindFlags = D3D11_BIND_RENDER_TARGET;
  ComPtr<ID3D11Texture2D> rt, staging;
  ck(d->CreateTexture2D(&td, nullptr, &rt), "rt");
  td.BindFlags = 0;
  td.Usage = D3D11_USAGE_STAGING;
  td.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
  ck(d->CreateTexture2D(&td, nullptr, &staging), "staging");
  ComPtr<ID3D11RenderTargetView> view;
  ck(d->CreateRenderTargetView(rt.Get(), nullptr, &view), "rtv");
  D3D11_RASTERIZER_DESC rd = {};
  rd.FillMode = D3D11_FILL_SOLID;
  rd.CullMode = D3D11_CULL_NONE;
  rd.DepthClipEnable = FALSE;
  ComPtr<ID3D11RasterizerState> rs;
  ck(d->CreateRasterizerState(&rd, &rs), "rasterizer");
  float clear[4] = {};
  c->ClearRenderTargetView(view.Get(), clear);
  ID3D11RenderTargetView *rv = view.Get();
  c->OMSetRenderTargets(1, &rv, nullptr);
  D3D11_VIEWPORT vp = {0, 0, 256, 256, 0, 1};
  c->RSSetViewports(1, &vp);
  c->RSSetState(rs.Get());
  ID3D11Buffer *buf = vb.Get();
  UINT stride = 256, offset = 0;
  c->IASetVertexBuffers(0, 1, &buf, &stride, &offset);
  c->IASetInputLayout(layout.Get());
  c->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  c->VSSetShader(vs.Get(), nullptr, 0);
  buf = cb.Get();
  c->VSSetConstantBuffers(0, 1, &buf);
  c->PSSetShader(pixel.Get(), nullptr, 0);
  c->Draw((UINT)(vertices.size() / 256), 0);
  c->CopyResource(staging.Get(), rt.Get());
  D3D11_MAPPED_SUBRESOURCE m = {};
  ck(c->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &m), "readback");
  unsigned pixels = 0;
  for (unsigned y = 0; y < 256; y++) {
    auto row = (unsigned char *)m.pData + y * m.RowPitch;
    for (unsigned x = 0; x < 256; x++)
      if (row[x * 4] || row[x * 4 + 1] || row[x * 4 + 2])
        pixels++;
  }
  c->Unmap(staging.Get(), 0);
  printf("GPU fixture vertices=%zu covered_pixels=%u depth_clip=0 driver=%s "
         "expectation=%s\n",
         vertices.size() / 256, pixels, hardware ? "hardware" : "warp",
         expect_zero ? "zero" : "nonzero");
  return (expect_zero ? pixels == 0 : pixels > 0) ? 0 : 1;
}

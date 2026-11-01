#ifndef PS3RECOMP_RSX_D3D12_MRT_H
#define PS3RECOMP_RSX_D3D12_MRT_H
#include <d3d12.h>
/* Blend factors remain caller-owned; write enables are independent per target. */
static void rsx_d3d12_write_masks(D3D12_BLEND_DESC* b, unsigned nrt, unsigned masks) {
    b->IndependentBlendEnable = nrt > 1 ? TRUE : FALSE;
    for (unsigned r=0;r<nrt;r++) b->RenderTarget[r].RenderTargetWriteMask=(UINT8)((masks>>(r*4))&15u);
}
/* Enables are independent; common factors/equations remain caller-owned. */
static void rsx_d3d12_blend_enables(D3D12_BLEND_DESC* b, unsigned nrt, unsigned enables) {
    for (unsigned r=0;r<nrt;r++) b->RenderTarget[r].BlendEnable=(enables&(1u<<r))?TRUE:FALSE;
}
#endif

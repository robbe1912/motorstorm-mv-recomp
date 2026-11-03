/* Fallback shaders share their VS/root signature, but an absent depth
 * attachment requires a matching PSO rather than the depth-enabled variant. */
#ifndef RSX_D3D12_FALLBACK_H
#define RSX_D3D12_FALLBACK_H

static DXGI_FORMAT rsx_d3d12_depth_format(const D3D12_DEPTH_STENCIL_DESC* state)
{
    return state->DepthEnable || state->StencilEnable ?
        DXGI_FORMAT_D24_UNORM_S8_UINT : DXGI_FORMAT_UNKNOWN;
}

static HRESULT rsx_d3d12_fallback_no_depth(
    ID3D12Device* device, const D3D12_GRAPHICS_PIPELINE_STATE_DESC* attached,
    ID3D12PipelineState** result)
{
    D3D12_GRAPHICS_PIPELINE_STATE_DESC state = *attached;
    state.DepthStencilState.DepthEnable = FALSE;
    state.DepthStencilState.DepthWriteMask = D3D12_DEPTH_WRITE_MASK_ZERO;
    state.DepthStencilState.StencilEnable = FALSE;
    state.DSVFormat = rsx_d3d12_depth_format(&state.DepthStencilState);
    ID3D12PipelineState* replacement = NULL;
    HRESULT status = device->lpVtbl->CreateGraphicsPipelineState(device, &state,
        &IID_ID3D12PipelineState, (void**)&replacement);
    if (FAILED(status)) return status;
    if (*result) (*result)->lpVtbl->Release(*result);
    *result = replacement;
    return status;
}

static ID3D12PipelineState* rsx_d3d12_fallback_select(
    ID3D12PipelineState* compiled, int textured, int has_depth,
    ID3D12PipelineState* atlas, ID3D12PipelineState* color,
    ID3D12PipelineState* atlas_no_depth, ID3D12PipelineState* color_no_depth)
{
    if (compiled) return compiled;
    if (!has_depth) {
        atlas = atlas_no_depth;
        color = color_no_depth;
    }
    if (textured && atlas) return atlas;
    return color ? color : atlas;
}
#endif

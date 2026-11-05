/* Minimal authored D3D12 surface for the sampler-table regression. Copied to
 * a temporary include directory as d3d12.h, ahead of any SDK header, so the
 * production rsx_d3d12_guest_sampler.h and rsx_d3d12_sampler_tables.inc
 * compile unchanged against owner-tagged COM objects. */
#ifndef RSX_SAMPLER_D3D12_MOCK_H
#define RSX_SAMPLER_D3D12_MOCK_H
#include <stddef.h>
#include <stdint.h>
typedef int HRESULT;
typedef unsigned int UINT;
typedef size_t SIZE_T;
typedef uint64_t UINT64;
#define S_OK 0
#define FAILED(hr) ((hr) < 0)
#define D3D12_FLOAT32_MAX 3.402823466e+38f
typedef enum { D3D12_TEXTURE_ADDRESS_MODE_WRAP = 1, D3D12_TEXTURE_ADDRESS_MODE_MIRROR = 2,
               D3D12_TEXTURE_ADDRESS_MODE_CLAMP = 3, D3D12_TEXTURE_ADDRESS_MODE_BORDER = 4,
               D3D12_TEXTURE_ADDRESS_MODE_MIRROR_ONCE = 5 } D3D12_TEXTURE_ADDRESS_MODE;
typedef enum { D3D12_FILTER_MIN_MAG_MIP_POINT = 0, D3D12_FILTER_MIN_MAG_MIP_LINEAR = 0x15,
               D3D12_FILTER_ANISOTROPIC = 0x55 } D3D12_FILTER;
enum { D3D12_FILTER_TYPE_POINT = 0, D3D12_FILTER_TYPE_LINEAR = 1 };
enum { D3D12_FILTER_REDUCTION_TYPE_STANDARD = 0 };
#define D3D12_ENCODE_BASIC_FILTER(min, mag, mip, reduction) \
    ((D3D12_FILTER)((((min) & 3) << 4) | (((mag) & 3) << 2) | ((mip) & 3) | (((reduction) & 3) << 7)))
typedef enum { D3D12_COMPARISON_FUNC_ALWAYS = 8 } D3D12_COMPARISON_FUNC;
typedef struct {
    D3D12_FILTER Filter;
    D3D12_TEXTURE_ADDRESS_MODE AddressU, AddressV, AddressW;
    float MipLODBias;
    UINT MaxAnisotropy;
    D3D12_COMPARISON_FUNC ComparisonFunc;
    float BorderColor[4];
    float MinLOD, MaxLOD;
} D3D12_SAMPLER_DESC;
typedef enum { D3D12_DESCRIPTOR_HEAP_TYPE_SAMPLER = 1 } D3D12_DESCRIPTOR_HEAP_TYPE;
enum { D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE = 1 };
typedef struct { D3D12_DESCRIPTOR_HEAP_TYPE Type; UINT NumDescriptors; UINT Flags; UINT NodeMask; } D3D12_DESCRIPTOR_HEAP_DESC;
typedef struct { SIZE_T ptr; } D3D12_CPU_DESCRIPTOR_HANDLE;
typedef struct { UINT64 ptr; } D3D12_GPU_DESCRIPTOR_HANDLE;
typedef struct { int unused; } IID;
static const IID IID_ID3D12DescriptorHeap = {0};

typedef struct ID3D12Device ID3D12Device;
typedef struct ID3D12DescriptorHeap ID3D12DescriptorHeap;
typedef struct ID3D12GraphicsCommandList ID3D12GraphicsCommandList;
typedef struct {
    unsigned (*Release)(ID3D12DescriptorHeap*);
    D3D12_CPU_DESCRIPTOR_HANDLE* (*GetCPUDescriptorHandleForHeapStart)(ID3D12DescriptorHeap*, D3D12_CPU_DESCRIPTOR_HANDLE*);
    D3D12_GPU_DESCRIPTOR_HANDLE* (*GetGPUDescriptorHandleForHeapStart)(ID3D12DescriptorHeap*, D3D12_GPU_DESCRIPTOR_HANDLE*);
} ID3D12DescriptorHeapVtbl;
struct ID3D12DescriptorHeap { const ID3D12DescriptorHeapVtbl* lpVtbl; unsigned refs; ID3D12Device* owner; UINT64 base; };
typedef struct {
    HRESULT (*CreateDescriptorHeap)(ID3D12Device*, const D3D12_DESCRIPTOR_HEAP_DESC*, const IID*, void**);
    HRESULT (*GetDeviceRemovedReason)(ID3D12Device*);
    UINT (*GetDescriptorHandleIncrementSize)(ID3D12Device*, D3D12_DESCRIPTOR_HEAP_TYPE);
    void (*CreateSampler)(ID3D12Device*, const D3D12_SAMPLER_DESC*, D3D12_CPU_DESCRIPTOR_HANDLE);
} ID3D12DeviceVtbl;
struct ID3D12Device { const ID3D12DeviceVtbl* lpVtbl; HRESULT status; unsigned heaps; };
typedef struct {
    void (*SetDescriptorHeaps)(ID3D12GraphicsCommandList*, UINT, ID3D12DescriptorHeap* const*);
    void (*SetGraphicsRootDescriptorTable)(ID3D12GraphicsCommandList*, UINT, D3D12_GPU_DESCRIPTOR_HANDLE);
} ID3D12GraphicsCommandListVtbl;
struct ID3D12GraphicsCommandList { const ID3D12GraphicsCommandListVtbl* lpVtbl; };
typedef struct ID3D12Fence ID3D12Fence;
typedef struct { UINT64 (*GetCompletedValue)(ID3D12Fence*); } ID3D12FenceVtbl;
struct ID3D12Fence { const ID3D12FenceVtbl* lpVtbl; UINT64 value; };
#endif

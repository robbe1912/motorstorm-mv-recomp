/* Owner-thread PSO creation; a rejected disk blob gets one original-source
 * recompile, except device loss/OOM. No cache failure changes guest shaders. */
#ifndef RSX_SHADER_PSO_RECOVERY_H
#define RSX_SHADER_PSO_RECOVERY_H
static HRESULT shader_retry_vs_disk(int index,ID3DBlob** current)
{
    VPVSEntry* entry=&s_d3d.vp_vs[index];
    rsx_shader_key key={entry->disk_source,strlen(entry->disk_source),"guest_vp2","main","vs_5_0",0,0};
    rsx_shader_disk_remove(&s_shader_disk,&key);
    ID3DBlob *blob=NULL,*error=NULL;double begin=perf_now();
    HRESULT hr=fp_compile_uncached(&key,&blob,&error);
    if(SUCCEEDED(hr) && !blob)hr=E_FAIL;
    (void)begin;
    if(error){
        if(FAILED(hr))fprintf(stderr,"[SHADERCACHE] VS recovery compile failed: %s\n",
            (const char*)error->lpVtbl->GetBufferPointer(error));
        error->lpVtbl->Release(error);
    }
    if(SUCCEEDED(hr) && blob){
        shader_disk_store(&key,blob);
        entry->vs->lpVtbl->Release(entry->vs);entry->vs=blob;*current=blob;
        s_vs_disk_source_bytes-=key.bytes+1;free(entry->disk_source);entry->disk_source=NULL;
    }else if(blob)blob->lpVtbl->Release(blob);
    return hr;
}
static HRESULT shader_create_pso(D3D12_GRAPHICS_PIPELINE_STATE_DESC* desc,
    const char* fp_source,int vs_index,ID3DBlob** vs,ID3DBlob** ps,
    unsigned fp_disk,ID3D12PipelineState** output,double* driver_seconds)
{
    double begin=perf_now();*driver_seconds=0;
    HRESULT hr=s_d3d.device->lpVtbl->CreateGraphicsPipelineState(
        s_d3d.device,desc,&IID_ID3D12PipelineState,(void**)output);
    *driver_seconds+=perf_now()-begin;
    int vs_disk=vs_index>=0 && vs_index<s_d3d.vp_vs_n && s_d3d.vp_vs[vs_index].disk_source!=NULL;
    if(SUCCEEDED(hr) || (!fp_disk && !vs_disk) || hr==E_OUTOFMEMORY ||
        FAILED(s_d3d.device->lpVtbl->GetDeviceRemovedReason(s_d3d.device)))return hr;
    static unsigned notices;
    if(notices++<16)fprintf(stderr,"[SHADERCACHE] cached PSO rejected %08lX; retrying original sources once (FP=%u VS=%d)\n",
        (unsigned long)hr,fp_disk,vs_disk);
    if(*output){(*output)->lpVtbl->Release(*output);*output=NULL;}
    if(vs_disk){
        hr=shader_retry_vs_disk(vs_index,vs);
        if(FAILED(hr))return hr;
        desc->VS.pShaderBytecode=(*vs)->lpVtbl->GetBufferPointer(*vs);
        desc->VS.BytecodeLength=(*vs)->lpVtbl->GetBufferSize(*vs);
    }
    if(fp_disk){
        rsx_shader_key key={fp_source,strlen(fp_source),"guest_fp","main","ps_5_0",0,0};
        rsx_shader_disk_remove(&s_shader_disk,&key);
        rsx_shader_cache_remove(&s_fp_bytecode,&key,&s_fp_blob_ops);
        (*ps)->lpVtbl->Release(*ps);*ps=NULL;
        ID3DBlob* error=NULL;begin=perf_now();
        hr=fp_compile_uncached(&key,ps,&error);
        (void)begin;
        if(error){
            if(FAILED(hr))fprintf(stderr,"[SHADERCACHE] FP recovery compile failed: %s\n",
                (const char*)error->lpVtbl->GetBufferPointer(error));
            error->lpVtbl->Release(error);
        }
        if(FAILED(hr) || !*ps)return FAILED(hr)?hr:E_FAIL;
        shader_disk_store(&key,*ps);
        rsx_shader_cache_put(&s_fp_bytecode,&key,*ps,(*ps)->lpVtbl->GetBufferSize(*ps),&s_fp_blob_ops);
        desc->PS.pShaderBytecode=(*ps)->lpVtbl->GetBufferPointer(*ps);
        desc->PS.BytecodeLength=(*ps)->lpVtbl->GetBufferSize(*ps);
    }
    begin=perf_now();
    hr=s_d3d.device->lpVtbl->CreateGraphicsPipelineState(
        s_d3d.device,desc,&IID_ID3D12PipelineState,(void**)output);
    *driver_seconds+=perf_now()-begin;return hr;
}
#endif

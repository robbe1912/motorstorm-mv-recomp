/* Temporary named-build observer. No guest writes or behavioral substitutions. */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <atomic>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static std::atomic<unsigned> havok_probe_events{0};
static std::atomic<size_t> havok_probe_bytes{0};
static thread_local unsigned havok_probe_id;
static thread_local uint32_t havok_probe_stream;
static std::atomic<unsigned> havok_raw_slots{0};
static thread_local unsigned char* havok_raw_bytes;
static thread_local size_t havok_raw_length;
static thread_local uint32_t havok_raw_object;
static thread_local uint32_t havok_raw_ea;

static bool havok_probe_read(uint32_t ea, void* dst, size_t len)
{
    SIZE_T read = 0;
    return ea && (uint64_t)ea + len <= 0x100000000ULL &&
        ReadProcessMemory(GetCurrentProcess(), vm_base + ea, dst, len, &read) && read == len;
}

static uint32_t havok_probe_word(uint32_t ea)
{
    unsigned char b[4] = {};
    if (!havok_probe_read(ea, b, 4)) return 0;
    return ((uint32_t)b[0]<<24)|((uint32_t)b[1]<<16)|((uint32_t)b[2]<<8)|(uint32_t)b[3];
}

/* Private diagnostic cache: max four16MiB host buffers, no disk/log on success. */
static void havok_record_raw_oct10(ppu_context* ctx, uint32_t site = 0)
{
    (void)site;
    havok_raw_length=0;
    if (!getenv("CAP_HAVOK_DIR")) return;
    uint32_t object=(uint32_t)ctx->gpr[20];
    uint32_t length=havok_probe_word(object+0x20);
    if (!length || length>16*1024*1024) return;
    if (!havok_raw_bytes && havok_raw_slots.fetch_add(1)<4)
        havok_raw_bytes=(unsigned char*)malloc(16*1024*1024);
    if (!havok_raw_bytes) return;
    havok_raw_object=object;havok_raw_ea=(uint32_t)ctx->gpr[31];
    if (havok_probe_read(havok_raw_ea,havok_raw_bytes,length)) havok_raw_length=length;
}

static void havok_probe_dump(FILE* meta, const char* dir, unsigned event,
                             const char* label, uint32_t ea, size_t len)
{
    if (!ea || !len || len > 16*1024*1024) return;
    size_t before = havok_probe_bytes.fetch_add(len);
    if (before + len > 128*1024*1024) return;
    unsigned char* bytes = (unsigned char*)malloc(len);
    bool ok = bytes && havok_probe_read(ea, bytes, len);
    fprintf(meta, "dump %s ea=%08X size=%zu readable=%d\n", label, ea, len, ok);
    if (ok) {
        char path[1024];
        snprintf(path, sizeof(path), "%s/%04u_%s_%08X.bin", dir, event, label, ea);
        FILE* f = fopen(path, "wb");
        if (f) { fwrite(bytes, 1, len, f); fclose(f); }
    }
    free(bytes);
}

static void havok_probe_string(FILE* meta, const char* label, uint32_t ea)
{
    char str[257] = {};
    for (unsigned i=0;i<256;++i) {
        if (!havok_probe_read(ea+i, str+i, 1) || !str[i]) break;
        if ((unsigned char)str[i]<32 || (unsigned char)str[i]>126) str[i]='?';
    }
    fprintf(meta, "string %s ea=%08X value=%s\n", label, ea, str);
}

static void havok_probe_oct10(ppu_context* ctx, const char* stage, uint32_t site = 0)
{
    const char* dir = getenv("CAP_HAVOK_DIR");
    if (!dir || !*dir) return;
    unsigned event = havok_probe_events.fetch_add(1);
    if (event>=128) return;
    if (!strcmp(stage, "entry")) {
        havok_probe_id=event;
        havok_probe_stream=(uint32_t)ctx->gpr[5];
    }
    char path[1024];
    snprintf(path,sizeof(path),"%s/%04u_%s.txt",dir,event,stage);
    FILE *f=fopen(path,"wb");
    if (!f) return;
    fprintf(f,"stage=%s site=%08X ctor=%u thread=%lu tick=%llu lr=%08llX\n",stage,site,havok_probe_id,
            GetCurrentThreadId(),(unsigned long long)GetTickCount64(),ctx->lr);
    for (unsigned i=0;i<32;++i) fprintf(f,"r%u=%016llX\n",i,ctx->gpr[i]);
    if (!strcmp(stage,"fatal177")) {
        fprintf(f,"raw_cache object=%08X ea=%08X length=%zu matches=%d\n",
                havok_raw_object,havok_raw_ea,havok_raw_length,
                havok_raw_object==(uint32_t)ctx->gpr[20]);
        if (havok_raw_length && havok_raw_object==(uint32_t)ctx->gpr[20]) {
            char raw_path[1024];
            snprintf(raw_path,sizeof(raw_path),"%s/%04u_pre_relocation_%08X.bin",dir,event,havok_raw_ea);
            FILE *raw=fopen(raw_path,"wb");
            if (raw) { fwrite(havok_raw_bytes,1,havok_raw_length,raw);fclose(raw); }
        }
    }
    havok_probe_dump(f,dir,event,"stack",(uint32_t)ctx->gpr[1],4096);
    havok_probe_dump(f,dir,event,"stream",havok_probe_stream,256);
    if (!strcmp(stage,"entry")) {
        for (unsigned i=0;i<16;++i) {
            char label[32];snprintf(label,sizeof(label),"stream_ptr%u",i);
            havok_probe_dump(f,dir,event,label,havok_probe_word(havok_probe_stream+4*i),256);
        }
    } else {
        uint32_t object=(uint32_t)ctx->gpr[20];
        havok_probe_dump(f,dir,event,"resource",object,128);
        uint32_t data=havok_probe_word(object+0x24);
        uint32_t len=havok_probe_word(object+0x20);
        havok_probe_dump(f,dir,event,"packfile",data,len);
        if (!strcmp(stage,"raw"))
            havok_probe_dump(f,dir,event,"aligned_stream_bytes",(uint32_t)ctx->gpr[31],len);
        if (strcmp(stage,"raw")) {
            havok_probe_dump(f,dir,event,"result",(uint32_t)ctx->gpr[22],32);
            havok_probe_dump(f,dir,event,"reader",(uint32_t)ctx->gpr[25],128);
            uint32_t root=(uint32_t)ctx->gpr[24];
            havok_probe_dump(f,dir,event,"root",root,64);
            uint32_t variants=havok_probe_word(root);
            uint32_t count=havok_probe_word(root+4);
            fprintf(f,"root=%08X variants=%08X count=%u\n",root,variants,count);
            if (count<=64) {
                havok_probe_dump(f,dir,event,"variants",variants,16*count);
                for (unsigned i=0;i<count;++i) {
                    uint32_t v=variants+16*i;
                    char label[32];snprintf(label,sizeof(label),"name%u",i);
                    havok_probe_string(f,label,havok_probe_word(v));
                    snprintf(label,sizeof(label),"class%u",i);
                    havok_probe_string(f,label,havok_probe_word(v+4));
                    snprintf(label,sizeof(label),"variant%u",i);
                    havok_probe_dump(f,dir,event,label,havok_probe_word(v+8),256);
                }
            }
            for (unsigned offset=0x5750;offset<=0x575C;offset+=4) {
                char label[32];snprintf(label,sizeof(label),"class_toc_%X",offset);
                havok_probe_dump(f,dir,event,label,havok_probe_word((uint32_t)ctx->gpr[2]+offset),128);
            }
        }
    }
    fclose(f);
    fprintf(stderr,"[DEBUG-havok-oct10] event=%u ctor=%u stage=%s site=%08X\n",event,havok_probe_id,stage,site);
}

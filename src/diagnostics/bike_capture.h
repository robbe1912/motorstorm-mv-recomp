/* Temporary bike-lane observer for issue #24. No guest writes or behavioral
 * substitutions; reads guest memory only through the documented probe helpers.
 * All output is gated on CAP_BIKE_DIR so probe-off boots are unchanged. */
#ifndef BIKE_CAPTURE_H
#define BIKE_CAPTURE_H
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <atomic>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

static std::atomic<unsigned> bike_probe_events{0};

static bool bike_probe_read(uint32_t ea, void* dst, size_t len)
{
    SIZE_T read = 0;
    return ea && (uint64_t)ea + len <= 0x100000000ULL &&
        ReadProcessMemory(GetCurrentProcess(), vm_base + ea, dst, len, &read) && read == len;
}

static uint32_t bike_probe_word(uint32_t ea)
{
    unsigned char b[4] = {};
    if (!bike_probe_read(ea, b, 4)) return 0;
    return ((uint32_t)b[0]<<24)|((uint32_t)b[1]<<16)|((uint32_t)b[2]<<8)|b[3];
}

static void bike_probe_string(FILE* f, const char* label, uint32_t ea)
{
    char str[129] = {};
    if (ea) {
        for (unsigned i=0; i<128; ++i) {
            if (!bike_probe_read(ea+i, str+i, 1) || !str[i]) break;
            if ((unsigned char)str[i]<32 || (unsigned char)str[i]>126) str[i]='?';
        }
    }
    fprintf(f, "string %s ea=%08X value=%s\n", label, ea, ea ? str : "(null)");
}

static void bike_probe_dump(FILE* f, const char* label, uint32_t ea, size_t len)
{
    if (!ea || !len || len > 4096) return;
    unsigned char bytes[4096];
    bool ok = bike_probe_read(ea, bytes, len);
    fprintf(f, "dump %s ea=%08X size=%zu readable=%d\n", label, ea, len, ok);
    if (ok) {
        for (size_t i=0; i<len; i+=32) {
            fprintf(f, "  %08X:", (uint32_t)(ea+i));
            for (size_t j=0; j<32 && i+j<len; ++j) fprintf(f, " %02X", bytes[i+j]);
            fputc('\n', f);
        }
    }
}

/* Entry probe: one file per event, registers plus selected argument memory.
 * keep_bytes limits per-event guest dumps so long runs stay bounded. */
static void bike_probe_entry(ppu_context* ctx, const char* stage)
{
    const char* dir = getenv("CAP_BIKE_DIR");
    if (!dir || !*dir) return;
    /* High-frequency resource stages fire all through boot; late-gate them to
     * the observed selection-screen window so rare stages keep their slots. */
    static ULONGLONG boot_tick = GetTickCount64();
    bool frequent = !strcmp(stage,"rsload") || !strcmp(stage,"rsfind");
    if (frequent && GetTickCount64() - boot_tick < 240000) return;
    unsigned event = bike_probe_events.fetch_add(1);
    if (event>=1024) return;
    static unsigned stage_seen[16];
    unsigned slot = (unsigned)(stage[0] | (stage[1]<<8));
    slot &= 15;
    if (++stage_seen[slot] > 64) return;
    char path[1024];
    snprintf(path,sizeof(path),"%s/%04u_%s.txt",dir,event,stage);
    FILE* f=fopen(path,"wb");
    if (!f) return;
    fprintf(f,"stage=%s thread=%lu tick=%llu lr=%08llX\n",stage,
            GetCurrentThreadId(),(unsigned long long)GetTickCount64(),ctx->lr);
    for (unsigned i=0;i<32;++i) fprintf(f,"r%u=%016llX\n",i,ctx->gpr[i]);
    if (!strcmp(stage,"vpfn") || !strcmp(stage,"dynsel") || !strcmp(stage,"rsload")) {
        bike_probe_string(f,"name",(uint32_t)ctx->gpr[4]);
    }
    if (!strcmp(stage,"rsfind")) {
        /* ResourceIdentifier blob (r4): dump raw so its layout is observable. */
        bike_probe_dump(f,"identifier",(uint32_t)ctx->gpr[4],96);
    }
    if (!strcmp(stage,"sor") || !strcmp(stage,"vtload")) {
        /* this=r3, resource system=r4, stream=r5; dump stream header. */
        bike_probe_dump(f,"stream",(uint32_t)ctx->gpr[5],192);
        uint32_t vtable=bike_probe_word((uint32_t)ctx->gpr[5]);
        bike_probe_dump(f,"stream_vtable",vtable,128);
    }
    if (!strcmp(stage,"sor")) {
        /* SceneObjectResource base resource fields after the fact. */
        bike_probe_dump(f,"resourcesystem",(uint32_t)ctx->gpr[4],64);
    }
    fclose(f);
    fprintf(stderr,"[DEBUG-bike-oct11] event=%u stage=%s\n",event,stage);
}

#endif

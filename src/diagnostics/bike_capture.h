/* Temporary bike-lane observer for issue #24. No guest writes or behavioral
 * substitutions; reads guest memory only through the documented probe helpers.
 * All output is gated on CAP_BIKE_DIR so probe-off boots are unchanged. */
#ifndef BIKE_CAPTURE_H
#define BIKE_CAPTURE_H
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mutex>
#include <map>
#include <string>
#include <errno.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

/* One ledger across translation units; all mutations are protected. */
struct bike_probe_ledger {
    std::mutex mutex;
    std::map<std::string, unsigned> stages;
    unsigned events = 0;
    bool armed_reported = false;
    bool full_reported = false;
};
inline bike_probe_ledger bike_probe_counts;

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
 * Per-stage and global quotas bound output; exhaustion is explicit. */
static void bike_probe_entry(ppu_context* ctx, const char* stage)
{
    const char* dir = getenv("CAP_BIKE_DIR");
    if (!dir || !*dir || !ctx || !stage || !*stage) return;
    /* Operators create this marker before an observed selection input. Direct
     * users may omit it to capture from boot; no wall-time guess gates events. */
    const char* arm = getenv("CAP_BIKE_ARM_FILE");
    if (arm && *arm && GetFileAttributesA(arm) == INVALID_FILE_ATTRIBUTES) return;
    unsigned event;
    {
        std::lock_guard<std::mutex> lock(bike_probe_counts.mutex);
        auto& ledger = bike_probe_counts;
        if (!ledger.armed_reported) {
            ledger.armed_reported = true;
            fprintf(stderr, "[DEBUG-bike-oct11] armed dir=%s\n", dir);
        }
        if (ledger.events >= 1024 ||
            (ledger.stages.size() >= 32 && !ledger.stages.count(stage))) {
            if (!ledger.full_reported) {
                ledger.full_reported = true;
                fprintf(stderr, "[DEBUG-bike-oct11] global capture budget reached\n");
            }
            return;
        }
        unsigned& count = ledger.stages[stage];
        if (count >= 64) return;
        if (++count == 64)
            fprintf(stderr, "[DEBUG-bike-oct11] stage=%s capture budget reached\n", stage);
        event = ledger.events++;
    }
    char path[1024];
    snprintf(path,sizeof(path),"%s/%04u_%s.txt",dir,event,stage);
    FILE* f=fopen(path,"wb");
    if (!f) { fprintf(stderr,"[DEBUG-bike-oct11] capture fopen failed path=%s errno=%d\n",path,errno); return; }
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
    if (ferror(f)) fprintf(stderr,"[DEBUG-bike-oct11] capture write failed path=%s\n",path);
    if (fclose(f)) fprintf(stderr,"[DEBUG-bike-oct11] capture close failed path=%s errno=%d\n",path,errno);
    fprintf(stderr,"[DEBUG-bike-oct11] event=%u stage=%s\n",event,stage);
}

#endif

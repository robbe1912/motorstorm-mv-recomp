// Job manager services MotorStorm's native jobs call (SPU_PM_NATIVE_SVC=1,
// run.py --pm-native-services; default off). See "Native policy-module
// services" in vendor/ps3recomp/runtime/spu/spu_channels.c.
//
// Image 3 is the lifted job manager policy module. Its text is staged at
// LS 0xA00; the registered 0x2B80 bytes are the 11120-byte template at guest
// EA 0x10135E00 plus 16 zero bytes, FNV-1a C042E76A9A90E5BF.
//
// Entries: the bisl targets of job code (the vehicle job calls 0x1648 from
// segments 0/1, 0x1670 from segment 2, 0x2D68 from segments 3/4 and 0x1650
// from segments 5/6). Code ranges: every lifted function those entries reach
// by direct branches and calls (function start to the next function start),
// plus the targets of their indirect branches that are fixed in the text:
// 0x19D0 (passed by 0x1650 to 0x1560), 0x1A1C/0x1A60 and the 0x1540 jump
// table (0x2170, 0x1A60, 0x1B38, 0x2048, 0x20E8, 0x2134). The text between
// 0xC00 and 0x1440 also holds the job manager's live tables, so it is not
// registered; other indirect targets, such as the 0x9D0 kernel vector, run
// as before.
#include "spu_native_owned.h"

namespace {
constexpr uint32_t kEntries[] = {0x1670u, 0x1650u, 0x2D68u, 0x1648u};
constexpr uint32_t kCode[][2] = {
    {0x1560u, 0x1580u}, {0x1648u, 0x1908u}, {0x19D0u, 0x2180u}, {0x2190u, 0x21C0u},
    {0x2288u, 0x2400u}, {0x26E4u, 0x2748u}, {0x2750u, 0x2A10u}, {0x2B88u, 0x2CA0u},
    {0x2D68u, 0x3008u}, {0x33D8u, 0x3418u}, {0x3430u, 0x350Cu},
};
struct JobManagerServices {
    JobManagerServices() {
        spu_pm_services services{};
        services.image_id = 3;
        services.ls_base = 0xA00u;
        services.text_len = 0x2B80u;
        services.tmpl_ea = 0x10135E00u;
        services.tmpl_len = 11120u;
        services.text_fnv = 0xC042E76A9A90E5BFull;
        services.entries = kEntries;
        services.nentries = static_cast<int>(sizeof kEntries / sizeof kEntries[0]);
        services.code = kCode;
        services.ncode = static_cast<int>(sizeof kCode / sizeof kCode[0]);
        spu_pm_services_register(&services);
    }
};
const JobManagerServices g_job_manager_services;
}  // namespace

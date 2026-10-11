/*
 * ps3recomp game project -- entry point template.
 *
 * This is the runner. It boots a lifted title through the toolkit's PPU
 * scaffold: allocate the flat guest VM, load the PPU ELF named on the command
 * line, register the lifted function table and the HLE NID handlers, start a
 * frame clock, and dispatch the entry OPD.
 *
 * The scaffold does the work; nothing below reimplements it. ppu_load_elf,
 * ppu_recomp_register, ppu_hle_init, ppu_sysprx_register, ppu_fs_register,
 * lv2_init_syscalls and ppu_run all come from the toolkit, compiled into this
 * project from PS3RECOMP_DIR (see CMakeLists.txt). What is left here is the
 * part a port owns: which backend to present through, how the frame clock is
 * paced, and whatever diagnostics the title turns out to need.
 *
 * runtime/ppu/tests/boot_main.cpp in the toolkit is the same boot in its
 * fully-instrumented form -- crash filter, hang watchdog, guest-PC sampling
 * profiler. Read it when a boot goes wrong; copy from it what the title
 * needs. It is deliberately not what a fresh project starts with.
 *
 * The one part that IS duplicated from it is the frame clock below, because a
 * port is expected to change its pacing and a shared one would be the wrong
 * shape for that. It was copied faithfully, comments and all. If a pacing bug
 * is fixed in one of the two, look at the other.
 *
 * This builds on Windows, macOS and Linux. CI builds and runs it against the
 * boot smoke title on the last two, and compile-checks it against clang-cl on
 * the first (tools/check_ppu_scaffold.py).
 */

/* The lifter's generated header, which declares ppu_context and the function
 * table. It comes first: everything below is written against that struct. */
#include "ppu_recomp.h"

/* The Win32 names -- Sleep, GetTickCount64, CreateThread, InterlockedIncrement,
 * VirtualAlloc, the scalar typedefs -- from one place. On Windows this is a
 * passthrough to <windows.h>; off Windows the toolkit's shim supplies the same
 * names over pthreads and mmap, so the call sites below are written once. */
#include "win32_compat.h"
#include "thread_name.h"   /* ps3_thread_setname */
#include "ps3emu/loadtime_trace.h"   /* #11 load-stage timing (observer) */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
/* timeBeginPeriod: <windows.h> arrives with WIN32_LEAN_AND_MEAN set, which
 * excludes the multimedia timer API, so it is asked for by name -- and after
 * windows.h, since timeapi.h uses UINT. No shim exists off Windows because
 * there is nothing to shim: the 15.6 ms default timer granularity this works
 * around is a Windows problem. */
#include <timeapi.h>
#endif

/* ---------------------------------------------------------------------------
 * What the scaffold gives this file
 * -----------------------------------------------------------------------*/
extern "C" {
uint32_t ppu_load_elf(const char* path);      /* ELF -> guest RAM, returns entry OPD */
void     ppu_recomp_register(void);           /* generated: lifted table -> address map */
void     ppu_hle_init(void);                  /* firmware import NID -> HLE handler */
void     ppu_sysprx_register(void);           /* boot-critical CRT (sys_initialize_tls, ...) */
void     ppu_fs_register(void);               /* cellFs over the real game directory */
void     lv2_init_syscalls(void);             /* the lv2 syscall table */
int      ppu_run(uint32_t entry_opd, uint32_t stack_top);

/* This project's own: load whatever real system PRX modules the title needs
 * into guest RAM and register their exports. stubs.cpp has the empty version
 * a game with no lifted PRX wants. */
void     ps3_load_prx_modules(void);

extern const char* ppu_vfs_root;              /* host dir the PS3 mount points map into */

/* The status the guest handed to sys_process_exit. A title that exits that way
 * never returns through ppu_run, so this is only read on the path where the
 * entry function unwound instead. */
extern int     g_sys_process_exit_called;
extern int32_t g_sys_process_exit_code;

/* Host-provided symbols the runtime and the HLE libraries link against. */
uint8_t* vm_base = nullptr;
extern uint32_t ppu_vm_size;                  /* ppu_loader.cpp: the OOB guard */

/* Guest-callback dispatch. g_ps3_guest_caller is the hook the HLE runtime
 * calls back into recompiled code through -- cellSysutil events and the GCM
 * vblank/flip handlers. ppu_guest_call does the OPD -> dispatch. */
typedef void (*ps3_guest_caller_fn)(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                                    uint64_t, uint64_t, uint64_t, uint64_t);
extern ps3_guest_caller_fn g_ps3_guest_caller;
uint64_t ppu_guest_call(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                        uint64_t, uint64_t, uint64_t, uint64_t);

/* The GCM half of the frame clock. */
void     cellGcmTickVBlank(void);
void     cellGcmTickFlip(void);
int      cellGcm_take_flip_pending_synced(void);
void     cellGcm_rsx_process_fifo(void);      /* drain get -> put */
unsigned cellGcm_flip_request_count(void);
/* A guest thread whose fence wait found the FIFO dry sets this; waiting on it
 * here instead of a blind sleep services fence/label polls at ~0ms latency. */
void*    cellGcm_fifo_kick_event(void);
}

/* ---------------------------------------------------------------------------
 * RSX present backend
 * -----------------------------------------------------------------------*/
/* D3D12 on Windows, Metal on Apple, and the null backend's headless software
 * path anywhere else -- the same selection runtime/host/host_posix.c and the
 * toolkit's boot harness make. All three expose the same three entry points,
 * so the frame clock below is backend-agnostic. */
#if defined(_WIN32)
extern "C" int  rsx_d3d12_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_d3d12_backend_present(void);
extern "C" int  rsx_d3d12_backend_pump_messages(void);
#  define rsx_backend_init    rsx_d3d12_backend_init
#  define rsx_backend_present rsx_d3d12_backend_present
#  define rsx_backend_pump    rsx_d3d12_backend_pump_messages
#  define RSX_BACKEND_NAME    "D3D12"
#elif defined(__APPLE__)
extern "C" int  rsx_metal_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_metal_backend_present(void);
extern "C" int  rsx_metal_backend_pump_messages(void);
#  define rsx_backend_init    rsx_metal_backend_init
#  define rsx_backend_present rsx_metal_backend_present
#  define rsx_backend_pump    rsx_metal_backend_pump_messages
#  define RSX_BACKEND_NAME    "Metal"
#else
extern "C" int  rsx_null_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_null_backend_present(void);
extern "C" int  rsx_null_backend_pump_messages(void);
#  define rsx_backend_init    rsx_null_backend_init
#  define rsx_backend_present rsx_null_backend_present
#  define rsx_backend_pump    rsx_null_backend_pump_messages
#  define RSX_BACKEND_NAME    "null (headless software)"
#endif

/* ---------------------------------------------------------------------------
 * Configuration
 * -----------------------------------------------------------------------*/
/* The flat VM must span every region the PS3 memory map uses, not just the
 * game image: sys_ppu_thread_create puts thread stacks at 0xD0000000, so a
 * smaller arena makes every spawned thread's stack access out of bounds. */
#define VM_SIZE       0x100010000ull   /* the full 32-bit guest space + a 64K guard */
#define STACK_TOP     0x0FF00000u      /* main-thread stack, below the 0x10000000 segment */
#define WINDOW_WIDTH  1280
#define WINDOW_HEIGHT 720

/* ---------------------------------------------------------------------------
 * Frame clock
 * -----------------------------------------------------------------------*/
/* On real hardware the RSX raises a vblank interrupt about 60 times a second
 * and that is what drives the game's frame loop. With no RSX it is synthesized
 * here: a host thread calls cellGcmTickVBlank/TickFlip, which invoke the
 * handlers the guest registered, and drains the GCM FIFO. Without this the
 * title initialises, registers its handlers and then waits forever.
 *
 * The ticks are driven off real elapsed time rather than off how long present()
 * took: a hidden or occluded window makes present block hard, and pacing the
 * ticks behind it paces the whole game behind it. The loop runs at a fast
 * (~1 ms) cadence so the FIFO drain -- the thing every guest fence and label
 * poll waits on -- never waits a 16 ms beat, while vblank/flip completions
 * fire only on the 59.94 Hz beats. */
static volatile LONG g_frames_presented = 0;

/* Frames handed to the backend at a guest FLIP boundary -- one per frame the
 * guest actually finished. The presents made before the guest's first flip, so
 * a fresh window is not left blank through a long boot, carry no guest frame
 * and are deliberately not counted. */
extern "C" unsigned ppu_boot_frames_presented(void)
{
    return (unsigned)g_frames_presented;
}

static void present_guest_frame(void)
{
    rsx_backend_present();
    /* This thread increments and guest threads read, so interlocked rather
     * than a volatile ++, which on arm64 is neither atomic nor a fence. */
    InterlockedIncrement(&g_frames_presented);
}

/* One fast-cadence iteration of the frame loop: pump window messages, drain
 * the FIFO, present a completed flip. Returns 0 when the window died; the
 * caller then stops touching the backend but keeps the vblank beats going,
 * so the guest does not hang behind a closed window. */
static int frame_clock_iteration(int rsx_ok)
{
    if (!rsx_ok) return 1;
    if (rsx_backend_pump() != 0) return 0;
    /* Drain FIRST, at the fast (~1 ms) cadence: titles fence every render
     * pass on an RSX label the drain writes. At a 16 ms drain each fence
     * cost a frame's worth of time (wave: six passes -> ~7 fps; the
     * MotorStorm menu sat at 13-26 fps with a ~33 ms gap between submits
     * because every wait landed on the next 16 ms beat). */
    cellGcm_rsx_process_fifo();
    /* Present once the drain has consumed the flipped frame:
     * take_flip_pending_synced only fires at get==put, so the batch held is
     * exactly the completed frame (the guest blocks in WaitFlip after
     * flipping). */
    if (cellGcm_take_flip_pending_synced()) {
        present_guest_frame();
        return 1;
    }
    /* Boot fallback: before the first flip, present freely so the window is
     * not left blank through a long boot. */
    if (cellGcm_flip_request_count() == 0) rsx_backend_present();
    return 1;
}

static DWORD WINAPI frame_clock(LPVOID)
{
    const char* title = getenv("PS3_TITLE");
    if (!title || !*title) title = "ps3recomp";

    int rsx_ok = (rsx_backend_init(WINDOW_WIDTH, WINDOW_HEIGHT, title) == 0);
    fprintf(stderr, "[rsx] %s backend init %s\n", RSX_BACKEND_NAME,
            rsx_ok ? "OK -- window open" : "FAILED");


#ifdef _WIN32
    /* Vblank beats at the true PS3 rate (59.94 Hz NTSC), accumulated on QPC.
     * GetTickCount64 + `next_tick += 16` quantized the beat to whole ms at
     * 62.5 Hz, which drifts against the 59.94 Hz vsync present and made every
     * flip-synced title skip beats. Accumulating qpf*1001/60000 QPC ticks
     * holds 60000/1001 Hz to within the period truncation (<=1 tick/beat). */
    LARGE_INTEGER qpf_li, qpc_li;
    QueryPerformanceFrequency(&qpf_li);
    QueryPerformanceCounter(&qpc_li);
    const ULONGLONG vblank_period = (ULONGLONG)(qpf_li.QuadPart * 1001ULL / 60000ULL);
    ULONGLONG next_tick = (ULONGLONG)qpc_li.QuadPart;
    /* High-resolution waitable timer for the fast cadence. Sleep() rounds to
     * the 15.6 ms scheduler tick -- and Windows 10+ ignores timeBeginPeriod
     * for unfocused processes -- which capped the FIFO-drain cadence at
     * ~64 Hz and paced guests into the 13-26 fps range. The
     * HIGH_RESOLUTION flag is precise and focus-independent (Win10 1803+).
     * The kick event is in the wait set: a fence-starved guest wakes the
     * drain immediately instead of after the timer slice. */
    HANDLE hrtimer = CreateWaitableTimerExW(NULL, NULL,
        0x00000002 /* CREATE_WAITABLE_TIMER_HIGH_RESOLUTION */, TIMER_ALL_ACCESS);
    HANDLE kick = (HANDLE)cellGcm_fifo_kick_event();
    HANDLE waits[2]; int n_waits = 0;
    if (hrtimer) waits[n_waits++] = hrtimer;
    if (kick)    waits[n_waits++] = kick;

    for (;;) {
        if (hrtimer) {
            LARGE_INTEGER due; due.QuadPart = -10000;   /* 1 ms, 100 ns units */
            SetWaitableTimer(hrtimer, &due, 0, NULL, NULL, FALSE);
            WaitForMultipleObjects(n_waits, waits, FALSE, 2);
        } else if (kick) {
            WaitForSingleObject(kick, 2);
        } else {
            Sleep(2);
        }
        QueryPerformanceCounter(&qpc_li);
        ULONGLONG now = (ULONGLONG)qpc_li.QuadPart;
        while ((long long)(now - next_tick) >= 0) {
            cellGcmTickVBlank();
            /* Flip completion on the vblank beat = 59.94 Hz vsync pacing;
             * with the fast fence drain below, an unpaced guest otherwise
             * runs far past 60 fps. */
            cellGcmTickFlip();
            next_tick += vblank_period;
            /* Fell >1 s behind (debugger pause, machine sleep): resync
             * instead of machine-gunning catch-up vblanks. */
            if ((long long)(now - next_tick) > (long long)(qpf_li.QuadPart)) {
                next_tick = now;
                break;
            }
        }
        if (!frame_clock_iteration(rsx_ok)) rsx_ok = 0;
    }
#else
    /* POSIX: no waitable-timer API; plain sleeps are already fine-grained.
     * 17 ms whole-ms beats ~= 58.8 Hz (the smoke titles do not pace on it). */
    ULONGLONG next_tick = GetTickCount64();
    for (;;) {
        Sleep(2);
        ULONGLONG now = GetTickCount64();
        while ((long long)(now - next_tick) >= 0) {
            cellGcmTickVBlank();
            cellGcmTickFlip();
            next_tick += 17;
            if ((long long)(now - next_tick) > 1000) { next_tick = now; break; }
        }
        if (!frame_clock_iteration(rsx_ok)) rsx_ok = 0;
    }
#endif
    return 0;
}

/* ---------------------------------------------------------------------------
 * VFS root
 * -----------------------------------------------------------------------*/
/* Derive the directory holding PS3_GAME from the EBOOT path
 * <root>/PS3_GAME/USRDIR/EBOOT.elf -> <root>. $PS3_VFS_ROOT overrides. */
static char s_vfs_root[1024];

static void derive_vfs_root(const char* eboot)
{
    const char* env = getenv("PS3_VFS_ROOT");
    if (env && *env) { ppu_vfs_root = env; return; }

    strncpy(s_vfs_root, eboot, sizeof s_vfs_root - 1);
    for (char* p = s_vfs_root; *p; p++) if (*p == '\\') *p = '/';
    /* strip EBOOT.elf, USRDIR and PS3_GAME */
    for (int i = 0; i < 3; i++) { char* s = strrchr(s_vfs_root, '/'); if (s) *s = 0; }
    if (!s_vfs_root[0]) strcpy(s_vfs_root, ".");
    ppu_vfs_root = s_vfs_root;
}

/* ---------------------------------------------------------------------------
 * Guest VM
 * -----------------------------------------------------------------------*/
#ifdef _WIN32
/* Demand-paging for the flat VM: reserve the whole 4 GB guest space, which
 * costs no commit, and commit each 64 KB page on first access. Every 32-bit
 * guest offset is then valid, so a garbage guest pointer reads zero instead of
 * killing the process. Faults outside the arena fall through untouched. */
static LONG WINAPI vm_commit_veh(EXCEPTION_POINTERS* ep)
{
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
        ULONG_PTR fault = ep->ExceptionRecord->ExceptionInformation[1];
        uintptr_t base  = (uintptr_t)vm_base;
        if (vm_base && fault >= base && fault < base + VM_SIZE) {
            void* page = (void*)(fault & ~(uintptr_t)0xFFFF);
            if (VirtualAlloc(page, 0x10000, MEM_COMMIT, PAGE_READWRITE))
                return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

static bool alloc_guest_vm(void)
{
#ifdef _WIN32
    AddVectoredExceptionHandler(1, vm_commit_veh);
    vm_base = (uint8_t*)VirtualAlloc(NULL, VM_SIZE, MEM_RESERVE, PAGE_READWRITE);
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#else
    /* No vectored exception handlers off Windows, so the arena is committed up
     * front and lazily backed by the OS: only pages the title touches cost
     * anything. It stops below the 0xE0000000 mark, so ppu_vm_size arms the
     * loader's bounds check for what is left. */
    vm_base = (uint8_t*)calloc(1, 0xE0000000u);
    ppu_vm_size = 0xE0000000u;
#endif
    return vm_base != nullptr;
}

/* ---------------------------------------------------------------------------
 * Main
 * -----------------------------------------------------------------------*/
static void harness_guest_caller(uint32_t opd, uint64_t a0, uint64_t a1,
                                 uint64_t a2, uint64_t a3, uint64_t a4,
                                 uint64_t a5, uint64_t a6, uint64_t a7)
{
    ppu_guest_call(opd, a0, a1, a2, a3, a4, a5, a6, a7);
}

int main(int argc, char** argv)
{
    if (argc < 2) {
        printf("usage: %s <PPU ELF>\n", argv[0]);
        return 2;
    }

#ifdef _WIN32
#pragma comment(lib, "winmm.lib")
    /* 1 ms timer resolution. The default granularity is about 15.6 ms, which
     * inflates every shorter wait the title makes and throttles the whole
     * thing. POSIX timers are already fine-grained. */
    timeBeginPeriod(1);
    setvbuf(stdout, NULL, _IONBF, 0);   /* unbuffered: do not lose prints on a kill */
#endif

    printf("=== ps3recomp game runner ===\n");

    if (!alloc_guest_vm()) {
        fprintf(stderr, "ERROR: could not allocate the guest address space\n");
        return 1;
    }
    if (loadtime_on()) loadtime_event("boot", "stage=vm_alloc");

    uint32_t entry = ppu_load_elf(argv[1]);
    if (!entry) {
        fprintf(stderr, "ERROR: could not load %s\n", argv[1]);
        return 1;
    }
    if (loadtime_on()) { char d[96];
        snprintf(d, sizeof d, "stage=elf_loaded entry=0x%08X", entry);
        loadtime_event("boot", d); }

    derive_vfs_root(argv[1]);
    printf("[boot] VFS root: %s\n", ppu_vfs_root);
    if (loadtime_on()) loadtime_event("boot", "stage=vfs_root");

    /* MotorStorm imports the bare-name sys_net exports (connect, getsockname,
     * send, ...). Only the PS3_NET_ONLINE model registers them; without it
     * every one falls to the unresolved-NID default, which answers CELL_OK
     * with out-params untouched. Sockets that cannot reach PSN fail with
     * honest host errors, which is the offline behavior the game expects. */
    _putenv("PS3_NET_ONLINE=1");

    ppu_recomp_register();   /* lifted function table -> address map */
    ps3_load_prx_modules();  /* this game's lifted system PRX, if it has any */
    ppu_hle_init();          /* firmware import NID -> HLE handlers */
    ppu_sysprx_register();   /* boot-critical CRT */
    ppu_fs_register();       /* cellFs over the game directory */
    lv2_init_syscalls();     /* the lv2 syscall table */
    if (loadtime_on()) loadtime_event("boot", "stage=services_ready");

    /* Install the guest-callback hook, then start the frame clock. It no-ops
     * until the title registers its vblank and flip handlers during init. */
    g_ps3_guest_caller = harness_guest_caller;
    { HANDLE _fc = CreateThread(NULL, 4u * 1024 * 1024, frame_clock, NULL, 0, NULL);
      ps3_thread_setname((uintptr_t)_fc, "frame_clock"); }

    printf("\n[boot] dispatching entry OPD 0x%08X (stack top 0x%08X)\n\n",
           entry, STACK_TOP);
    if (loadtime_on()) { char d[96];
        snprintf(d, sizeof d, "stage=entry_dispatch opd=0x%08X", entry);
        loadtime_event("boot", d); }

    int rc = ppu_run(entry, STACK_TOP);
    printf("\n[boot] ppu_run returned %d (entry function unwound)\n", rc);
    if (loadtime_on()) { char d[96];
        snprintf(d, sizeof d, "stage=ppu_run_return rc=%d", rc);
        loadtime_event("boot", d); }

    /* A title that called sys_process_exit never reaches this line: that path
     * ends in the host exit(). Getting here means the entry function returned
     * instead, so hand back the status the guest published if it published
     * one. Returning a hardcoded 0 would report success for a run that never
     * got anywhere. */
    return g_sys_process_exit_called ? (int)g_sys_process_exit_code : 0;
}

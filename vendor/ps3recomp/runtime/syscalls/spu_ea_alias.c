/*
 * ps3recomp - LV1 SPU effective-address alias window (firmware dual mapping).
 *
 * LV1 maps every memory-container page for SPU access TWICE: the primary VA
 * the PPU sees, and a second window at +0x05000000 (the "SPU color" alias the
 * SPURS kernel uses for its work-area EAs -- the SPU-side code computes
 * base|0x05000000 directly and never issues a syscall for it). On firmware
 * both VAs resolve to the same physical pages.
 *
 * This runtime's VM is flat, so an unimplemented alias sends every SPU
 * completion PUT into unrelated committed pages: the PPU protocol memory
 * never hears back, the title wedges wherever the race lands, and whatever
 * allocation owns the +0x05000000 pages is silently corrupted (MotorStorm
 * BCES00006 dead boots: 8432 completion PUTs to 0x452443D0 while the ticket
 * header lives at 0x40244380).
 *
 * Fix: registration-based EA normalization on the SPU paths only. When an
 * SPU MFC/atomic EA carries the 0x05000000 window bit, the primary EA is a
 * registered allocation, and the EA as-is is NOT, the address is the same
 * memory under the alias and is normalized down. Anything else -- a real
 * allocation at the aliased address, an unregistered primary -- is left
 * untouched, so behavior only changes exactly where firmware would have
 * resolved both VAs to the same bytes.
 *
 * Self-contained on purpose: sys_memory.c registers its handouts; the SPU
 * DMA/atomic layers query. Unit-testable straight-in
 * (runtime/syscalls/tests/test_spu_ea_alias.c).
 */

#include <stdint.h>

#define SPU_ALIAS_MAX 32

typedef struct spu_alias_range {
    uint32_t addr;
    uint32_t size;
} spu_alias_range;

static spu_alias_range s_alias[SPU_ALIAS_MAX];
static int             s_alias_n;

/* sys_memory.c records each handed-out allocation window here. */
void sysmem_alias_record(uint32_t addr, uint32_t size)
{
    if (s_alias_n < SPU_ALIAS_MAX && size) {
        s_alias[s_alias_n].addr = addr;
        s_alias[s_alias_n].size = size;
        s_alias_n++;
    }
}

static int spu_alias_in_table(uint32_t ea)
{
    for (int i = 0; i < s_alias_n; i++)
        if (ea >= s_alias[i].addr && ea < s_alias[i].addr + s_alias[i].size)
            return 1;
    return 0;
}

/* Normalize an SPU/PPU-side EA through the LV1 dual mapping. Returns the EA
 * the PPU-side protocol memory lives at; identity when the alias does not
 * apply.
 *
 * The window is ARITHMETIC: firmware maps each container page at its primary
 * VA and again at exactly +0x05000000 (guest code computes base+0x05000000;
 * MotorStorm's CreateTask args 0x41ED0000->0x46ED0000 prove ADD, and the
 * original WWS case 0x40244380->0x452443D0 agrees since OR==ADD there).
 * A mask (ea & ~0x05000000) only reproduces this when the primary lacks the
 * window bits itself; for primaries like 0x41EBC100 the OR-form (0x45EBC100)
 * and ADD-form (0x46EBC100) diverge and the mask silently matched neither. */
uint32_t sysmem_spu_alias_fixup(uint32_t ea)
{
    /* MFC storage alias, EA bit 31 (bg_275): the CBE MFC addresses main
     * storage through a second mapping at 0x80000000|ea -- EA[31] is
     * ignored for main-storage targets, and Sony code posts these aliased
     * EAs routinely (MotorStorm's SPURS claims its job queue at
     * 0x80440440 while the queue lives at 0x00440440 -- the low-heap
     * layout right after the EBOOT). RPCS3 needs no explicit rule because
     * vm::_ptr(eal) (SPUThread.cpp do_dma_transfer, line ~2058) resolves
     * through a VM whose mapping already covers the alias; our flat VM
     * must normalize. Raw-SPU problem state (0xE0000000+) keeps its bit31
     * MMIO meaning -- the < 0x90000000 bound leaves it untouched, and the
     * PS3 kernel range 0x90000000+ is never an SPU DMA target. Applied
     * BEFORE the +0x05000000 window so both aliases compose. */
    if ((ea & 0x80000000u) != 0u && ea < 0x90000000u)
        return 0x40000000u | (ea & 0x3FFFFFFFu); /* bg_276: 0x00440440 is
         * EBOOT .text; the posted queue arena lives at 0x4004xxxx+, so the
         * bit31 mapping is into the sys_memory container arena, not low
         * memory. [mfc-alias] probe in spu_channels.c verifies live. */
    /* Registration determines the valid alias extent; larger allocation
     * arenas may place a registered primary above the old 0x50000000 end. */
    if (ea < 0x45000000u) return ea;
    uint32_t prim = ea - 0x05000000u;
    if (spu_alias_in_table(prim) && !spu_alias_in_table(ea)) return prim;
    return ea;
}

/* Allocator collision guard (called from sys_memory.c under the bump lock):
 * a candidate real allocation must not sit on the +0x05000000 alias image of
 * any recorded allocation, and must not place its own alias image on top of
 * one either. On firmware both VAs of one page are the SAME physical memory,
 * so two different allocations whose VAs differ by exactly 0x05000000 cannot
 * exist; the observed 17MB block [0x45F00000,0x47000000) landing on the 56MB
 * block's image was an impossible layout and made every EA in it ambiguous. */
int sysmem_alias_va_conflicts(uint32_t addr, uint32_t size)
{
    for (int i = 0; i < s_alias_n; i++) {
        uint32_t a = s_alias[i].addr, b = a + s_alias[i].size;
        uint32_t ia = a + 0x05000000u, ib = b + 0x05000000u; /* its image */
        if (addr < ib && ia < addr + size) return 1; /* candidate on its image */
        if (addr + 0x05000000u < b && a < addr + 0x05000000u + size) return 1; /* ours on an alloc */
    }
    return 0;
}

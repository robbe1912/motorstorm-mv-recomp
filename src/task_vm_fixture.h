/* Authored empty VM and strict callback adapters, shared by source fixtures. */
#include <stdint.h>
#include <stdlib.h>
uint8_t* vm_base;
uint32_t sysmem_spu_alias_fixup(uint32_t a) { if (a >= 0x50000) abort(); return a; }
volatile int g_spu_coh_armed;
int g_resv_store_active;
uint32_t g_ww_lo, g_ww_hi;
volatile unsigned char vm_read_sync_pages[1u << 20];
void ppu_resv_break_store(uint64_t a) { (void)a; abort(); }
void ps3_ww_report_inline(uint32_t a, uint64_t v, int n) { (void)a; (void)v; (void)n; abort(); }
void vm_read_sync_dispatch(uint32_t a, uint32_t n) { (void)a; (void)n; abort(); }
int spu_coh_is_reserved(uint32_t a) { (void)a; return 0; }
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void spu_coh_notify_write(uint32_t a) { (void)a; }

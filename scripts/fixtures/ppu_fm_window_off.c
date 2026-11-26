/* Link definitions of the fastmem window hooks for checks that build the SPU
 * runtime without runtime/ppu/ppu_loader.cpp (the production definitions).
 * runtime/syscalls/spu_ea_alias.c calls both hooks from sysmem_alias_record.
 * The form is the one of the production build without fastmem. */
#include <stdint.h>

void ppu_fm_window_begin(uint32_t page) { (void)page; }
void ppu_fm_window_end(uint32_t page, int state) { (void)page; (void)state; }

#include "ps3emu/guest_read_sync.h"
#include <stddef.h>
volatile unsigned char vm_read_sync_pages[1u << 20];
static vm_read_sync_handler s_handler;
static void *s_opaque;
void vm_read_sync_set_handler(vm_read_sync_handler handler, void *opaque) {
    if(handler) s_opaque=opaque;
#if defined(_MSC_VER) && !defined(__clang__)
    _InterlockedExchangePointer((void *volatile *)&s_handler,(void *)handler);
#else
    __atomic_store_n(&s_handler,handler,__ATOMIC_RELEASE);
#endif
}
int vm_read_sync_mark_range(uint32_t address, uint64_t bytes) {
    if(!bytes || bytes>UINT64_C(0x100000000)-(uint64_t)address) return -1;
    unsigned first=address>>12,last=(unsigned)(((uint64_t)address+bytes-1)>>12);
    for(unsigned page=first;page<=last;page++) {
#if defined(_MSC_VER) && !defined(__clang__)
        _InterlockedExchange8((volatile char *)&vm_read_sync_pages[page],1);
#else
        __atomic_store_n(&vm_read_sync_pages[page],1,__ATOMIC_RELEASE);
#endif
    }
    return 0;
}
void vm_read_sync_dispatch(uint32_t address, uint32_t bytes) {
#if defined(_MSC_VER) && !defined(__clang__)
    vm_read_sync_handler handler=(vm_read_sync_handler)_InterlockedCompareExchangePointer((void *volatile *)&s_handler,NULL,NULL);
#else
    vm_read_sync_handler handler=__atomic_load_n(&s_handler,__ATOMIC_ACQUIRE);
#endif
    if(handler)handler(address,bytes,s_opaque);
}

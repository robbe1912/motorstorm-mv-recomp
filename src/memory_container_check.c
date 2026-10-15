/* Authored syscall fixture. Uses the production allocator and VM commit path. */
#ifndef TARGET_SOURCE
#define TARGET_SOURCE "../vendor/ps3recomp/runtime/syscalls/sys_memory.c"
#endif
#include TARGET_SOURCE
#include <stdlib.h>

uint8_t* vm_base;
uint32_t ppu_vm_size;
uint32_t ppu_hle_inject_base;
static uint32_t conflict_start, conflict_end;
int sysmem_alias_va_conflicts(uint32_t address, uint32_t size)
{ return address < conflict_end && conflict_start < address + size; }
void sysmem_alias_record(uint32_t address, uint32_t size) { (void)address; (void)size; }
uint32_t sysmem_spu_alias_fixup(uint32_t address) { return address; }
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
#define RC(x) ((int64_t)(int32_t)(x))
static lv2_syscall_table table;
static uint32_t output(uint32_t ea)
{
    const uint8_t* p=vm_base+ea;
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static uint32_t reset(void)
{
    lv2_syscall_table_init(&table); sys_memory_init(&table);
    conflict_start=conflict_end=0;
    ppu_context cpu={0}; cpu.gpr[3]=0x1000; cpu.gpr[4]=0x800000;
    CHECK(sys_memory_container_create(&cpu)==CELL_OK);
    return output(0x1000);
}
static int64_t allocate(uint64_t size, uint32_t cid, uint64_t flags, uint32_t out)
{
    ppu_context cpu={0}; cpu.gpr[3]=size; cpu.gpr[4]=cid;
    cpu.gpr[5]=flags; cpu.gpr[6]=out;
    return table.handlers[SYS_MEMORY_ALLOCATE_FROM_CONTAINER](&cpu);
}
static int64_t release(uint32_t address)
{ ppu_context cpu={0}; cpu.gpr[3]=address; return sys_memory_free(&cpu); }
static int64_t destroy(uint32_t cid)
{ ppu_context cpu={0}; cpu.gpr[3]=cid; return sys_memory_container_destroy(&cpu); }
static void unchanged_error(uint32_t cid,uint64_t size,uint64_t flags,uint32_t out,int64_t expected)
{
    uint32_t bump=g_sys_mem_bump_ptr,total=s_total_allocated,used=g_sys_mem_containers[cid-1].used_size;
    memset(vm_base+0x1004,0xA5,4);
    CHECK(allocate(size,cid,flags,out)==expected);
    CHECK(g_sys_mem_bump_ptr==bump && s_total_allocated==total);
    CHECK(g_sys_mem_containers[cid-1].used_size==used && output(0x1004)==0xA5A5A5A5);
}
int main(void)
{
#ifdef _WIN32
    vm_base=(uint8_t*)VirtualAlloc(NULL,(SIZE_T)VM_TOTAL_SIZE,MEM_RESERVE,PAGE_NOACCESS);
    CHECK(vm_base && VirtualAlloc(vm_base,0x10000,MEM_COMMIT,PAGE_READWRITE));
#else
    void* region=mmap(NULL,(size_t)VM_TOTAL_SIZE,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    CHECK(region!=MAP_FAILED); vm_base=(uint8_t*)region;
    CHECK(mprotect(vm_base,0x10000,PROT_READ|PROT_WRITE)==0);
#endif
    uint32_t cid=reset();
    CHECK(allocate(0x600000,cid,SYS_MEMORY_PAGE_SIZE_1M,0x1004)==CELL_OK);
    uint32_t first=output(0x1004);
    CHECK(g_sys_mem_allocs[0].size==0x600000 && g_sys_mem_allocs[0].container_id==(int32_t)cid);
    CHECK(g_sys_mem_containers[cid-1].used_size==0x600000);
    ppu_context cpu={0};cpu.gpr[3]=0x100000;cpu.gpr[4]=SYS_MEMORY_PAGE_SIZE_1M;cpu.gpr[5]=0x1008;
    CHECK(sys_memory_allocate(&cpu)==CELL_OK);
    CHECK(output(0x1008)>=first+0x600000);
    CHECK(destroy(cid)==RC(CELL_EBUSY));
    CHECK(release(first)==CELL_OK && g_sys_mem_containers[cid-1].used_size==0);
    CHECK(release(first)==RC(CELL_EINVAL));
    CHECK(destroy(cid)==CELL_OK);

    cid=reset();
    CHECK(allocate(0x20000,cid,SYS_MEMORY_PAGE_SIZE_64K,0x1004)==CELL_OK);
    CHECK(g_sys_mem_allocs[0].size==0x20000 && g_sys_mem_allocs[0].page_size==0x10000);
    CHECK(release(output(0x1004))==CELL_OK);
    CHECK(allocate(0x100000,cid,0,0x1004)==CELL_OK && g_sys_mem_allocs[0].page_size==0x100000);
    CHECK(release(output(0x1004))==CELL_OK);
    unchanged_error(cid,0,0,0x1004,RC(CELL_EALIGN));
    unchanged_error(cid,1,SYS_MEMORY_PAGE_SIZE_1M,0x1004,RC(CELL_EALIGN));
    unchanged_error(cid,0x100000,0x600,0x1004,RC(CELL_EINVAL));
    unchanged_error(cid,0x100000,UINT64_C(0x100000400),0x1004,RC(CELL_EINVAL));
    unchanged_error(cid,UINT64_C(0x100000000),0,0x1004,RC(CELL_ENOMEM));
    unchanged_error(cid,0x100000,0,0,RC(CELL_EFAULT));
    unchanged_error(cid,0x900000,0,0x1004,RC(CELL_ENOMEM));
    CHECK(allocate(0x100000,0,0,0x1004)==RC(CELL_ESRCH));
    CHECK(allocate(0x100000,SYS_MEMORY_CONTAINER_MAX+1,0,0x1004)==RC(CELL_ESRCH));
    CHECK(allocate(0x100000,2,0,0x1004)==RC(CELL_ESRCH));

    cid=reset();s_total_allocated=SYS_MEM_USER_TOTAL-0x100000;
    unchanged_error(cid,0x200000,0,0x1004,RC(CELL_ENOMEM));
    cid=reset();for(int i=0;i<SYS_MEMORY_ALLOC_MAX;i++)g_sys_mem_allocs[i].active=1;
    unchanged_error(cid,0x100000,0,0x1004,RC(CELL_ENOMEM));
    cid=reset();g_sys_mem_bump_ptr=SYS_MEM_ALLOC_END;
    unchanged_error(cid,0x100000,0,0x1004,RC(CELL_ENOMEM));
    cid=reset();conflict_start=SYS_MEM_ALLOC_BASE;conflict_end=SYS_MEM_ALLOC_BASE+0x100000;
    CHECK(allocate(0x100000,cid,0,0x1004)==CELL_OK && output(0x1004)==conflict_end);

    cid=reset();uint8_t* saved=vm_base;vm_base=NULL;
    CHECK(allocate(0x100000,cid,0,0x1004)==RC(CELL_EFAULT));
    vm_base=saved;
    CHECK(g_sys_mem_bump_ptr==0 && s_total_allocated==0 && g_sys_mem_containers[cid-1].used_size==0);
    CHECK(!g_sys_mem_allocs[0].active);
#ifdef _WIN32
    CHECK(VirtualFree(vm_base,0,MEM_RELEASE));
#else
    CHECK(munmap(vm_base,(size_t)VM_TOTAL_SIZE)==0);
#endif
    puts("PASS: container allocation ABI, non-overlap, accounting, free, budgets and failure rollback");
    return 0;
}

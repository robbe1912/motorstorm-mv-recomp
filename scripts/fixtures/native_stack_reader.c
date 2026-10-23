#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <dbghelp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Offline only: no process attachment and no execution of mapped input images.
 * DbgHelp's runtime-function/epilogue walker reads only bounded saved memory. */
typedef struct { uint64_t base, size; const wchar_t *path; } input_module;
typedef struct { uint64_t ip, sp, displacement; uint32_t symbol_type; char symbol[256]; } output_frame;
typedef struct { input_module input; HANDLE file, mapping; void *view; RUNTIME_FUNCTION *functions; uint32_t function_count; } mapped_module;
_Static_assert(sizeof(CONTEXT) == 1232, "Windows AMD64 context required");
static mapped_module *modules;
static uint32_t module_count;
static const unsigned char *saved_stack;
static uint64_t saved_base, saved_size, missing_address;
static uint32_t missing_reads;
static HANDLE process;
static char error_text[512];

__declspec(dllexport) const char *stack_error(void) { return error_text; }
__declspec(dllexport) uint32_t stack_frame_size(void) { return sizeof(output_frame); }
__declspec(dllexport) void stack_close(void)
{
    if (process) SymCleanup(process);
    process = NULL;
    for (uint32_t i = 0; i < module_count; ++i) {
        if (modules[i].view) UnmapViewOfFile(modules[i].view);
        if (modules[i].mapping) CloseHandle(modules[i].mapping);
        if (modules[i].file != INVALID_HANDLE_VALUE) CloseHandle(modules[i].file);
    }
    free(modules); modules = NULL; module_count = 0;
}
static DWORD64 CALLBACK module_base(HANDLE ignored, DWORD64 address)
{
    (void)ignored;
    for (uint32_t i = 0; i < module_count; ++i)
        if (address >= modules[i].input.base && address - modules[i].input.base < modules[i].input.size)
            return modules[i].input.base;
    return 0;
}
static PVOID CALLBACK function_table(HANDLE ignored, DWORD64 address)
{
    (void)ignored;
    for (uint32_t i = 0; i < module_count; ++i) {
        mapped_module *m = &modules[i];
        if (address < m->input.base || address - m->input.base >= m->input.size) continue;
        uint32_t rva = (uint32_t)(address - m->input.base), lo = 0, hi = m->function_count;
        while (lo < hi) {
            uint32_t mid = lo + (hi-lo)/2; RUNTIME_FUNCTION *f = &m->functions[mid];
            if (rva < f->BeginAddress) hi = mid;
            else if (rva >= f->EndAddress) lo = mid+1;
            else return f;
        }
    }
    return NULL;
}
static BOOL CALLBACK read_saved(HANDLE ignored, DWORD64 address, PVOID buffer, DWORD count, LPDWORD done)
{
    (void)ignored; *done = 0;
    if (address >= saved_base && address - saved_base <= saved_size && count <= saved_size - (address - saved_base)) {
        memcpy(buffer, saved_stack + (address - saved_base), count); *done = count; return TRUE;
    }
    for (uint32_t i = 0; i < module_count; ++i) {
        mapped_module *m = &modules[i];
        if (address >= m->input.base && address - m->input.base <= m->input.size && count <= m->input.size - (address - m->input.base)) {
            SIZE_T actual = 0;
            /* Reads our non-executable mapping, never a target process. This
             * reports inaccessible PE gaps instead of dereferencing them. */
            if (ReadProcessMemory(GetCurrentProcess(), (char *)m->view + (address - m->input.base), buffer, count, &actual) && actual == count) {
                *done = count; return TRUE;
            }
            break;
        }
    }
    ++missing_reads; missing_address = address; return FALSE;
}
__declspec(dllexport) int stack_open(const input_module *input, uint32_t count, const wchar_t *symbols)
{
    stack_close(); error_text[0] = 0;
    if (!count || count > 4096) return -1;
    modules = calloc(count, sizeof(*modules)); if (!modules) return -1;
    module_count = count;
    for (uint32_t i = 0; i < count; ++i) modules[i].file = INVALID_HANDLE_VALUE;
    SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME | SYMOPT_EXACT_SYMBOLS |
                  SYMOPT_FAIL_CRITICAL_ERRORS | SYMOPT_NO_PROMPTS |
                  SYMOPT_IGNORE_NT_SYMPATH | SYMOPT_DISABLE_SYMSRV_AUTODETECT);
    process = GetCurrentProcess();
    if (!SymInitializeW(process, symbols, FALSE)) { snprintf(error_text, sizeof(error_text), "SymInitialize error %lu", GetLastError()); return -1; }
    for (uint32_t i = 0; i < count; ++i) {
        mapped_module *m = &modules[i]; m->input = input[i];
        if (!input[i].path || !input[i].base || !input[i].size || input[i].size > UINT32_MAX) return -1;
        m->file = CreateFileW(input[i].path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (m->file == INVALID_HANDLE_VALUE) goto fail;
        m->mapping = CreateFileMappingW(m->file, NULL, PAGE_READONLY | SEC_IMAGE_NO_EXECUTE, 0, 0, NULL);
        if (!m->mapping) goto fail;
        m->view = MapViewOfFile(m->mapping, FILE_MAP_READ, 0, 0, 0);
        if (!m->view) goto fail;
        IMAGE_DOS_HEADER *dos = m->view;
        if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew < 0 || dos->e_lfanew > 1048576) goto fail;
        IMAGE_NT_HEADERS64 *nt = (void *)((char *)m->view + dos->e_lfanew);
        if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64 || nt->OptionalHeader.SizeOfImage != input[i].size) goto fail;
        DWORD exception_bytes = 0;
        m->functions = ImageDirectoryEntryToData(m->view, TRUE, IMAGE_DIRECTORY_ENTRY_EXCEPTION, &exception_bytes);
        if (exception_bytes % sizeof(RUNTIME_FUNCTION) ||
            (exception_bytes && (!m->functions || (uintptr_t)m->functions < (uintptr_t)m->view ||
             (uintptr_t)m->functions - (uintptr_t)m->view > m->input.size ||
             exception_bytes > m->input.size - ((uintptr_t)m->functions - (uintptr_t)m->view)))) goto fail;
        /* GNU-produced modules can contain sorted empty exception ranges.
         * They own no PC and are not malformed nonempty ranges. */
        m->function_count = exception_bytes / sizeof(RUNTIME_FUNCTION);
        for (uint32_t f = 0; f < m->function_count; ++f) {
            RUNTIME_FUNCTION *entry = &m->functions[f];
            if (entry->BeginAddress > entry->EndAddress || entry->EndAddress > m->input.size ||
                (entry->UnwindData & ~3u) >= m->input.size ||
                (f && entry->BeginAddress < m->functions[f-1].EndAddress)) goto fail;
        }
        SetLastError(0);
        if (!SymLoadModuleExW(process, m->file, input[i].path, NULL, input[i].base, (DWORD)input[i].size, NULL, 0)) goto fail;
        continue;
    fail:
        snprintf(error_text, sizeof(error_text), "module %u load/extent error %lu", i, GetLastError());
        return -1;
    }
    return 0;
}
typedef struct { uint32_t symbol_type, age; unsigned char guid[16]; char pdb[MAX_PATH]; } module_identity;
__declspec(dllexport) int stack_module_identity(uint64_t base, module_identity *out, uint32_t size)
{
    if (!process || size != sizeof(*out)) return -1;
    IMAGEHLP_MODULE64 info; memset(&info, 0, sizeof(info)); info.SizeOfStruct = sizeof(info);
    if (!SymGetModuleInfo64(process, base, &info)) return -1;
    memset(out, 0, sizeof(*out)); out->symbol_type = info.SymType; out->age = info.PdbAge;
    memcpy(out->guid, &info.PdbSig70, 16); snprintf(out->pdb, sizeof(out->pdb), "%s", info.LoadedPdbName);
    return 0;
}
__declspec(dllexport) int stack_walk(const void *context, uint32_t context_size, uint64_t base,
    const void *stack, uint32_t size, output_frame *output, uint32_t capacity,
    uint32_t *reason, uint32_t *misses, uint64_t *missing)
{
    if (!process || context_size != sizeof(CONTEXT) || !context || !stack || !size || !capacity) return -1;
    error_text[0] = 0;
    CONTEXT ctx; memcpy(&ctx, context, sizeof(ctx));
    if ((ctx.ContextFlags & (CONTEXT_CONTROL | CONTEXT_INTEGER)) != (CONTEXT_CONTROL | CONTEXT_INTEGER) || ctx.Rsp != base || !module_base(process, ctx.Rip)) return -1;
    saved_stack = stack; saved_base = base; saved_size = size; missing_reads = 0; missing_address = 0;
    STACKFRAME64 frame; memset(&frame, 0, sizeof(frame));
    frame.AddrPC.Offset = ctx.Rip; frame.AddrStack.Offset = ctx.Rsp; frame.AddrFrame.Offset = ctx.Rbp;
    frame.AddrPC.Mode = frame.AddrStack.Mode = frame.AddrFrame.Mode = AddrModeFlat;
    uint32_t count = 0; *reason = 2;
    for (uint32_t attempt = 0; attempt < capacity + 2; ++attempt) {
        uint64_t ip = frame.AddrPC.Offset, sp = frame.AddrStack.Offset;
        if (!ip) { *reason = 0; break; }
        int duplicate = count && output[count-1].ip == ip && output[count-1].sp == sp;
        if (duplicate && attempt > 1) { *reason = 4; break; }
        if (!duplicate) {
            if (count == capacity) { *reason = 3; break; }
            for (uint32_t i = 0; i < count; ++i) if (output[i].ip == ip && output[i].sp == sp) { *reason = 4; goto finished; }
            if (count && sp < output[count-1].sp) { *reason = 4; break; }
            output_frame *f = &output[count++]; memset(f, 0, sizeof(*f)); f->ip = ip; f->sp = sp;
            char storage[sizeof(SYMBOL_INFO) + 1024]; SYMBOL_INFO *info = (void *)storage;
            memset(storage, 0, sizeof(storage)); info->SizeOfStruct = sizeof(*info); info->MaxNameLen = 1024;
            DWORD64 displacement = 0;
            if (SymFromAddr(process, ip, &displacement, info)) { snprintf(f->symbol, sizeof(f->symbol), "%s", info->Name); f->displacement = displacement; }
            IMAGEHLP_MODULE64 module; memset(&module, 0, sizeof(module)); module.SizeOfStruct = sizeof(module);
            if (SymGetModuleInfo64(process, ip, &module)) f->symbol_type = module.SymType;
        }
        if (!module_base(process, ip)) { *reason = 5; break; }
        if (!StackWalk64(IMAGE_FILE_MACHINE_AMD64, process, GetCurrentThread(), &frame, &ctx,
                         read_saved, function_table, module_base, NULL)) {
            snprintf(error_text, sizeof(error_text), "StackWalk stopped; last Win32 error %lu, table %p, ip %llx sp %llx flags %lx", GetLastError(), function_table(process, ip), (unsigned long long)ip, (unsigned long long)sp, ctx.ContextFlags);
            *reason = missing_reads ? 1 : 2; break;
        }
    }
finished:
    *misses = missing_reads; *missing = missing_address;
    saved_stack = NULL; saved_size = 0;
    return (int)count;
}

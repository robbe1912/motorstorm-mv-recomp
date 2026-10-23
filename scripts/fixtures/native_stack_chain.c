#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char output_dir[MAX_PATH];
static void write_file(const char *name, const void *data, size_t size)
{
    char path[2*MAX_PATH]; snprintf(path, sizeof(path), "%s/%s", output_dir, name);
    FILE *f = NULL; if (fopen_s(&f, path, "wb") || !f || fwrite(data, 1, size, f) != size || fclose(f)) abort();
}
__declspec(noinline) int profile_leaf(int value)
{
    ULONG_PTR low, high; GetCurrentThreadStackLimits(&low, &high);
    unsigned char *stack = malloc(65536); if (!stack) abort();
    CONTEXT context; RtlCaptureContext(&context);
    size_t count = high - context.Rsp; if (count > 65536) count = 65536;
    memcpy(stack, (void *)(uintptr_t)context.Rsp, count);
    write_file("context.bin", &context, sizeof(context)); write_file("stack.bin", stack, count);
    unsigned char *image = (void *)GetModuleHandleW(NULL);
    IMAGE_DOS_HEADER *dos = (void *)image; IMAGE_NT_HEADERS64 *nt = (void *)(image + dos->e_lfanew);
    char meta[256]; int n = snprintf(meta, sizeof(meta), "%llu %llu %llu %llu %llu\n",
        (unsigned long long)(uintptr_t)image, (unsigned long long)nt->OptionalHeader.SizeOfImage,
        (unsigned long long)context.Rsp, (unsigned long long)count, (unsigned long long)context.Rip);
    write_file("meta.txt", meta, n); free(stack); return value + 1;
}
__declspec(noinline) int profile_middle(int value) { int r = profile_leaf(value+1); return r + value; }
__declspec(noinline) int profile_top(int value) { int r = profile_middle(value+1); return r + value; }
int main(int argc, char **argv)
{
    if (argc != 2 || strlen(argv[1]) >= sizeof(output_dir)) return 2;
    memcpy(output_dir, argv[1], strlen(argv[1])+1);
    volatile int value = argc; return profile_top(value) > 0 ? 0 : 3;
}

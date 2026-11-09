#include "ppu_recomp.h"
#include "ps3emu/ppu_function_registry.h"
#include "motorstorm/deformation_depth_observer.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>

namespace {
constexpr std::uint32_t kGetDepth = 0x0029c684u;
constexpr std::uint32_t kPixelBufferLock = 0x00799db4u;
ps3emu_ppu_function entries[2]{};
unsigned registrations{};
unsigned depth_calls{};
unsigned lock_calls{};
unsigned byte_reads{};
unsigned metadata_reads{};
bool call_lock{true};

void original_lock(ppu_context* ctx) {
    ++lock_calls;
    ctx->gpr[3] = 0xfedcba98u;
}

void original_depth(ppu_context* ctx) {
    ++depth_calls;
    if (call_lock) {
        ctx->gpr[3] = 0xaaaau;
        ctx->gpr[4] = 0xbbbbu;
        ctx->gpr[5] = 0xccccu;
        entries[1](ctx);
    }
    ctx->gpr[3] = 0x12345678u;
    ctx->fpr[1] = 3.5;
    ctx->gpr[8] = call_lock;
}

int index_for(std::uint32_t address) {
    if (address == kGetDepth) return 0;
    if (address == kPixelBufferLock) return 1;
    return -1;
}

bool check(bool condition, const char* label) {
    if (condition) return true;
    std::fprintf(stderr, "fixture check failed: %s\n", label);
    return false;
}
} // namespace

// Called by the authored generated entry, including its renamed fallback.
void fixture_depth_body(ppu_context* ctx) { original_depth(ctx); }

std::uint8_t fixture_original_read8(std::uint64_t address) {
    ++byte_reads;
    if (!check(address >= 0x7000 && address < 0x7005, "original byte address")) std::abort();
    return static_cast<std::uint8_t>(20 + address - 0x7000);
}

std::uint32_t vm_read32(std::uint64_t address) {
    ++metadata_reads;
    if (address == 0xaaaa + 0x54) return 0x25;
    if (address == 0xaaaa + 0x60) return 256;
    if (address == 0xaaaa + 0x64) return 128;
    if (address == 0xaaaa + 0x8c) return 0x5000;
    if (address == 0xbbbb) return 0x7000;
    if (address == 0xbbbb + 4) return 0x3e800000;
    if (address == 0xbbbb + 8) return 0x3f400000;
    if (address >= 0x5000 && address < 0x501c && (address & 3) == 0) {
        const std::uint32_t resource[] = {1, 0, 0x7000, 0x8000, 0x7000, 0x2000, 0x6000};
        return resource[(address - 0x5000) / 4];
    }
    if (address >= 0x6000 && address < 0x601c && (address & 3) == 0) {
        const std::uint32_t parent[] = {2, 0, 0x7000, 0x8000, 0x7000, 0x2000, 0};
        return parent[(address - 0x6000) / 4];
    }
    std::fprintf(stderr, "Unexpected metadata address %llx\n", static_cast<unsigned long long>(address));
    std::abort();
}

extern "C" void ppu_register_function(std::uint64_t address, ps3emu_ppu_function function) {
    const int index = index_for(static_cast<std::uint32_t>(address));
    if (index >= 0) {
        entries[index] = function;
        ++registrations;
    }
}

extern "C" int ppu_get_registered_function(std::uint32_t address, ps3emu_ppu_function* output) {
    const int index = index_for(address);
    if (!output || index < 0 || !entries[index]) return 0;
    *output = entries[index];
    return 1;
}

int main() {
    /* Disabled mode must leave dispatch untouched. */
    deformation_depth_observer_install();
    if (!check(registrations == 0, "disabled install")) return 1;

    entries[0] = func_0029C684;
    entries[1] = original_lock;
    ppu_context disabled{};
    func_0029C684(&disabled);
    if (!check(depth_calls == 1 && lock_calls == 1 && disabled.gpr[3] == 0x12345678u &&
               disabled.fpr[1] == 3.5, "disabled direct fallback")) return 1;
    if (!check(metadata_reads == 0 && byte_reads == 5, "disabled memory reads")) return 1;
    depth_calls = lock_calls = 0;
    entries[1] = nullptr;

#if defined(_WIN32)
    _putenv_s("MS_DEPTH_OBSERVER", "1");
#else
    setenv("MS_DEPTH_OBSERVER", "1", 1);
#endif
    deformation_depth_observer_install();
    if (!check(registrations == 0, "missing entries rejected")) return 1;

    entries[0] = original_depth;
    entries[1] = original_lock;
    deformation_depth_observer_install();
    if (!check(registrations == 0, "unbound depth install")) return 1;
    entries[0] = func_0029C684;
    deformation_depth_observer_install();
    if (!check(registrations == 1, "Lock wrapper installed") ||
        !check(entries[0] == func_0029C684 && entries[1] != original_lock, "bound depth and shadow Lock")) return 1;
    deformation_depth_observer_install();
    if (!check(registrations == 1, "duplicate installation rejected")) return 1;

    // Startup calls without Lock must not exhaust later nested-Lock evidence.
    for (unsigned phase = 0; phase != 2; ++phase) {
        call_lock = phase == 1;
        for (unsigned call = 0; call != 65; ++call) {
            ppu_context context{};
            context.gpr[3] = 0x111u;
            context.gpr[4] = 0x222u;
            context.gpr[5] = 0x333u;
            context.gpr[6] = 0x444u;
            context.fpr[1] = 1.0;
            context.fpr[2] = 2.0;
            context.fpr[3] = 3.0;
            context.fpr[4] = 4.0;
            if (call % 2 == 0) func_0029C684(&context);
            else entries[0](&context);
            if (!check(context.gpr[3] == 0x12345678u && context.fpr[1] == 3.5, "original output preserved")) return 1;
            if (!check(context.gpr[9] == (call_lock ? 110u : 0u), "exact original byte results")) return 1;
        }
    }
    if (!check(depth_calls == 130 && lock_calls == 65, "exact original fallback")) return 1;
    if (!check(byte_reads == 330, "no additional or skipped original byte reads")) return 1;
    std::printf("metadata reads=%u\n", metadata_reads);
    std::puts("PASS actual depth observer fallback and nested Lock capture");
    return 0;
}

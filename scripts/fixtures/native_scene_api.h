#pragma once
#include <cstdint>
struct ppu_context { std::uint64_t gpr[32]; };
extern std::uint8_t* vm_base;
std::uint8_t vm_read8(std::uint64_t);
std::uint32_t vm_read32(std::uint64_t);

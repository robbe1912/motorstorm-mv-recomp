#pragma once
#include <cstdint>
// Authored ABI seam; contains no original context or program payload.
struct ppu_context { std::uint64_t gpr[32], ctr; std::uint32_t cr; };
std::uint32_t vm_read32(std::uint64_t);
std::uint16_t vm_read16(std::uint64_t);
void native_job_wait_fixture_cooperate();

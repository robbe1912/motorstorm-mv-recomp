#include "pcm_cubic.h"
#include "native_cpu.h"

#include <algorithm>
#include <bit>
#include <cstring>
#include <fstream>
#include <immintrin.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace motorstorm::game;
int main(int argc, char** argv) {
    try {
        if (argc != 4 || !supports_native_world_transforms()) return 77;
        std::ifstream in(argv[1], std::ios::binary);
        std::uint32_t sizes[3]; in.read(reinterpret_cast<char*>(sizes), sizeof sizes);
        PcmCubicState state; in.read(reinterpret_cast<char*>(&state), sizeof state);
        std::vector<std::int16_t> pcm(sizes[0]);
        in.read(reinterpret_cast<char*>(pcm.data()), pcm.size() * sizeof(pcm[0]));
        if (!in || sizes[0] > 16384 || sizes[1] > 4096) return 2;
        const auto original_pcm = pcm;
        const auto original_state = state;
        std::vector<float> output(sizes[1], std::bit_cast<float>(0xcdcdcdcdu));
        auto target = std::span(output);
        if (sizes[2] & 2) target = std::span(state.positions);
        if (sizes[2] & 4) target = std::span(reinterpret_cast<float*>(pcm.data()), 16);
        const auto caller_csr = (_mm_getcsr() & ~0xe07fu) | 0x1f80u |
                                static_cast<unsigned>(std::stoul(argv[3], nullptr, 0));
        const auto saved_csr = _mm_getcsr(); _mm_setcsr(caller_csr);
        bool rejected = false;
        try { resample_pcm16_cubic(pcm, state, target); }
        catch (const std::invalid_argument&) { rejected = true; }
        if (_mm_getcsr() != caller_csr) throw std::runtime_error("Caller MXCSR changed");
        _mm_setcsr(saved_csr);
        if (pcm != original_pcm) throw std::runtime_error("Source PCM changed");
        if (rejected && (std::memcmp(&state, &original_state, sizeof state) ||
            std::any_of(output.begin(), output.end(), [](float f) {
                return std::bit_cast<std::uint32_t>(f) != 0xcdcdcdcdu;
            }))) throw std::runtime_error("Partial write on rejected operation");
        std::ofstream out(argv[2], std::ios::binary);
        std::uint32_t status = rejected;
        out.write(reinterpret_cast<const char*>(&status), sizeof status);
        out.write(reinterpret_cast<const char*>(&state), sizeof state);
        out.write(reinterpret_cast<const char*>(output.data()), output.size() * sizeof(output[0]));
        return out ? 0 : 3;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}

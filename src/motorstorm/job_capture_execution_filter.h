#pragma once
#include <array>
#include <charconv>
#include <cstdint>
#include <string_view>

/* Configure before installing producers and retain unchanged through their
 * lifetime. Matching uses raw source/target PC values. An unavailable zero PC
 * can match a selected zero, so event validity flags remain interpretation data. */
struct job_capture_execution_filter {
    static constexpr unsigned maximum_pcs = 32;
    std::array<uint32_t, maximum_pcs> pcs{};
    unsigned count = 0;

    bool parse(std::string_view specification) {
        job_capture_execution_filter parsed;
        while (!specification.empty()) {
            if (parsed.count == maximum_pcs) return false;
            const auto separator = specification.find(',');
            auto token = specification.substr(0, separator);
            int base = 10;
            if (token.size() >= 2 && token[0] == '0' && (token[1] == 'x' || token[1] == 'X')) {
                token.remove_prefix(2);
                base = 16;
            }
            if (token.empty()) return false;
            uint32_t pc = 0;
            const auto result = std::from_chars(token.data(), token.data() + token.size(), pc, base);
            if (result.ec != std::errc{} || result.ptr != token.data() + token.size() ||
                pc > 0x3fffcu || (pc & 3u)) return false;
            parsed.pcs[parsed.count++] = pc;
            if (separator == std::string_view::npos) {
                *this = parsed;
                return true;
            }
            specification.remove_prefix(separator + 1);
        }
        return false;
    }

    bool accepts(uint32_t source_pc, uint32_t target_pc) const {
        if (!count) return true;
        for (unsigned i = 0; i < count; ++i) {
            if (pcs[i] == source_pc || pcs[i] == target_pc) return true;
        }
        return false;
    }
};

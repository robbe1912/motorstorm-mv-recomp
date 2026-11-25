#include "job_capture_execution_filter.h"
#include <cassert>
#include <cstdio>
#include <string>

int main() {
    job_capture_execution_filter filter;
    assert(filter.accepts(4, 8));
    assert(filter.parse("0x0,0x30b0,12672"));
    assert(filter.count == 3 && filter.pcs[2] == 0x3180);
    assert(filter.accepts(0x30b0, 4));
    assert(filter.accepts(4, 0x3180));
    assert(filter.accepts(4, 0));
    assert(!filter.accepts(4, 8));
    const auto previous = filter;
    for (const auto* invalid : {"", ",", "1", "-4", "+4", "0x", "0x1", "0x40000",
                               "0xffffffff", "0x100000000", "0x4,", "0x4,,0x8", "junk",
                               "0x4junk", " 0x4", "0x4 ,0x8"}) {
        assert(!filter.parse(invalid));
        assert(filter.count == previous.count && filter.pcs == previous.pcs);
    }
    std::string maximum;
    for (unsigned i = 0; i < filter.maximum_pcs; ++i) {
        if (i) maximum += ',';
        maximum += "0x3fffc";
    }
    assert(filter.parse(maximum) && filter.count == filter.maximum_pcs);
    assert(filter.accepts(4, 0x3fffc) && !filter.accepts(4, 8));
    assert(!filter.parse(maximum + ",0x4"));
    assert(filter.count == filter.maximum_pcs && filter.pcs[0] == 0x3fffc);
    assert(filter.parse("0X4") && filter.count == 1 && filter.accepts(4, 8));
    puts("PASS raw source/target PC selection, full default, strict bounds and transactional parsing");
}

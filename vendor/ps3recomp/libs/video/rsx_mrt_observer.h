/* Read-only FIFO observations; not decoded render state or a rendering policy.
 * NV4097 register addresses are byte offsets. Unseen values remain unknown. */
#ifndef PS3RECOMP_RSX_MRT_OBSERVER_H
#define PS3RECOMP_RSX_MRT_OBSERVER_H
#include <stdint.h>
typedef struct RsxMrtWord {
    uint32_t value, get;
    int result;
} RsxMrtWord;
typedef struct RsxMrtObservation {
    uint32_t seen;
    RsxMrtWord word[4]; /* blend, blend MRT, color mask, color mask MRT */
} RsxMrtObservation;
typedef struct RsxMrtObserver {
    RsxMrtObservation subchannel[8];
} RsxMrtObserver;
static int rsx_mrt_observe(RsxMrtObserver* out, uint32_t subchannel,
    uint32_t method, uint32_t value, int result, uint32_t get)
{
    unsigned index;
    if (!out || subchannel >= 8) return 0;
    switch (method) {
    case 0x0310: index = 0; break;
    case 0x036c: index = 1; break;
    case 0x0324: index = 2; break;
    case 0x0370: index = 3; break;
    default: return 0;
    }
    RsxMrtObservation* observation = &out->subchannel[subchannel];
    observation->word[index].value = value;
    observation->word[index].get = get;
    observation->word[index].result = result;
    observation->seen |= 1u << index;
    return 1;
}
#endif

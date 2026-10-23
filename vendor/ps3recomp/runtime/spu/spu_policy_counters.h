#ifndef SPU_POLICY_COUNTERS_H
#define SPU_POLICY_COUNTERS_H

#include "spu_context.h"

#ifdef __cplusplus
extern "C" {
#endif

/* State owned by one host policy runner, including kernel-exit classification.
 * A coordinator must collect worker productivity after joining; reading its own
 * TLS cannot describe work performed by another lane. */
extern SPU_THREAD_LOCAL volatile unsigned g_spurs_pm_polls;
extern SPU_THREAD_LOCAL volatile unsigned g_spurs_pm_exited;
extern SPU_THREAD_LOCAL volatile unsigned g_wws_batch_gets;

#ifdef __cplusplus
}
#endif
#endif

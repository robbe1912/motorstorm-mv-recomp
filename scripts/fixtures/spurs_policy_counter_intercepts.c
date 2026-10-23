/* Compile the unchanged production intercepts and expose their static
 * interpreter entry solely to the authored concurrency fixture. */
#include "spu_channels.c"
void policy_counter_interpreted_kernel(spu_context* ctx)
{
    spu_pm_interp_trampoline(ctx);
}

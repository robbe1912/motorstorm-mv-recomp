#ifndef PS3RECOMP_RSX_FIFO_BOUNDARY_H
#define PS3RECOMP_RSX_FIFO_BOUNDARY_H
#ifdef __cplusplus
extern "C" {
#endif

typedef int (*CellGcmFifoBoundaryHandler)(void *opaque);

/* Renderer-owner operation, outside an existing FIFO drain. Performs one normal
 * bounded drain, then invokes the handler only if GET has reached the published
 * PUT observed after that drain. The FIFO lock remains held through the handler.
 * Returns 0 without invoking it if uninitialized, incomplete, or handler is null;
 * otherwise forwards the handler result. It does not take a pending flip or
 * manufacture completion.
 *
 * This is not a GPU fence: consumed words may leave an open primitive or CPU
 * draw records. The handler must preflight them, submit/retire supported backend
 * work and establish resource visibility. It must return normally and must not
 * reenter the FIFO. Producers
 * may publish later work; it cannot be consumed by another walker until return.
 */
int cellGcm_with_fifo_boundary(CellGcmFifoBoundaryHandler handler, void *opaque);

#ifdef __cplusplus
}
#endif
#endif

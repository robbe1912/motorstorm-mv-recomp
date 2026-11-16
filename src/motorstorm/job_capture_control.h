#pragma once

/* Call once before any observation producers start. When MS_JOB_CAPTURE_DIR is
 * absent this is a no-op. Otherwise install a process-lifetime owner and a
 * controller thread; report setup failure rather than running unobserved. */
int job_capture_control_start();

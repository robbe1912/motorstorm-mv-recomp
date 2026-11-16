#pragma once
#include "job_capture.h"
#include <atomic>

/* Install the returned configuration before producers start. The window and
 * original callbacks/user must outlive the capture and its producers. Opening
 * is one-way: a callback racing the transition may fall on either side, and
 * the transition itself is not a guest-event timestamp or a quiescence fence.
 * Check available() before installation. Existing exclusion counts combine
 * closed-window and downstream-filter exclusions; neither identifies a cause. */
struct job_capture_window {
    enum open_result { rejected, opened, opened_bad_clock };
    explicit job_capture_window(const job_capture_config& source) : original(source) {}
    job_capture_window(const job_capture_window&) = delete;
    job_capture_window& operator=(const job_capture_window&) = delete;

    bool available() const { return enabled.is_lock_free(); }
    /* One controller calls open once. The samples bound the host transition,
     * not individual racing callbacks or any guest operation. A zero or
     * backwards sample makes the returned bounds invalid. */
    open_result open(uint64_t* before, uint64_t* after) {
        if (!before || !after || !original.clock || enabled.load(std::memory_order_relaxed)) return rejected;
        *before = original.clock(original.user);
        enabled.store(true, std::memory_order_release);
        *after = original.clock(original.user);
        return *before != 0 && *after >= *before ? opened : opened_bad_clock;
    }
    job_capture_config config() {
        auto c = original;
        c.user = this;
        c.clock = original.clock ? clock : nullptr;
        c.thread_id = original.thread_id ? thread_id : nullptr;
        c.accept_atomic = atomic_filter;
        c.accept_execution = execution_filter;
        c.accept_scheduler = scheduler_filter;
        c.accept_queue_call = queue_call_filter;
        return c;
    }
private:
    const job_capture_config original;
    std::atomic<bool> enabled{false};
    static uint64_t clock(void* p) {
        auto& w = *static_cast<job_capture_window*>(p);
        return w.original.clock(w.original.user);
    }
    static uint64_t thread_id(void* p) {
        auto& w = *static_cast<job_capture_window*>(p);
        return w.original.thread_id(w.original.user);
    }
    static int atomic_filter(void* p, uint32_t source, uintptr_t context, uint64_t address, uint32_t size) {
        auto& w = *static_cast<job_capture_window*>(p);
        return w.enabled.load(std::memory_order_acquire) && (!w.original.accept_atomic ||
            w.original.accept_atomic(w.original.user, source, context, address, size));
    }
    static int execution_filter(void* p, uint32_t kind, uintptr_t context, uint32_t pc, uint32_t target) {
        auto& w = *static_cast<job_capture_window*>(p);
        return w.enabled.load(std::memory_order_acquire) && (!w.original.accept_execution ||
            w.original.accept_execution(w.original.user, kind, context, pc, target));
    }
    static int scheduler_filter(void* p, const ps3_spurs_scheduler_event* event) {
        auto& w = *static_cast<job_capture_window*>(p);
        return w.enabled.load(std::memory_order_acquire) && (!w.original.accept_scheduler ||
            w.original.accept_scheduler(w.original.user, event));
    }
    static int queue_call_filter(void* p, const job_queue_event* event) {
        auto& w = *static_cast<job_capture_window*>(p);
        return w.enabled.load(std::memory_order_acquire) && (!w.original.accept_queue_call ||
            w.original.accept_queue_call(w.original.user, event));
    }
};

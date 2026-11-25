#include "ppu_recomp.h"
#include "job_queue_lifecycle.h"
#include <atomic>
#include <cstdint>

void game_original_queue_reset(ppu_context*);
void game_original_queue_reset_multi(ppu_context*);
void game_original_queue_init(ppu_context*);
void game_original_add_job(ppu_context*);

namespace {
std::atomic<const job_queue_observer*> observer{nullptr};
std::atomic<std::uint64_t> next_id{1};

std::uint64_t reserve_id() noexcept {
    auto current = next_id.load(std::memory_order_relaxed);
    while (current && !next_id.compare_exchange_weak(
            current, current + 1, std::memory_order_relaxed)) {}
    return current; // zero means exhausted; never reuse an ID
}
void invoke(ppu_context* ctx, job_queue_operation operation, void (*original)(ppu_context*)) {
    const auto* target = observer.load(std::memory_order_acquire);
    if (!target) {
        original(ctx);
        return;
    }
    job_queue_event event{reserve_id(), reinterpret_cast<std::uintptr_t>(ctx),
        static_cast<std::uint32_t>(ctx->gpr[3]), static_cast<std::uint32_t>(ctx->gpr[4]),
        operation, job_queue_phase::enter, operation == job_queue_operation::add_job ? ctx->gpr[5] : 0, ctx->lr};
    target->event(target->user, event);
    original(ctx);
    event.phase = job_queue_phase::returned;
    target->event(target->user, event);
}
}
bool job_queue_observer_install(const job_queue_observer* value) noexcept {
    if (!observer.is_lock_free() || !next_id.is_lock_free() || (value && !value->event))
        return false;
    if (!value) {
        observer.store(nullptr, std::memory_order_release);
        return true;
    }
    const job_queue_observer* empty = nullptr;
    return observer.compare_exchange_strong(empty, value, std::memory_order_release,
                                            std::memory_order_relaxed);
}
void motorstorm_observe_queue_reset(ppu_context* ctx) {
    invoke(ctx, job_queue_operation::reset, game_original_queue_reset);
}
void motorstorm_observe_queue_reset_multi(ppu_context* ctx) {
    invoke(ctx, job_queue_operation::reset, game_original_queue_reset_multi);
}
void motorstorm_observe_queue_init(ppu_context* ctx) {
    invoke(ctx, job_queue_operation::init, game_original_queue_init);
}
void motorstorm_observe_add_job(ppu_context* ctx) {
    invoke(ctx, job_queue_operation::add_job, game_original_add_job);
}

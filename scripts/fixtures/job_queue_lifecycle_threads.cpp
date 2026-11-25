#include "ppu_recomp.h"
#include "job_queue_lifecycle.h"
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <limits>
#include <thread>
#include <unordered_map>
#include <unordered_set>

void motorstorm_observe_queue_reset(ppu_context*);
void motorstorm_observe_queue_reset_multi(ppu_context*);
void motorstorm_observe_queue_init(ppu_context*);
void motorstorm_observe_add_job(ppu_context*);
void queue_fixture_set_id(std::uint64_t);

namespace {
constexpr unsigned workers = 8;
constexpr unsigned iterations = 64;
constexpr unsigned operation_count = workers * iterations * 3;
std::array<job_queue_event, operation_count * 2 + 4> events{};
std::atomic<unsigned> count{0};
std::atomic<unsigned> ready{0};
std::atomic<bool> start{false};
std::array<ppu_context, workers> contexts{};

void observe(void*, const job_queue_event& event) noexcept {
    const auto index = count.fetch_add(1, std::memory_order_relaxed);
    assert(index < events.size());
    events[index] = event;
}
}

void game_original_queue_reset_multi(ppu_context* ctx) { ctx->gpr[3] += 10; }
void game_original_queue_reset(ppu_context* ctx) { ctx->gpr[3] += 10; }
void game_original_queue_init(ppu_context* ctx) {
    ctx->gpr[3] += 20;
    ctx->gpr[4] += 30;
}
void game_original_add_job(ppu_context* ctx) { ++ctx->gpr[5]; }

int main() {
    job_queue_observer observer{nullptr, observe};
    assert(job_queue_observer_install(&observer));
    std::array<std::thread, workers> threads;
    for (unsigned worker = 0; worker < workers; ++worker) {
        threads[worker] = std::thread([worker] {
            auto& ctx = contexts[worker];
            ready.fetch_add(1, std::memory_order_release);
            while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
            for (unsigned iteration = 0; iteration < iterations; ++iteration) {
                ctx.gpr[3] = 0x1000 + worker * 0x100 + iteration;
                ctx.gpr[4] = iteration;
                ctx.lr = 0x87b800 + worker * 0x100 + iteration;
                ctx.gpr[5] = 0x1234567800000000ULL + worker * iterations + iteration;
                const auto object = ctx.gpr[3];
                const auto header = ctx.gpr[5];
                if (iteration & 1)
                    motorstorm_observe_queue_reset(&ctx);
                else
                    motorstorm_observe_queue_reset_multi(&ctx);
                motorstorm_observe_queue_init(&ctx);
                motorstorm_observe_add_job(&ctx);
                assert(ctx.gpr[3] == object + 30);
                assert(ctx.gpr[4] == iteration + 30);
                assert(ctx.gpr[5] == header + 1);
            }
        });
    }
    while (ready.load(std::memory_order_acquire) != workers) std::this_thread::yield();
    start.store(true, std::memory_order_release);
    for (auto& thread : threads) thread.join();
    assert(count == operation_count * 2);
    std::unordered_map<std::uint64_t, job_queue_event> pending;
    std::unordered_set<std::uint64_t> ids;
    std::unordered_set<std::uintptr_t> context_ids;
    for (const auto& ctx : contexts)
        context_ids.insert(reinterpret_cast<std::uintptr_t>(&ctx));
    for (unsigned index = 0; index < count; ++index) {
        const auto& event = events[index];
        assert(event.call_id && context_ids.count(event.context));
        if (event.phase == job_queue_phase::enter) {
            assert(ids.insert(event.call_id).second);
            assert(pending.emplace(event.call_id, event).second);
        } else {
            const auto found = pending.find(event.call_id);
            assert(found != pending.end());
            const auto& entered = found->second;
            assert(event.context == entered.context && event.object == entered.object);
            assert(event.argument == entered.argument && event.operation == entered.operation);
            assert(event.header == entered.header && event.entry_lr == entered.entry_lr);
            pending.erase(found);
        }
    }
    assert(pending.empty() && ids.size() == operation_count);

    // Zero explicitly exposes exhausted IDs. Valid IDs never wrap or repeat.
    queue_fixture_set_id(std::numeric_limits<std::uint64_t>::max());
    motorstorm_observe_queue_reset(&contexts[0]);
    motorstorm_observe_queue_reset(&contexts[0]);
    assert(events[operation_count * 2].call_id == std::numeric_limits<std::uint64_t>::max());
    assert(events[operation_count * 2 + 2].call_id == 0);
    assert(job_queue_observer_install(nullptr));
}

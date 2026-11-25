#include "../../src/motorstorm/job_capture.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <thread>
#include <vector>

static const ps3_atomic_observer* atomic_observer;
static const ps3_spu_execution_observer* execution_observer;
static const ps3_spurs_scheduler_observer* scheduler_observer;
extern "C" int ps3_atomic_observer_install_ppu(const ps3_atomic_observer* value) {
    atomic_observer = value;
    return 1;
}
extern "C" int ps3_atomic_observer_install_spu(const ps3_atomic_observer*) { return 1; }
extern "C" int ps3_spu_execution_observer_install(const ps3_spu_execution_observer* value) {
    execution_observer = value;
    return 1;
}
extern "C" int ps3_spurs_scheduler_observer_install(const ps3_spurs_scheduler_observer* value) {
    scheduler_observer = value;
    return 1;
}
extern "C" int ps3_spurs_current_dispatch(ps3_spurs_dispatch_info*) { return 0; }
extern "C" void fixture_seed_exclusions(job_capture*, bool);
extern "C" unsigned fixture_used_exclusion_shards(job_capture*);
static thread_local uint64_t identity;
static uint64_t thread_id(void*) { return identity; }
static uint64_t clock_tick(void*) { return 1; }
static int reject_atomic(void*, uint32_t, uintptr_t, uint64_t, uint32_t) { return 0; }
static int reject_execution(void*, uint32_t, uintptr_t, uint32_t, uint32_t) { return 0; }
static int reject_scheduler(void*, const ps3_spurs_scheduler_event*) { return 0; }
static int reject_queue(void*, const job_queue_event*) { return 0; }

int main() {
    job_capture_config config{1, 1000, 8, nullptr, clock_tick, thread_id,
        reject_atomic, reject_execution, reject_scheduler, reject_queue};
    for (bool collide : {false, true}) {
        auto* capture = job_capture_start(&config);
        assert(capture);
        std::atomic<unsigned> ready{0};
        std::atomic<bool> go{false};
        std::vector<std::thread> threads;
        for (unsigned i = 0; i < 8; ++i) {
            threads.emplace_back([&, i] {
                identity = collide ? 0 : i + 1;
                ready.fetch_add(1, std::memory_order_release);
                while (!go.load(std::memory_order_acquire)) std::this_thread::yield();
                ps3_spurs_scheduler_event scheduler{};
                job_queue_event queue{};
                for (unsigned n = 0; n < 10000; ++n) {
                    assert(!atomic_observer->accept(atomic_observer->user, 2, 1, 0x1000, 8));
                    assert(!execution_observer->accept(execution_observer->user, 1, 1, 0x10, 0x20));
                    assert(!scheduler_observer->accept(scheduler_observer->user, &scheduler));
                    job_capture_queue_call(capture, queue);
                }
            });
        }
        while (ready.load(std::memory_order_acquire) != 8) std::this_thread::yield();
        go.store(true, std::memory_order_release);
        for (auto& thread : threads) thread.join();
        job_capture_info info{};
        assert(job_capture_describe(capture, &info));
        assert(info.excluded_atomic == 80000 && info.excluded_execution == 80000);
        assert(info.excluded_scheduler == 80000 && info.excluded_queue_call == 80000);
        assert(info.storage.attempted == 0);
        const auto used = fixture_used_exclusion_shards(capture);
        assert(collide ? used == 1 : used > 1);
        identity = 1;
        fixture_seed_exclusions(capture, true);
        assert(!atomic_observer->accept(atomic_observer->user, 2, 1, 0x1000, 8));
        assert(job_capture_describe(capture, &info) && info.excluded_atomic == UINT64_MAX);
        fixture_seed_exclusions(capture, false);
        assert(job_capture_describe(capture, &info) && info.excluded_atomic == UINT64_MAX);
        job_capture_stop(capture);
    }
    puts("PASS concurrent exclusion shards, collisions, unknown IDs and saturation");
}
